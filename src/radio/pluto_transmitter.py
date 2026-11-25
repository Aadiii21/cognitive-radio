#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

import numpy as np


def load_waveform(iq_path, metadata_path):
    iq_path = Path(iq_path)
    metadata_path = Path(metadata_path)

    if not iq_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError("IQ file or metadata file not found")

    metadata = json.loads(metadata_path.read_text())

    if metadata.get("iq_format") != "complex64 interleaved float32":
        raise ValueError("Unsupported IQ format")

    iq = np.fromfile(iq_path, dtype=np.complex64)

    if len(iq) != metadata["samples"]:
        raise ValueError("Sample count mismatch")

    if len(iq) == 0 or not np.isfinite(iq).all():
        raise ValueError("Invalid IQ samples")

    return iq, metadata


def prepare_for_transmission(iq, amplitude_scale=0.1, peak_limit=0.25):
    if amplitude_scale <= 0:
        raise ValueError("Amplitude scale must be positive")

    if not 0 < peak_limit <= 1:
        raise ValueError("Peak limit must be between 0 and 1")

    prepared = (iq * amplitude_scale).astype(np.complex64)
    peak = float(np.max(np.abs(prepared)))

    if peak > peak_limit:
        raise ValueError(
            f"Peak {peak:.4f} exceeds limit {peak_limit}"
        )

    return prepared


def main():
    parser = argparse.ArgumentParser(
        description="Prepare PlutoSDR IQ playback files"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--peak-limit", type=float, default=0.25)
    parser.add_argument("--amplitude-scale", type=float, default=0.1)

    args = parser.parse_args()

    iq, source_meta = load_waveform(args.input, args.metadata)

    prepared = prepare_for_transmission(
        iq,
        amplitude_scale=args.amplitude_scale,
        peak_limit=args.peak_limit,
    )

    power = np.abs(prepared) ** 2
    average_power = float(np.mean(power))
    peak_power = float(np.max(power))
    papr_db = float(10 * np.log10(peak_power / average_power))

    output_dir = Path("results/baseband/prepared")
    output_dir.mkdir(parents=True, exist_ok=True)

    modulation = source_meta["modulation"].lower()
    seed = source_meta.get("seed", 42)

    output_path = output_dir / f"{modulation}_seed{seed}_tx.cf32"
    metadata_path = output_path.with_suffix(".json")

    prepared.tofile(output_path)

    metadata = {
        "modulation": source_meta["modulation"],
        "samples": len(prepared),
        "sample_rate_sps": source_meta["sample_rate_sps"],
        "symbol_rate_sps": source_meta["symbol_rate_sps"],
        "samples_per_symbol": source_meta["samples_per_symbol"],
        "rolloff": source_meta["rolloff"],
        "amplitude_scale": args.amplitude_scale,
        "average_power": average_power,
        "peak_amplitude": float(np.max(np.abs(prepared))),
        "papr_db": papr_db,
        "iq_format": "complex64 interleaved float32",
        "iq_file": str(output_path),
        "rf_transmission_enabled": False,
    }

    metadata_path.write_text(json.dumps(metadata, indent=4))

    print(f"\n===== {source_meta['modulation']} TX PREPARATION =====")
    print(f"Samples         : {len(prepared)}")
    print(f"Amplitude scale : {args.amplitude_scale}")
    print(f"Average power   : {average_power:.6f}")
    print(f"Peak amplitude  : {metadata['peak_amplitude']:.6f}")
    print(f"PAPR            : {papr_db:.2f} dB")
    print(f"IQ output       : {output_path}")
    print(f"Metadata        : {metadata_path}")
    print("RF OUTPUT       : DISABLED")


if __name__ == "__main__":
    main()
