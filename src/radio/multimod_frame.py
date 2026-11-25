#!/usr/bin/env python3
"""Common framed waveform builder for BPSK, QPSK and Gray-coded 16-QAM.

A frame contains a repeated BPSK acquisition pilot, a unique BPSK sync word,
then a modulation-specific payload. The complete frame is placed at the start
of a cyclic buffer followed by zero padding.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from src.radio.waveform_generator import rrc_filter

SUPPORTED = ("BPSK", "QPSK", "16QAM")

def bytes_to_bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8), bitorder="little")

def bits_to_bytes(bits: np.ndarray) -> bytes:
    bits = np.asarray(bits, dtype=np.uint8)
    if len(bits) % 8:
        raise ValueError("Bit count must be divisible by 8")
    return np.packbits(bits, bitorder="little").tobytes()

def m_sequence_127() -> np.ndarray:
    # Deterministic 7-bit maximal-length sequence, mapped 0 -> +1, 1 -> -1.
    state = [1, 0, 0, 0, 0, 0, 0]
    out = []
    for _ in range(127):
        out.append(state[-1])
        feedback = state[-1] ^ state[3]
        state = [feedback] + state[:-1]
    return (1.0 - 2.0 * np.asarray(out, dtype=np.float64)).astype(np.complex128)

def map_bits(bits: np.ndarray, modulation: str) -> np.ndarray:
    bits = np.asarray(bits, dtype=np.uint8)
    if modulation not in SUPPORTED:
        raise ValueError(f"Unsupported modulation {modulation}")
    bps = {"BPSK": 1, "QPSK": 2, "16QAM": 4}[modulation]
    if len(bits) % bps:
        raise ValueError(f"{modulation} requires bit count divisible by {bps}")
    # Signed integers: with uint8, 1 - 2*b wraps to 255 for b = 1, which mapped
    # every "1" bit of BPSK/QPSK to +255 (or +255/sqrt(2)) instead of -1.
    b = bits.reshape(-1, bps).astype(np.int16)
    if modulation == "BPSK":
        return (1 - 2*b[:, 0]).astype(np.complex128)
    if modulation == "QPSK":
        return ((1 - 2*b[:, 0]) + 1j*(1 - 2*b[:, 1])) / np.sqrt(2)
    levels = np.array([-3.0, -1.0, 3.0, 1.0])
    ii = 2*b[:, 0] + b[:, 1]
    qq = 2*b[:, 2] + b[:, 3]
    return (levels[ii] + 1j*levels[qq]) / np.sqrt(10)

def demap_symbols(symbols: np.ndarray, modulation: str) -> np.ndarray:
    z = np.asarray(symbols, dtype=np.complex128)
    if modulation == "BPSK":
        return (z.real < 0).astype(np.uint8)
    if modulation == "QPSK":
        out = np.empty((len(z), 2), dtype=np.uint8)
        out[:, 0] = z.real < 0
        out[:, 1] = z.imag < 0
        return out.reshape(-1)
    if modulation == "16QAM":
        levels = np.array([-3.0, -1.0, 3.0, 1.0]) / np.sqrt(10)
        idx_i = np.argmin(np.abs(z.real[:, None] - levels[None, :]), axis=1)
        idx_q = np.argmin(np.abs(z.imag[:, None] - levels[None, :]), axis=1)
        out = np.empty((len(z), 4), dtype=np.uint8)
        out[:, 0], out[:, 1] = idx_i // 2, idx_i % 2
        out[:, 2], out[:, 3] = idx_q // 2, idx_q % 2
        return out.reshape(-1)
    raise ValueError(f"Unsupported modulation {modulation}")

def build_framed_waveform(modulation="BPSK", payload_bytes=128, total_symbols=65536,
                          sps=4, sample_rate=2083333, beta=0.35, seed=42):
    if modulation not in SUPPORTED:
        raise ValueError(f"modulation must be one of {SUPPORTED}")
    if payload_bytes <= 0 or total_symbols <= 0 or sps < 2:
        raise ValueError("payload_bytes/total_symbols must be positive and sps >= 2")
    rng = np.random.default_rng(seed)
    payload = rng.integers(0, 256, payload_bytes, dtype=np.uint8)
    payload_bits = bytes_to_bits(payload.tobytes())
    payload_symbols = map_bits(payload_bits, modulation)
    # Constant +1 pilot (a CW tone after pulse shaping): its lag-1-symbol
    # phase increment gives a data- and timing-independent coarse CFO estimate.
    cfo_pilot = np.ones(64, dtype=np.complex128)
    sync = m_sequence_127()
    preamble = np.concatenate([cfo_pilot, sync])
    burst = np.concatenate([preamble, payload_symbols])
    if len(burst) > total_symbols:
        raise ValueError(f"Frame needs {len(burst)} symbols, buffer has {total_symbols}")
    symbols = np.zeros(total_symbols, dtype=np.complex128)
    symbols[:len(burst)] = burst
    up = np.zeros(total_symbols*sps, dtype=np.complex128)
    up[::sps] = symbols
    taps = rrc_filter(beta=beta, sps=sps, span=10)
    half = len(taps)//2
    kernel = np.zeros(len(up), dtype=np.float64)
    kernel[:half+1] = taps[half:]
    kernel[-half:] = taps[:half]
    iq = np.fft.ifft(np.fft.fft(up) * np.fft.fft(kernel))
    iq /= np.sqrt(np.mean(np.abs(iq[:len(burst)*sps])**2))
    meta = {
        "format": "multimod_frame_v1", "modulation": modulation,
        "payload_hex": payload.tobytes().hex(), "payload_bit_order": "lsb_first",
        "payload_bits": int(len(payload_bits)), "payload_symbols": int(len(payload_symbols)),
        "payload_bytes": int(payload_bytes), "preamble_symbols": int(len(preamble)),
        "cfo_pilot_symbols": int(len(cfo_pilot)), "sync_symbols": int(len(sync)),
        "burst_symbols": int(len(burst)), "total_symbols": int(total_symbols),
        "samples": int(len(iq)), "samples_per_symbol": int(sps),
        "sample_rate_sps": float(sample_rate), "symbol_rate_sps": float(sample_rate/sps),
        "rolloff": float(beta), "seed": int(seed), "iq_format": "complex64",
        "average_power": float(np.mean(np.abs(iq)**2)),
        "burst_rms": float(np.sqrt(np.mean(np.abs(iq[:len(burst)*sps])**2))),
        "peak_amplitude": float(np.max(np.abs(iq))),
    }
    return iq.astype(np.complex64), meta, payload_bits

def save_framed_waveform(output_dir, modulation, **kwargs):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    iq, meta, bits = build_framed_waveform(modulation=modulation, **kwargs)
    stem = f"{modulation.lower()}_framed_seed{kwargs.get('seed', 42)}"
    iq_path = output / f"{stem}.cf32"
    meta_path = output / f"{stem}.json"
    iq.tofile(iq_path)
    meta["iq_file"] = str(iq_path)
    meta_path.write_text(json.dumps(meta, indent=2))
    return iq_path, meta_path, meta, bits
