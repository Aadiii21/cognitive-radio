#!/usr/bin/env python3
"""
BPSK frame definition shared by the TX waveform generator and the receiver.

One frame (one cyclic TX buffer) is:

    [ preamble | payload | silent padding ]
      64 sym     512 sym   64 960 sym (zero amplitude)   = 65 536 symbols

* Preamble: 63-chip m-sequence (x^6 + x + 1) plus one 0 chip. Unlike the
  earlier 0101... preamble, its aperiodic autocorrelation has a single peak,
  so frame timing and BPSK polarity are unambiguous.
* Payload bits are taken from payload bytes **LSB first** (bit 0 of byte 0 is
  the first transmitted payload bit). This matches the existing
  bpsk_joined_seed42 waveform and is written to the metadata explicitly.
* Bit -> symbol: 0 -> +1, 1 -> -1.
* Padding is zero amplitude (not constant +1), so the transmission is a short
  burst instead of a near-continuous unmodulated carrier.
* RRC pulse shaping is applied by circular convolution, so the cyclically
  repeated buffer has no discontinuity at the wrap-around point, and symbol k
  peaks exactly at sample k * sps.
* Amplitude: the burst (preamble + payload) is normalised to unit RMS.
  TX amplitude scaling is applied later, exactly once, by PlutoTXAdapter.

This file only defines and builds the waveform; it does not touch hardware.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

FRAME_FORMAT = "bpsk_frame_v2"


# ============================================================
# Bit helpers
# ============================================================
def bytes_to_bits(byte_values, bit_order: str = "lsb_first") -> np.ndarray:
    """Unpack bytes to bits in the given per-byte order."""
    arr = np.asarray(byte_values, dtype=np.uint8)
    if bit_order == "lsb_first":
        return np.unpackbits(arr, bitorder="little")
    if bit_order == "msb_first":
        return np.unpackbits(arr, bitorder="big")
    raise ValueError(f"Unknown bit order: {bit_order}")


def bits_to_bytes(bits, bit_order: str = "lsb_first") -> np.ndarray:
    """Pack bits (length multiple of 8) to bytes in the given per-byte order."""
    bits = np.asarray(bits, dtype=np.uint8)
    if len(bits) % 8:
        raise ValueError("Bit count must be a multiple of 8.")
    if bit_order == "lsb_first":
        return np.packbits(bits, bitorder="little")
    if bit_order == "msb_first":
        return np.packbits(bits, bitorder="big")
    raise ValueError(f"Unknown bit order: {bit_order}")


def bits_to_symbols(bits) -> np.ndarray:
    """BPSK mapping 0 -> +1, 1 -> -1."""
    return (1.0 - 2.0 * np.asarray(bits, dtype=np.float64)).astype(np.complex128)


def m_sequence_preamble() -> np.ndarray:
    """63-chip maximal-length sequence (x^6 + x + 1, seed 000001) plus a 0."""
    state = [0, 0, 0, 0, 0, 1]
    chips = []
    for _ in range(63):
        chips.append(state[-1])
        feedback = state[-1] ^ state[0]
        state = [feedback] + state[:-1]
    return np.array(chips + [0], dtype=np.uint8)


# ============================================================
# Pulse shaping (same definition as waveform_generator.rrc_filter)
# ============================================================
def rrc_taps(beta: float = 0.35, sps: int = 4, span: int = 10) -> np.ndarray:
    from src.radio.waveform_generator import rrc_filter

    return rrc_filter(beta=beta, sps=sps, span=span)


# ============================================================
# Frame specification
# ============================================================
@dataclass
class FrameSpec:
    preamble_bits: list
    payload_bytes: list
    total_symbols: int = 65_536
    sps: int = 4
    rolloff: float = 0.35
    rrc_span_symbols: int = 10
    payload_bit_order: str = "lsb_first"
    padding: str = "zeros"
    format: str = FRAME_FORMAT
    extra: dict = field(default_factory=dict)

    @property
    def preamble_len(self) -> int:
        return len(self.preamble_bits)

    @property
    def payload_bits(self) -> np.ndarray:
        return bytes_to_bits(self.payload_bytes, self.payload_bit_order)

    @property
    def payload_len(self) -> int:
        return 8 * len(self.payload_bytes)

    @property
    def burst_symbols(self) -> int:
        return self.preamble_len + self.payload_len

    @property
    def padding_symbols(self) -> int:
        return self.total_symbols - self.burst_symbols

    @property
    def frame_samples(self) -> int:
        return self.total_symbols * self.sps

    def burst_reference_symbols(self) -> np.ndarray:
        bits = np.concatenate([np.asarray(self.preamble_bits, np.uint8), self.payload_bits])
        return bits_to_symbols(bits)

    def validate(self):
        if self.padding_symbols < 0:
            raise ValueError("Preamble + payload exceed total_symbols.")
        if self.sps < 2:
            raise ValueError("sps must be >= 2.")
        if self.padding != "zeros":
            raise ValueError("Only zero padding is supported by this frame format.")

    @classmethod
    def from_metadata(cls, meta: dict) -> "FrameSpec":
        """Build from waveform metadata JSON. Requires explicit fields."""
        if meta.get("format") != FRAME_FORMAT:
            raise ValueError(
                f"Waveform metadata format is {meta.get('format')!r}, expected "
                f"{FRAME_FORMAT!r}. Older waveforms (e.g. bpsk_joined_seed42) "
                f"use an ambiguous 0101 preamble and are not supported."
            )
        spec = cls(
            preamble_bits=list(meta["preamble_bits"]),
            payload_bytes=list(meta["payload_bytes"]),
            total_symbols=int(meta["symbols"]),
            sps=int(meta["samples_per_symbol"]),
            rolloff=float(meta["rolloff"]),
            rrc_span_symbols=int(meta["rrc_span_symbols"]),
            payload_bit_order=meta["payload_bit_order"],
            padding=meta["padding"],
        )
        spec.validate()
        return spec


def build_frame_waveform(spec: FrameSpec) -> np.ndarray:
    """Return one frame of complex64 IQ at sps samples/symbol (burst RMS = 1)."""
    spec.validate()
    symbols = np.zeros(spec.total_symbols, dtype=np.complex128)
    symbols[: spec.burst_symbols] = spec.burst_reference_symbols()

    upsampled = np.zeros(spec.frame_samples, dtype=np.complex128)
    upsampled[:: spec.sps] = symbols

    taps = rrc_taps(spec.rolloff, spec.sps, spec.rrc_span_symbols)
    half = len(taps) // 2
    # Circular convolution, centred: symbol k peaks at sample k*sps.
    kernel = np.zeros(spec.frame_samples, dtype=np.float64)
    kernel[: half + 1] = taps[half:]
    kernel[-half:] = taps[:half]
    iq = np.fft.ifft(np.fft.fft(upsampled) * np.fft.fft(kernel))

    burst = iq[: spec.burst_symbols * spec.sps]
    iq /= np.sqrt(np.mean(np.abs(burst) ** 2))
    return iq.astype(np.complex64)


def make_metadata(spec: FrameSpec, iq: np.ndarray, sample_rate: float, seed, iq_path: Path,
                  payload_source: str) -> dict:
    burst = iq[: spec.burst_symbols * spec.sps]
    return {
        "format": FRAME_FORMAT,
        "modulation": "BPSK",
        "symbols": spec.total_symbols,
        "samples": int(len(iq)),
        "samples_per_symbol": spec.sps,
        "sample_rate_sps": float(sample_rate),
        "sample_rate_note": "Nominal rate the waveform was designed for. The "
                            "rate actually used is recorded per experiment.",
        "symbol_rate_sps": float(sample_rate) / spec.sps,
        "rolloff": spec.rolloff,
        "rrc_span_symbols": spec.rrc_span_symbols,
        "rrc_taps": spec.rrc_span_symbols * spec.sps + 1,
        "pulse_shaping": "root-raised-cosine, circular, symbol k peaks at sample k*sps",
        "bit_to_symbol": {"0": 1, "1": -1},
        "preamble": "m-sequence x^6+x+1 (63 chips) + 0",
        "preamble_bits": [int(b) for b in spec.preamble_bits],
        "payload_bytes": [int(b) for b in spec.payload_bytes],
        "payload_hex": bytes(int(b) for b in spec.payload_bytes).hex(),
        "payload_bit_order": spec.payload_bit_order,
        "payload_source": payload_source,
        "padding": spec.padding,
        "burst_symbols": spec.burst_symbols,
        "padding_symbols": spec.padding_symbols,
        "first_symbol_sample_index": 0,
        "normalization": "burst (preamble+payload) RMS = 1; TX amplitude scale not applied",
        "burst_average_power": float(np.mean(np.abs(burst) ** 2)),
        "frame_average_power": float(np.mean(np.abs(iq) ** 2)),
        "peak_amplitude": float(np.max(np.abs(iq))),
        "seed": seed,
        "iq_format": "complex64 interleaved float32",
        "iq_file": str(iq_path),
        "rf_transmission_enabled": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate a bpsk_frame_v2 waveform (no TX).")
    parser.add_argument("--seed", type=int, default=42, help="Seed for the random payload.")
    parser.add_argument("--payload-hex", default=None,
                        help="Use this payload instead of a random one (64 bytes).")
    parser.add_argument("--payload-bytes", type=int, default=64)
    parser.add_argument("--sample-rate", type=float, default=2_083_333.0,
                        help="Nominal design rate written to metadata (default 2083333).")
    parser.add_argument("--output", default="results/baseband/prepared")
    args = parser.parse_args()

    if args.payload_hex:
        payload = list(bytes.fromhex(args.payload_hex))
        source = "provided via --payload-hex"
        seed = None
    else:
        rng = np.random.default_rng(args.seed)
        payload = rng.integers(0, 256, args.payload_bytes, dtype=np.uint8).tolist()
        source = f"numpy default_rng({args.seed}).integers(0, 256, {args.payload_bytes}, uint8)"
        seed = args.seed

    spec = FrameSpec(preamble_bits=m_sequence_preamble().tolist(), payload_bytes=payload)
    iq = build_frame_waveform(spec)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{FRAME_FORMAT}_seed{seed}" if seed is not None else f"{FRAME_FORMAT}_custom"
    iq_path = out / f"{stem}.cf32"
    meta_path = out / f"{stem}.json"
    iq.tofile(iq_path)
    meta = make_metadata(spec, iq, args.sample_rate, seed, iq_path, source)
    meta_path.write_text(json.dumps(meta, indent=4))
    print(f"IQ       : {iq_path} ({len(iq)} samples)")
    print(f"Metadata : {meta_path}")
    print(f"Burst    : {spec.burst_symbols} symbols, padding {spec.padding_symbols} zero symbols")
    print(f"Peak     : {meta['peak_amplitude']:.4f} (burst RMS 1)")


if __name__ == "__main__":
    main()
