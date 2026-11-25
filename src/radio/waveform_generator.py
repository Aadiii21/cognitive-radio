#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.signal import convolve


def rrc_filter(beta=0.35, sps=4, span=10):
    """Generate a root-raised-cosine pulse shaping filter."""
    n = np.arange(-span * sps // 2, span * sps // 2 + 1)
    t = n / sps
    h = np.zeros_like(t, dtype=np.float64)

    for i, x in enumerate(t):
        if np.isclose(x, 0.0):
            h[i] = 1 - beta + 4 * beta / np.pi

        elif beta > 0 and np.isclose(abs(x), 1 / (4 * beta)):
            h[i] = (
                beta / np.sqrt(2)
                * (
                    (1 + 2 / np.pi) * np.sin(np.pi / (4 * beta))
                    + (1 - 2 / np.pi) * np.cos(np.pi / (4 * beta))
                )
            )

        else:
            numerator = (
                np.sin(np.pi * x * (1 - beta))
                + 4 * beta * x * np.cos(np.pi * x * (1 + beta))
            )
            denominator = np.pi * x * (1 - (4 * beta * x) ** 2)
            h[i] = numerator / denominator

    h /= np.sqrt(np.sum(h**2))
    return h


def generate_symbols(modulation, count, rng):
    if modulation == "BPSK":
        bits = rng.integers(0, 2, count)
        return (1 - 2 * bits).astype(np.complex64)

    if modulation == "QPSK":
        bits = rng.integers(0, 2, (count, 2))
        i = 1 - 2 * bits[:, 0]
        q = 1 - 2 * bits[:, 1]
        return ((i + 1j * q) / np.sqrt(2)).astype(np.complex64)

    if modulation == "16QAM":
        bits = rng.integers(0, 2, (count, 4))

        # Gray-coded 4-PAM mapping.
        levels = np.array([-3, -1, 3, 1])

        i_idx = 2 * bits[:, 0] + bits[:, 1]
        q_idx = 2 * bits[:, 2] + bits[:, 3]

        i = levels[i_idx]
        q = levels[q_idx]

        return ((i + 1j * q) / np.sqrt(10)).astype(np.complex64)

    raise ValueError(f"Unsupported modulation: {modulation}")


def generate_waveform(modulation, count, sps, beta, seed):
    rng = np.random.default_rng(seed)

    symbols = generate_symbols(modulation, count, rng)

    # Upsample by inserting zeros.
    upsampled = np.zeros(count * sps, dtype=np.complex64)
    upsampled[::sps] = symbols

    # Root-raised-cosine pulse shaping.
    taps = rrc_filter(beta=beta, sps=sps)
    iq = convolve(upsampled, taps, mode="same")

    # Normalize average power.
    iq /= np.sqrt(np.mean(np.abs(iq) ** 2))

    return iq.astype(np.complex64), symbols, taps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modulation", choices=["BPSK", "QPSK", "16QAM"],
                        required=True)
    parser.add_argument("--symbols", type=int, default=65536)
    parser.add_argument("--sps", type=int, default=4)
    parser.add_argument("--sample-rate", type=int, default=2400000)
    parser.add_argument("--beta", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="results/baseband")

    args = parser.parse_args()

    if args.symbols <= 0 or args.sps <= 0:
        parser.error("symbols and sps must be positive")

    if not 0 <= args.beta <= 1:
        parser.error("beta must be between 0 and 1")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    iq, symbols, taps = generate_waveform(
        args.modulation,
        args.symbols,
        args.sps,
        args.beta,
        args.seed,
    )

    stem = f"{args.modulation.lower()}_seed{args.seed}"

    iq_path = output_dir / f"{stem}.cf32"
    metadata_path = output_dir / f"{stem}.json"

    iq.tofile(iq_path)

    metadata = {
        "modulation": args.modulation,
        "symbols": args.symbols,
        "samples": len(iq),
        "samples_per_symbol": args.sps,
        "sample_rate_sps": args.sample_rate,
        "symbol_rate_sps": args.sample_rate / args.sps,
        "rolloff": args.beta,
        "filter": "root-raised-cosine",
        "filter_taps": len(taps),
        "seed": args.seed,
        "iq_format": "complex64 interleaved float32",
        "average_power": float(np.mean(np.abs(iq) ** 2)),
        "peak_amplitude": float(np.max(np.abs(iq))),
        "iq_file": str(iq_path),
    }

    metadata_path.write_text(json.dumps(metadata, indent=4))

    print("\n===== WAVEFORM GENERATED =====")
    print(f"Modulation     : {args.modulation}")
    print(f"Symbols        : {args.symbols}")
    print(f"IQ samples     : {len(iq)}")
    print(f"Sample rate    : {args.sample_rate / 1e6:.3f} MSPS")
    print(f"Symbol rate    : {args.sample_rate / args.sps / 1e3:.1f} kSymbols/s")
    print(f"Average power  : {metadata['average_power']:.6f}")
    print(f"Peak amplitude : {metadata['peak_amplitude']:.6f}")
    print(f"IQ file        : {iq_path}")
    print(f"Metadata       : {metadata_path}")


if __name__ == "__main__":
    main()
