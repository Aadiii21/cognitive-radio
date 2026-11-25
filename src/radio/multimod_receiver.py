#!/usr/bin/env python3
"""
Receiver for the multimod_frame_v1 format (src/radio/multimod_frame.py).

Frame (symbols, sps samples/symbol, circular RRC, burst RMS = 1):

    [ pilot: 64 x (+1) | sync: 127-chip m-sequence | payload (BPSK/QPSK/16QAM) | zeros ]

Modulation and payload length are NOT carried in-band. They are explicit
inputs (or read from trusted metadata for offline tests). There is no blind
modulation detection.

Receive chain:
 1. Input validation, DC removal (estimated from the quiet zero-padding
    blocks; a whole-capture mean is biased by the DC pilot at small CFO).
 2. Rate conversion from the actual RX rate to the actual TX rate
    (bpsk_receiver.convert_rate).
 3. RRC matched filter.
 4. Pilot acquisition + coarse CFO: lag-1-symbol autocorrelation
    c[n] = y[n+sps] * conj(y[n]) summed over a pilot-length window. On the
    constant pilot this is |a|^2 * exp(j*2*pi*f*sps/fs) for any sample phase.
    Candidates are ranked by the UNnormalised |sum c| (energy-weighted, so weak
    LO leakage or noise in the zero padding ranks low). Unambiguous for
    |CFO| < fs / (2*sps) (260 kHz at 2.083 MS/s, 4 SPS); max_cfo_hz caps it.
 5. CFO correction, then 127-symbol sync correlation in a window around the
    expected position (normalised to [0, 1], detection threshold). The sync
    word, not the pilot, defines the frame boundary.
 6. Fractional timing (parabolic peak + FFT fractional delay).
 7. Complex gain/phase from the 191 known pilot+sync symbols. All
    constellations have unit average energy, so one gain serves 16-QAM too.
 8. Residual CFO/phase drift: data-aided linear phase fit over pilot+sync,
    then guarded decision-directed refinement over the payload (accepted only
    if it reduces the mean decision error).
 9. Demapping with multimod_frame.demap_symbols.
10. Per-frame and aggregate payload BER (payload bits only), data-aided EVM
    and SNR.

A frame whose payload would run past the end of the capture is reported as
truncated, never decoded. No BER is produced without a detected frame.

This module does not transmit and does not touch hardware.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from src.radio.bpsk_receiver import convert_rate, fractional_advance, preamble_correlation
from src.radio.multimod_frame import SUPPORTED, bytes_to_bits, demap_symbols, m_sequence_127, map_bits
from src.radio.waveform_generator import rrc_filter

FRAME_FORMAT = "multimod_frame_v1"
BITS_PER_SYMBOL = {"BPSK": 1, "QPSK": 2, "16QAM": 4}
DEFAULT_DETECTION_THRESHOLD = 0.6
DEFAULT_MAX_CFO_HZ = 100_000.0
PHASE_BLOCK_SYMBOLS = 32
SYNC_SEARCH_SYMBOLS = 24   # +- search around the expected sync start
PILOT_EDGE_SYMBOLS = 4     # pilot symbols excluded at each edge of the CFO window


# ============================================================
# Frame specification
# ============================================================
@dataclass
class MultimodFrameSpec:
    modulation: str
    payload_bytes: bytes
    sps: int = 4
    rolloff: float = 0.35
    rrc_span_symbols: int = 10
    pilot_symbols: int = 64
    sync_symbols: int = 127
    total_symbols: int = 65_536

    def __post_init__(self):
        if self.modulation not in SUPPORTED:
            raise ValueError(f"modulation must be one of {SUPPORTED}")
        if self.sps < 2:
            raise ValueError("sps must be >= 2")
        if self.sync_symbols != 127:
            raise ValueError("multimod_frame_v1 uses the 127-chip sync word")
        if not self.payload_bytes:
            raise ValueError("payload must not be empty")
        if (8 * len(self.payload_bytes)) % BITS_PER_SYMBOL[self.modulation]:
            raise ValueError("payload bits not divisible by bits/symbol")
        if self.burst_symbols > self.total_symbols:
            raise ValueError("burst longer than the cyclic buffer")

    @property
    def payload_bits(self) -> np.ndarray:
        return bytes_to_bits(bytes(self.payload_bytes))

    @property
    def payload_symbols_count(self) -> int:
        return len(self.payload_bits) // BITS_PER_SYMBOL[self.modulation]

    @property
    def known_symbols(self) -> np.ndarray:
        return np.concatenate([np.ones(self.pilot_symbols, dtype=np.complex128), m_sequence_127()])

    @property
    def preamble_symbols(self) -> int:
        return self.pilot_symbols + self.sync_symbols

    @property
    def burst_symbols(self) -> int:
        return self.preamble_symbols + self.payload_symbols_count

    @property
    def frame_samples(self) -> int:
        return self.total_symbols * self.sps

    def reference_payload_symbols(self) -> np.ndarray:
        return map_bits(self.payload_bits, self.modulation)

    @classmethod
    def from_metadata(cls, meta: dict) -> "MultimodFrameSpec":
        if meta.get("format") != FRAME_FORMAT:
            raise ValueError(f"metadata format {meta.get('format')!r} is not {FRAME_FORMAT!r}")
        if meta.get("payload_bit_order") != "lsb_first":
            raise ValueError("only lsb_first payload bit order is defined for this format")
        spec = cls(
            modulation=meta["modulation"],
            payload_bytes=bytes.fromhex(meta["payload_hex"]),
            sps=int(meta["samples_per_symbol"]),
            rolloff=float(meta["rolloff"]),
            pilot_symbols=int(meta["cfo_pilot_symbols"]),
            sync_symbols=int(meta["sync_symbols"]),
            total_symbols=int(meta["total_symbols"]),
        )
        for key, value in (("payload_bits", len(spec.payload_bits)),
                           ("payload_symbols", spec.payload_symbols_count),
                           ("burst_symbols", spec.burst_symbols),
                           ("preamble_symbols", spec.preamble_symbols)):
            if int(meta[key]) != value:
                raise ValueError(f"metadata {key}={meta[key]} inconsistent with spec ({value})")
        return spec


# ============================================================
# Results
# ============================================================
@dataclass
class MultimodFrameResult:
    sync_start_sample: int          # TX-rate grid index of sync symbol 0 (frame boundary)
    fractional_timing: float
    pilot_metric: float             # normalised lag-1 pilot coherence, 0..1
    sync_metric: float              # normalised sync correlation, 0..1
    coarse_cfo_hz: float
    residual_cfo_hz: float
    phase_rad: float
    known_symbol_errors: int        # pilot+sync hard-decision errors (diagnostic)
    payload_bit_errors: int
    payload_bits_compared: int
    ber: float
    evm_rms_percent: float          # data-aided, payload symbols
    snr_db: float                   # data-aided, payload symbols (1/EVM^2)
    recovered_payload_hex: str


@dataclass
class MultimodReceiverResult:
    modulation: str
    detected: bool
    frames_detected: int
    frames: list = field(default_factory=list)
    total_payload_bit_errors: int | None = None
    total_payload_bits_compared: int | None = None
    ber: float | None = None
    tx_sample_rate_hz: float | None = None
    rx_sample_rate_hz: float | None = None
    resample_up: int = 1
    resample_down: int = 1
    resample_ratio_error_ppm: float = 0.0
    detection_threshold: float = DEFAULT_DETECTION_THRESHOLD
    max_sync_metric: float = 0.0
    truncated_frames: int = 0
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# Building blocks
# ============================================================
def _moving_sum(x: np.ndarray, window: int) -> np.ndarray:
    cs = np.concatenate([[0], np.cumsum(x)])
    return cs[window:] - cs[:-window]


DC_BLOCK_SAMPLES = 256


def estimate_dc(x: np.ndarray, block: int = DC_BLOCK_SAMPLES) -> complex:
    """Receiver DC offset estimated from the quietest blocks (zero padding).

    The whole-capture mean is biased by the signal itself: the 64-symbol
    constant pilot is DC when the CFO is near 0. Measured on noiseless IQ
    at CFO 0: mean subtraction limited payload SNR to 29-36 dB versus
    42-43 dB for an ideal matched filter. Blocks with power below the median
    are almost entirely zero padding (burst duty cycle << 50 %), so their
    mean is the receiver's own DC offset.
    """
    nb = len(x) // block
    if nb < 4:
        return complex(np.mean(x))
    blocks = x[: nb * block].reshape(nb, block)
    power = np.mean(np.abs(blocks) ** 2, axis=1)
    quiet = blocks[power <= np.median(power)]
    return complex(np.mean(quiet))


def pilot_statistic(y: np.ndarray, sps: int, window: int):
    """Lag-1-symbol autocorrelation summed over `window` samples.

    Returns (P[n] complex sum, E[n] energy normaliser), index n = window start.
    """
    c = y[sps:] * np.conj(y[:-sps])
    P = _moving_sum(c, window)
    e = np.abs(y) ** 2
    E = np.sqrt(_moving_sum(e[:-sps], window) * _moving_sum(e[sps:], window))
    return P, np.maximum(E, 1e-30)


def _nearest_points(z: np.ndarray, modulation: str) -> np.ndarray:
    return map_bits(demap_symbols(z, modulation), modulation)


def _linear_phase_fit(r, d, block):
    """phase(k) = phi0 + w*k from block sums of r*conj(d)."""
    nb = len(r) // block
    if nb < 2:
        return float(np.angle(np.sum(r * np.conj(d)))), 0.0
    prod = (r[: nb * block] * np.conj(d[: nb * block])).reshape(nb, block).sum(axis=1)
    phases = np.unwrap(np.angle(prod))
    centers = np.arange(nb) * block + (block - 1) / 2.0
    w, phi0 = np.polyfit(centers, phases, 1, w=np.abs(prod))
    return float(phi0), float(w)


FINE_LAG_SYMBOLS = 16


def _refine_pilot_cfo(y, n, win, sps, fs, coarse_cfo, lag=FINE_LAG_SYMBOLS):
    """Refine CFO on the pilot window [n, n+win) using a lag of `lag` symbols."""
    lag_s = lag * sps
    length = win - lag_s
    if length <= sps or n + win > len(y):
        return coarse_cfo
    idx = np.arange(n, n + win)
    seg = y[n:n + win] * np.exp(-2j * np.pi * coarse_cfo * idx / fs)
    acc = np.sum(seg[lag_s:] * np.conj(seg[:length]))
    return float(coarse_cfo + np.angle(acc) * fs / (2 * np.pi * lag_s))


TRACK_BLOCK_SYMBOLS = 32
TRACK_FREQ_GAIN = 0.15


def _track_payload(r, modulation, w0=0.0, block=TRACK_BLOCK_SYMBOLS, freq_gain=TRACK_FREQ_GAIN):
    """Second-order block tracker: phase += residual, w += freq_gain*residual/block.

    The residual of each block is the decision-directed phase error after
    applying the predicted phase ramp, so it stays within the constellation's
    ambiguity (+-pi/2 BPSK, +-pi/4 QPSK/16-QAM) as long as the prediction does.
    Returns (corrected symbols, final frequency estimate in rad/symbol).
    """
    out = np.empty_like(r)
    phase, w = 0.0, float(w0)
    for start in range(0, len(r), block):
        seg = r[start:start + block]
        n = np.arange(len(seg))
        pred = seg * np.exp(-1j * (phase + w * n))
        resid = float(np.angle(np.sum(pred * np.conj(_nearest_points(pred, modulation)))))
        out[start:start + len(seg)] = pred * np.exp(-1j * resid)
        phase += w * len(seg) + resid
        w += freq_gain * resid / len(seg)
    return out, w


# ============================================================
# Per-frame processing
# ============================================================
def _decode_frame(y, sync_start, mu, spec, symbol_rate, coarse_cfo, pilot_metric, sync_metric):
    sps = spec.sps
    L = spec.preamble_symbols
    n_burst = spec.burst_symbols
    start = sync_start - spec.pilot_symbols * sps
    guard = 8 * sps
    lo, hi = start - guard, start + n_burst * sps + guard
    seg = np.zeros(hi - lo, dtype=np.complex128)
    a, b = max(lo, 0), min(hi, len(y))
    seg[a - lo: b - lo] = y[a:b]
    seg = fractional_advance(seg, mu)
    r = seg[guard: guard + n_burst * sps: sps].copy()

    known = spec.known_symbols
    ref_payload = spec.reference_payload_symbols()
    k = np.arange(n_burst)

    # Gain/phase and residual frequency from the 191 known symbols.
    g = np.vdot(known, r[:L]) / np.vdot(known, known)
    if abs(g) < 1e-30:
        raise RuntimeError("zero gain on known symbols")
    r = r / g
    phi, w = _linear_phase_fit(r[:L], known, PHASE_BLOCK_SYMBOLS)
    r = r * np.exp(-1j * (phi + w * k))
    total_w, total_phi = w, float(np.angle(g)) + phi

    # Payload: block-wise decision-directed phase/frequency tracker. A single
    # linear phase fit extrapolated from the 191 known symbols drifts over
    # long payloads at low SNR (measured: BPSK BER 6-25x theory with 2048
    # payload symbols), so the phase is tracked block by block.
    payload, w_end = _track_payload(r[L:], spec.modulation, w0=0.0)
    total_w += w_end
    # Amplitude refit (matters for 16-QAM): least squares against decisions.
    d = _nearest_points(payload, spec.modulation)
    scale = float(np.real(np.vdot(d, payload)) / np.real(np.vdot(d, d)))
    if scale > 0:
        payload = payload / scale
    r = np.concatenate([r[:L], payload])

    payload = r[L:]
    bits_rx = demap_symbols(payload, spec.modulation)
    bits_tx = spec.payload_bits
    errors = int(np.sum(bits_rx != bits_tx))
    err_vec = payload - ref_payload
    evm2 = float(np.mean(np.abs(err_vec) ** 2) / np.mean(np.abs(ref_payload) ** 2))
    known_hard = np.where(np.real(r[:L]) >= 0, 1.0, -1.0)

    return MultimodFrameResult(
        sync_start_sample=int(sync_start),
        fractional_timing=float(mu),
        pilot_metric=float(pilot_metric),
        sync_metric=float(sync_metric),
        coarse_cfo_hz=float(coarse_cfo),
        residual_cfo_hz=float(total_w * symbol_rate / (2 * np.pi)),
        phase_rad=float(np.angle(np.exp(1j * total_phi))),
        known_symbol_errors=int(np.sum(known_hard != known.real)),
        payload_bit_errors=errors,
        payload_bits_compared=int(len(bits_tx)),
        ber=errors / len(bits_tx),
        evm_rms_percent=float(100 * np.sqrt(evm2)),
        snr_db=float(10 * np.log10(1 / evm2)) if evm2 > 0 else float("inf"),
        recovered_payload_hex=np.packbits(bits_rx, bitorder="little").tobytes().hex(),
    )


# ============================================================
# Full receiver
# ============================================================
def receive_multimod(
    rx_iq,
    spec: MultimodFrameSpec,
    tx_sample_rate: float,
    rx_sample_rate: float,
    detection_threshold: float = DEFAULT_DETECTION_THRESHOLD,
    max_cfo_hz: float = DEFAULT_MAX_CFO_HZ,
    max_frames: int = 8,
) -> MultimodReceiverResult:
    """Detect, synchronise and demodulate multimod_frame_v1 bursts in captured IQ."""
    x = np.asarray(rx_iq, dtype=np.complex128)
    if x.ndim != 1 or len(x) == 0:
        raise ValueError("rx_iq must be a non-empty 1-D array")
    if not np.all(np.isfinite(x)):
        raise ValueError("rx_iq contains non-finite samples")
    if not 0 < detection_threshold < 1:
        raise ValueError("detection_threshold must be in (0, 1)")

    res = MultimodReceiverResult(
        modulation=spec.modulation, detected=False, frames_detected=0,
        tx_sample_rate_hz=float(tx_sample_rate), rx_sample_rate_hz=float(rx_sample_rate),
        detection_threshold=float(detection_threshold),
    )
    fs = float(tx_sample_rate)
    sps = spec.sps
    symbol_rate = fs / sps
    if max_cfo_hz >= symbol_rate / 2:
        raise ValueError(f"max_cfo_hz must be < symbol_rate/2 = {symbol_rate / 2:.0f} Hz "
                         "(pilot lag-1 estimator ambiguity)")

    x = x - estimate_dc(x)
    x, up, down, err_ppm = convert_rate(x, fs, float(rx_sample_rate))
    res.resample_up, res.resample_down, res.resample_ratio_error_ppm = up, down, err_ppm

    burst_len = spec.burst_symbols * sps
    if len(x) < burst_len + 16 * sps:
        res.notes.append("Capture shorter than one burst; nothing to detect.")
        return res

    y = np.convolve(x, rrc_filter(beta=spec.rolloff, sps=sps, span=spec.rrc_span_symbols), mode="same")

    # Pilot candidates (energy-weighted), strongest first, one per frame period.
    win = (spec.pilot_symbols - 2 * PILOT_EDGE_SYMBOLS) * sps
    P, E = pilot_statistic(y, sps, win)
    strength = np.abs(P)
    suppress = max(spec.frame_samples // 2, burst_len)
    sync_ref = m_sequence_127()
    seen_sync = []
    work = strength.copy()
    attempts = 0
    while len(res.frames) < max_frames and attempts < 4 * max_frames:
        attempts += 1
        n = int(np.argmax(work))
        if work[n] <= 0:
            break
        work[max(0, n - suppress): n + suppress] = 0.0
        pilot_metric = float(strength[n] / E[n])
        cfo = float(np.angle(P[n]) * fs / (2 * np.pi * sps))
        if abs(cfo) > max_cfo_hz:
            res.notes.append(f"Candidate at {n}: CFO {cfo:.0f} Hz outside +-{max_cfo_hz:.0f} Hz, skipped.")
            continue
        # Fine CFO on the same pilot window with a FINE_LAG-symbol lag:
        # FINE_LAG x finer; unambiguous for a coarse error < fs/(2*sps*FINE_LAG)
        # (16 kHz at 2.083 MS/s). Measured coarse error at Es/N0 = 4 dB: ~5 kHz,
        # which alone rotates the 127-symbol sync word by ~7.7 rad.
        cfo = _refine_pilot_cfo(y, n, win, sps, fs, cfo)

        # The pilot window starts PILOT_EDGE symbols into the pilot; the plateau
        # of |P| has a width of 2*PILOT_EDGE symbols, so search the sync around it.
        expected_sync = n - PILOT_EDGE_SYMBOLS * sps + spec.pilot_symbols * sps
        lo = max(0, expected_sync - SYNC_SEARCH_SYMBOLS * sps)
        hi = min(len(y), expected_sync + SYNC_SEARCH_SYMBOLS * sps + spec.sync_symbols * sps)
        if hi - lo < spec.sync_symbols * sps:
            res.truncated_frames += 1
            res.notes.append(f"Candidate at {n}: sync search window truncated by capture edge.")
            continue
        idx = np.arange(lo, hi)
        seg = y[lo:hi] * np.exp(-2j * np.pi * cfo * idx / fs)
        c, m = preamble_correlation(seg, sync_ref, sps)
        j = int(np.argmax(m))
        sync_metric = float(m[j])
        res.max_sync_metric = max(res.max_sync_metric, sync_metric)
        if sync_metric < detection_threshold:
            continue
        sync_start = lo + j
        if any(abs(sync_start - s) < suppress for s in seen_sync):
            continue  # duplicate of an already decoded frame
        frame_start = sync_start - spec.pilot_symbols * sps
        frame_end = frame_start + burst_len + 8 * sps
        if frame_start - 8 * sps < 0 or frame_end > len(y):
            res.truncated_frames += 1
            res.notes.append(f"Frame with sync at {sync_start} truncated by capture edge; not decoded.")
            continue
        mag = np.abs(c)
        a_, b_, c_ = (mag[j - 1] if j > 0 else mag[j]), mag[j], (mag[j + 1] if j + 1 < len(mag) else mag[j])
        denom = a_ - 2 * b_ + c_
        mu = float(np.clip(0.5 * (a_ - c_) / denom, -0.5, 0.5)) if denom != 0 else 0.0

        yc = y * np.exp(-2j * np.pi * cfo * np.arange(len(y)) / fs)
        fr = _decode_frame(yc, sync_start, mu, spec, symbol_rate, cfo, pilot_metric, sync_metric)
        res.frames.append(fr)
        seen_sync.append(sync_start)

    res.frames.sort(key=lambda f: f.sync_start_sample)
    res.frames_detected = len(res.frames)
    if res.frames:
        res.detected = True
        res.total_payload_bit_errors = int(sum(f.payload_bit_errors for f in res.frames))
        res.total_payload_bits_compared = int(sum(f.payload_bits_compared for f in res.frames))
        res.ber = res.total_payload_bit_errors / res.total_payload_bits_compared
    else:
        res.notes.append(f"No sync word above detection threshold {detection_threshold} "
                         f"(max {res.max_sync_metric:.3f}). No BER computed.")
    return res
