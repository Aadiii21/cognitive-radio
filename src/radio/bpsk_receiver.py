#!/usr/bin/env python3
"""
BPSK burst receiver for the bpsk_frame_v2 format (see src/radio/bpsk_frame.py).

Receive chain, applied to captured complex baseband IQ:

 1. DC removal (RTL-SDR has a DC offset at 0 Hz).
 2. Rate conversion from the *actual* RX rate to the *actual* TX rate
    (rational approximation, residual ratio error reported in ppm).
 3. RRC matched filter.
 4. Coarse CFO: spectral line of the squared BPSK signal at 2*CFO.
 5. Frame detection: preamble correlation at sample rate, normalised to [0, 1],
    with a detection threshold. Several cyclic repetitions may be found.
 6. Fractional timing: parabolic interpolation of the correlation peak and
    FFT fractional delay of the burst segment.
 7. Complex gain/phase (and BPSK polarity) from the known preamble.
 8. Residual CFO / phase drift: block-wise decision-directed phase, linear fit
    over the burst, two iterations.
 9. Hard decisions, payload extraction (preamble removed, padding never read).
10. BER over payload bits only, against the known transmitted payload.
11. Data-aided post-matched-filter symbol SNR estimate.

If no preamble exceeds the detection threshold, no BER is produced.

The previous implementation of this module (fixed 2083333/2048000 resampling,
1-sample-per-symbol reference, inverted decisions, payload at bits [0:512])
is described in docs/HARDWARE_PATH_AUDIT.md (A15, A16) and was replaced.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from fractions import Fraction

import numpy as np
from scipy.signal import resample_poly

from src.radio.bpsk_frame import FrameSpec, bits_to_bytes, rrc_taps

DEFAULT_DETECTION_THRESHOLD = 0.6
DEFAULT_MAX_CFO_HZ = 100_000.0
PHASE_BLOCK_SYMBOLS = 32


# ============================================================
# Results
# ============================================================
@dataclass
class FrameResult:
    start_sample: int                 # integer sample index (TX-rate grid) of preamble symbol 0
    fractional_timing: float          # samples, added to start_sample
    detection_metric: float           # normalised preamble correlation, 0..1
    residual_cfo_hz: float
    phase_rad: float
    preamble_bit_errors: int
    payload_bit_errors: int
    payload_bits_compared: int
    ber: float
    snr_db: float                     # data-aided, post-MF symbol SNR
    evm_rms_percent: float
    recovered_payload_hex: str


@dataclass
class ReceiverResult:
    detected: bool
    frames_detected: int
    frames: list = field(default_factory=list)
    total_payload_bit_errors: int | None = None
    total_payload_bits_compared: int | None = None
    ber: float | None = None
    coarse_cfo_hz: float | None = None
    tx_sample_rate_hz: float | None = None
    rx_sample_rate_hz: float | None = None
    resample_up: int = 1
    resample_down: int = 1
    resample_ratio_error_ppm: float = 0.0
    detection_threshold: float = DEFAULT_DETECTION_THRESHOLD
    max_detection_metric: float = 0.0
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ============================================================
# Building blocks
# ============================================================
def convert_rate(x: np.ndarray, tx_rate: float, rx_rate: float, max_denominator: int = 2000):
    """Resample RX-rate samples onto the TX-rate grid using the actual rates."""
    if tx_rate <= 0 or rx_rate <= 0:
        raise ValueError("Sample rates must be positive.")
    if not 0.5 <= tx_rate / rx_rate <= 2.0:
        raise ValueError(
            f"TX rate {tx_rate} and RX rate {rx_rate} differ by more than 2x: "
            f"inconsistent configuration, refusing to resample."
        )
    if tx_rate == rx_rate:
        return x, 1, 1, 0.0
    ratio = Fraction(tx_rate / rx_rate).limit_denominator(max_denominator)
    up, down = ratio.numerator, ratio.denominator
    error_ppm = ((up / down) / (tx_rate / rx_rate) - 1.0) * 1e6
    return resample_poly(x, up, down), up, down, float(error_ppm)


def coarse_cfo_squaring(y: np.ndarray, fs: float, max_cfo_hz: float) -> float:
    """CFO from the 2*CFO spectral line of the squared (MF-filtered) BPSK signal."""
    z = y * y
    nfft = 1 << int(np.ceil(np.log2(len(z))))
    spec = np.abs(np.fft.fft(z, nfft)) ** 2
    freqs = np.fft.fftfreq(nfft, d=1.0 / fs)
    mask = np.abs(freqs) <= 2.0 * max_cfo_hz
    idx_all = np.flatnonzero(mask)
    k = idx_all[np.argmax(spec[mask])]
    # Parabolic interpolation on log power around the peak.
    km, kp = (k - 1) % nfft, (k + 1) % nfft
    a, b, c = np.log(spec[km] + 1e-30), np.log(spec[k] + 1e-30), np.log(spec[kp] + 1e-30)
    denom = a - 2 * b + c
    delta = 0.5 * (a - c) / denom if denom != 0 else 0.0
    return float((freqs[k] + delta * fs / nfft) / 2.0)


def preamble_correlation(y: np.ndarray, preamble_symbols: np.ndarray, sps: int):
    """Normalised sample-rate correlation with the preamble (symbols spaced sps apart).

    Returns (complex correlation c[n], normalised metric m[n] in [0, 1]).
    c[n] = sum_k conj(p_k) * y[n + k*sps]
    """
    L = len(preamble_symbols)
    template = np.zeros((L - 1) * sps + 1, dtype=np.complex128)
    template[::sps] = preamble_symbols
    n_valid = len(y) - len(template) + 1
    if n_valid <= 0:
        raise ValueError("Capture shorter than the preamble.")
    # Correlation via FFT: c[n] = sum_m conj(t[m]) y[n+m]
    nfft = 1 << int(np.ceil(np.log2(len(y) + len(template))))
    Y = np.fft.fft(y, nfft)
    T = np.fft.fft(template[::-1].conj(), nfft)
    c = np.fft.ifft(Y * T)[len(template) - 1: len(template) - 1 + n_valid]
    comb = np.zeros_like(template, dtype=np.float64)
    comb[::sps] = 1.0
    P = np.fft.fft(np.abs(y) ** 2, nfft)
    C = np.fft.fft(comb[::-1], nfft)
    energy = np.real(np.fft.ifft(P * C))[len(template) - 1: len(template) - 1 + n_valid]
    energy = np.maximum(energy, 1e-30)
    metric = np.abs(c) / np.sqrt(L * energy)
    return c, np.clip(metric, 0.0, 1.0)


def fractional_advance(x: np.ndarray, mu: float) -> np.ndarray:
    """Return x(t + mu) for a band-limited signal (FFT phase ramp)."""
    if mu == 0:
        return x
    n = len(x)
    f = np.fft.fftfreq(n)
    return np.fft.ifft(np.fft.fft(x) * np.exp(2j * np.pi * f * mu))


def _block_phase_fit(r: np.ndarray, d: np.ndarray, block: int):
    """Fit phase(k) = phi0 + w*k from block-wise phases of r * conj(d)."""
    nb = len(r) // block
    if nb < 2:
        prod = r * np.conj(d)
        return float(np.angle(np.sum(prod))), 0.0
    prod = (r[: nb * block] * np.conj(d[: nb * block])).reshape(nb, block)
    sums = prod.sum(axis=1)
    phases = np.unwrap(np.angle(sums))
    centers = np.arange(nb) * block + (block - 1) / 2.0
    w, phi0 = np.polyfit(centers, phases, 1, w=np.abs(sums))
    return float(phi0), float(w)


# ============================================================
# Per-frame demodulation
# ============================================================
def _demodulate_frame(y, start, mu, spec: FrameSpec, symbol_rate):
    sps = spec.sps
    n_burst = spec.burst_symbols
    guard = 8 * sps
    lo, hi = start - guard, start + n_burst * sps + guard
    seg = np.zeros(hi - lo, dtype=np.complex128)
    src_lo, src_hi = max(lo, 0), min(hi, len(y))
    seg[src_lo - lo: src_hi - lo] = y[src_lo:src_hi]
    seg = fractional_advance(seg, mu)
    r = seg[guard: guard + n_burst * sps: sps].copy()

    ref = spec.burst_reference_symbols()
    L = spec.preamble_len
    pre_ref = ref[:L]

    # Gain, phase and polarity from the known preamble.
    g = np.vdot(pre_ref, r[:L]) / L
    if np.abs(g) < 1e-30:
        raise RuntimeError("Zero preamble gain after detection.")
    r = r / g
    phase0 = float(np.angle(g))

    # Residual frequency / phase drift: decision-directed linear phase fit.
    # The coarse CFO is normally accurate to a few Hz, so the residual drift
    # over one burst is small. A correction is accepted only if it increases
    # the mean decision metric; this prevents a noisy slope estimate at low
    # SNR from rotating the end of the burst into wrong decisions.
    def _metric(v):
        d = np.where(np.real(v) >= 0, 1.0, -1.0)
        d[:L] = pre_ref.real
        return float(np.mean(np.real(v) * d))

    total_w = 0.0
    phi_tot = 0.0
    k = np.arange(n_burst)
    for _ in range(2):
        d = np.where(np.real(r) >= 0, 1.0, -1.0).astype(np.complex128)
        d[:L] = pre_ref
        phi, w = _block_phase_fit(r, d, PHASE_BLOCK_SYMBOLS)
        candidate = r * np.exp(-1j * (phi + w * k))
        if _metric(candidate) <= _metric(r):
            break
        r = candidate
        total_w += w
        phi_tot += phi

    bits = (np.real(r) < 0).astype(np.uint8)
    pre_bits = np.asarray(spec.preamble_bits, dtype=np.uint8)
    payload_rx = bits[L: L + spec.payload_len]
    payload_tx = spec.payload_bits
    errors = int(np.sum(payload_rx != payload_tx))
    compared = int(len(payload_tx))

    # Data-aided SNR on the known burst symbols.
    a = float(np.mean(np.real(r * np.conj(ref))))
    noise = float(np.mean(np.abs(r - a * ref) ** 2))
    snr_db = float(10 * np.log10(a * a / noise)) if noise > 0 and a > 0 else float("inf")
    evm = float(100 * np.sqrt(noise) / abs(a)) if a != 0 else float("inf")

    return FrameResult(
        start_sample=int(start),
        fractional_timing=float(mu),
        detection_metric=0.0,
        residual_cfo_hz=float(total_w * symbol_rate / (2 * np.pi)),
        phase_rad=float(np.angle(np.exp(1j * (phase0 + phi_tot)))),
        preamble_bit_errors=int(np.sum(bits[:L] != pre_bits)),
        payload_bit_errors=errors,
        payload_bits_compared=compared,
        ber=errors / compared,
        snr_db=snr_db,
        evm_rms_percent=evm,
        recovered_payload_hex=bits_to_bytes(payload_rx, spec.payload_bit_order).tobytes().hex(),
    )


# ============================================================
# Full receiver
# ============================================================
def receive_bpsk(
    rx_iq,
    spec: FrameSpec,
    tx_sample_rate: float,
    rx_sample_rate: float,
    detection_threshold: float = DEFAULT_DETECTION_THRESHOLD,
    max_cfo_hz: float = DEFAULT_MAX_CFO_HZ,
    max_frames: int = 8,
) -> ReceiverResult:
    """Detect, synchronise and demodulate bpsk_frame_v2 bursts in captured IQ."""
    spec.validate()
    x = np.asarray(rx_iq, dtype=np.complex128)
    if x.ndim != 1 or len(x) == 0:
        raise ValueError("rx_iq must be a non-empty 1-D array.")
    if not np.all(np.isfinite(x)):
        raise ValueError("rx_iq contains non-finite samples.")

    result = ReceiverResult(
        detected=False,
        frames_detected=0,
        tx_sample_rate_hz=float(tx_sample_rate),
        rx_sample_rate_hz=float(rx_sample_rate),
        detection_threshold=float(detection_threshold),
    )

    x = x - np.mean(x)
    x, up, down, err_ppm = convert_rate(x, float(tx_sample_rate), float(rx_sample_rate))
    result.resample_up, result.resample_down, result.resample_ratio_error_ppm = up, down, err_ppm
    fs = float(tx_sample_rate)
    symbol_rate = fs / spec.sps

    burst_len = spec.burst_symbols * spec.sps
    if len(x) < burst_len + 16 * spec.sps:
        result.notes.append("Capture shorter than one burst; nothing to detect.")
        return result

    y = np.convolve(x, rrc_taps(spec.rolloff, spec.sps, spec.rrc_span_symbols), mode="same")

    cfo = coarse_cfo_squaring(y, fs, max_cfo_hz)
    result.coarse_cfo_hz = cfo
    y = y * np.exp(-2j * np.pi * cfo * np.arange(len(y)) / fs)

    pre_sym = spec.burst_reference_symbols()[: spec.preamble_len]
    c, m = preamble_correlation(y, pre_sym, spec.sps)
    result.max_detection_metric = float(m.max())

    # Peak picking: strongest first, suppress +-half a frame around each.
    work = m.copy()
    suppress = max(spec.frame_samples // 2, burst_len)
    starts = []
    while len(starts) < max_frames:
        n = int(np.argmax(work))
        if work[n] < detection_threshold:
            break
        work[max(0, n - suppress): n + suppress] = 0.0
        if n < 8 * spec.sps:
            result.notes.append(f"Preamble at sample {n} skipped: too close to capture start.")
            continue
        if n + burst_len + 8 * spec.sps > len(y):
            result.notes.append(f"Preamble at sample {n} skipped: burst truncated by capture end.")
            continue
        starts.append(n)
    starts.sort()

    for n in starts:
        mag = np.abs(c)
        a, b, cc = (mag[n - 1] if n > 0 else mag[n]), mag[n], (mag[n + 1] if n + 1 < len(mag) else mag[n])
        denom = a - 2 * b + cc
        mu = float(np.clip(0.5 * (a - cc) / denom, -0.5, 0.5)) if denom != 0 else 0.0
        fr = _demodulate_frame(y, n, mu, spec, symbol_rate)
        fr.detection_metric = float(m[n])
        result.frames.append(fr)

    result.frames_detected = len(result.frames)
    if result.frames:
        result.detected = True
        result.total_payload_bit_errors = int(sum(f.payload_bit_errors for f in result.frames))
        result.total_payload_bits_compared = int(sum(f.payload_bits_compared for f in result.frames))
        result.ber = result.total_payload_bit_errors / result.total_payload_bits_compared
    else:
        result.notes.append(
            f"No preamble above detection threshold {detection_threshold} "
            f"(max metric {result.max_detection_metric:.3f}). No BER computed."
        )
    return result


def calculate_ber(transmitted_bits, received_bits):
    """BER over equal-length bit arrays. Raises on length mismatch."""
    t = np.asarray(transmitted_bits, dtype=np.uint8)
    r = np.asarray(received_bits, dtype=np.uint8)
    if len(t) != len(r) or len(t) == 0:
        raise ValueError(f"Bit arrays must be non-empty and equal length ({len(t)} vs {len(r)}).")
    errors = int(np.sum(t != r))
    return errors / len(t), errors, len(t)
