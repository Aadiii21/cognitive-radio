"""Deep-learning modulation classifier: IQ window -> BPSK / QPSK / 16-QAM.

Training data is synthetic but is passed through the same chain as a real
capture, so the network sees what the receiver sees:

  random payload bits -> map_bits -> RRC (beta 0.35, 4 sps, 2.083 MS/s)
  -> CFO, phase, timing offset, AWGN at a chosen Es/N0
  -> resample to the RTL-SDR rate (2.048 MS/s) -> 8-bit RTL quantisation
  -> DC removal -> resample back to the TX grid (bpsk_receiver.convert_rate)
  -> windows of WINDOW samples, unit RMS

Real test data is the payload part of each frame the multimod receiver found
in the OTA captures (results/hardware/captures/*.cu8), cut the same way. The
classifier gets no CFO or phase correction: it must cope with the raw signal.

Payload bits are random for every training example, so the network cannot
memorise the fixed seed-42 payload used on air.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from src.radio.bpsk_receiver import convert_rate
from src.radio.multimod_frame import map_bits
from src.radio.multimod_receiver import estimate_dc
from src.radio.waveform_generator import rrc_filter

CLASSES = ("BPSK", "QPSK", "16QAM")
BITS_PER_SYMBOL = {"BPSK": 1, "QPSK": 2, "16QAM": 4}
SPS = 4
TX_RATE = 2_083_333.0
RX_RATE = 2_048_000.0
WINDOW = 512            # samples on the TX grid = 128 symbols
STRIDE = 256
SYNC_SYMBOLS = 127
EDGE = 8                # samples skipped at each end of the payload (pulse tails)


# ------------------------------------------------------------------ synthetic data
@dataclass
class ImpairmentRanges:
    esn0_db: tuple = (0.0, 26.0)
    cfo_hz: tuple = (-30_000.0, 30_000.0)
    rms_lsb: tuple = (1.5, 40.0)     # RTL input level after gain, in 8-bit LSB
    dc_lsb: tuple = (-1.5, 1.5)


def _shaped_burst(modulation, n_symbols, rng):
    bits = rng.integers(0, 2, n_symbols * BITS_PER_SYMBOL[modulation])
    sym = map_bits(bits, modulation)
    up = np.zeros(len(sym) * SPS, dtype=np.complex128)
    up[::SPS] = sym
    x = np.convolve(up, rrc_filter(beta=0.35, sps=SPS, span=10), mode="same")
    return x / np.sqrt(np.mean(np.abs(x) ** 2))


def rtl_chain(x_tx, rng, esn0_db, cfo_hz, rms_lsb, dc_lsb):
    """TX-grid signal -> impairments -> 8-bit RTL samples -> back on the TX grid."""
    n = np.arange(len(x_tx))
    x = x_tx * np.exp(1j * (2 * np.pi * cfo_hz * n / TX_RATE + rng.uniform(0, 2 * np.pi)))
    sigma2 = SPS / 10 ** (esn0_db / 10)          # signal power 1 per sample -> Es = SPS
    x = x + np.sqrt(sigma2 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    up, down = 1565, 1592                         # 2.048 / 2.083333 MS/s
    x = resample_poly(x, up, down)                # onto the RTL sample grid
    scale = rms_lsb / np.sqrt(np.mean(np.abs(x) ** 2))
    i = np.clip(np.round(x.real * scale + 127.5 + dc_lsb), 0, 255)
    q = np.clip(np.round(x.imag * scale + 127.5 + dc_lsb), 0, 255)
    y = (i - 127.5) + 1j * (q - 127.5)
    y = y - estimate_dc(y)
    y, *_ = convert_rate(y, TX_RATE, RX_RATE)
    return y


def windows_from(x, start, length, window=WINDOW, stride=STRIDE):
    out = []
    for s in range(start + EDGE, start + length - EDGE - window + 1, stride):
        w = x[s:s + window]
        rms = np.sqrt(np.mean(np.abs(w) ** 2))
        if len(w) == window and rms > 0:
            out.append(w / rms)
    return out


def synthetic_dataset(n_per_class, seed=0, ranges: ImpairmentRanges | None = None, esn0_db=None):
    """Returns X (N, 2, WINDOW) float32, y (N,) int64, esn0 (N,) float."""
    rng = np.random.default_rng(seed)
    r = ranges or ImpairmentRanges()
    X, y, e = [], [], []
    for label, mod in enumerate(CLASSES):
        got = 0
        while got < n_per_class:
            snr = float(esn0_db) if esn0_db is not None else rng.uniform(*r.esn0_db)
            x = _shaped_burst(mod, 256, rng)
            y_tx = rtl_chain(x, rng, snr, rng.uniform(*r.cfo_hz), rng.uniform(*r.rms_lsb), rng.uniform(*r.dc_lsb))
            off = int(rng.integers(0, 64))
            for w in windows_from(y_tx, 64 + off, len(y_tx) - 128 - off)[:2]:
                if got < n_per_class:
                    X.append(w), y.append(label), e.append(snr)
                    got += 1
    return to_tensor_array(X), np.array(y, dtype=np.int64), np.array(e)


def to_tensor_array(windows):
    W = np.asarray(windows)
    return np.stack([W.real, W.imag], axis=1).astype(np.float32)


# ------------------------------------------------------------------ real captures
def load_cu8(path):
    raw = np.fromfile(path, dtype=np.uint8).astype(np.float64)
    return (raw[0::2] - 127.5) + 1j * (raw[1::2] - 127.5)


def real_dataset(project_root, results_glob="results/hardware/experiment_results/experiment_result_*.json"):
    """Payload windows from every multimod_frame_v1 OTA run that decoded frames.

    Returns X, y, rows; rows[i] = dict(run, capture, modulation, frame, esn0_db, frame_ber, ...)
    so predictions can be grouped per frame / per capture.
    """
    root = Path(project_root)
    X, y, rows = [], [], []
    for rp in sorted(root.glob(results_glob)):
        rec = json.loads(rp.read_text())
        if rec.get("waveform_format") != "multimod_frame_v1" or not rec.get("receiver"):
            continue
        frames = rec["receiver"].get("frames") or []
        cap = root / "results" / "hardware" / "captures" / Path(rec["rx_capture_file"]).name
        if not frames or not cap.exists():
            continue
        meta = json.loads((root / rec["waveform_metadata"]).read_text())
        mod = meta["modulation"]
        n_payload = meta["payload_symbols"] * SPS
        x = load_cu8(cap)
        x = x - estimate_dc(x)
        x, *_ = convert_rate(x, float(rec["tx_sample_rate_hz_used"]), float(rec["rx_sample_rate_hz_used"]))
        for k, fr in enumerate(frames):
            start = int(fr["sync_start_sample"]) + SYNC_SYMBOLS * SPS
            for w in windows_from(x, start, n_payload):
                X.append(w)
                y.append(CLASSES.index(mod))
                rows.append({"run": rp.name, "capture": cap.name, "modulation": mod, "frame": k,
                             "esn0_db": float(fr["snr_db"]), "frame_ber": float(fr["ber"]),
                             "pluto_attenuation_db": rec.get("tx", {}).get("requested_attenuation_db")})
    if not X:
        return np.zeros((0, 2, WINDOW), np.float32), np.zeros(0, np.int64), rows
    return to_tensor_array(X), np.array(y, dtype=np.int64), rows


# ------------------------------------------------------------------ classical baseline
def cumulant_features(X):
    """Higher-order-statistics features (the textbook non-DL approach)."""
    z = X[:, 0] + 1j * X[:, 1]
    c21 = np.mean(np.abs(z) ** 2, axis=1)
    c20 = np.mean(z ** 2, axis=1)
    m40 = np.mean(z ** 4, axis=1)
    m42 = np.mean(np.abs(z) ** 4, axis=1)
    c40 = m40 - 3 * c20 ** 2
    c42 = m42 - np.abs(c20) ** 2 - 2 * c21 ** 2
    a = np.abs(z)
    kurt = np.mean((a - a.mean(1, keepdims=True)) ** 4, 1) / (np.var(a, 1) ** 2 + 1e-12)
    return np.stack([np.abs(c20) / c21, np.abs(c40) / c21 ** 2, c42 / c21 ** 2, kurt, np.std(a, 1)], axis=1)


# ------------------------------------------------------------------ model
def build_model():
    import torch.nn as nn

    def block(cin, cout, k):
        return nn.Sequential(nn.Conv1d(cin, cout, k, padding=k // 2), nn.BatchNorm1d(cout), nn.ReLU())

    return nn.Sequential(
        block(2, 32, 7), block(32, 32, 7), nn.MaxPool1d(2),
        block(32, 64, 5), block(64, 64, 5), nn.MaxPool1d(2),
        block(64, 96, 3), block(96, 96, 3),
        nn.AdaptiveAvgPool1d(1), nn.Flatten(),
        nn.Dropout(0.3), nn.Linear(96, len(CLASSES)),
    )


def predict(model, X, batch=512):
    import torch
    model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(X), batch):
            out.append(torch.softmax(model(torch.from_numpy(X[i:i + batch])), 1).numpy())
    return np.concatenate(out) if out else np.zeros((0, len(CLASSES)))
