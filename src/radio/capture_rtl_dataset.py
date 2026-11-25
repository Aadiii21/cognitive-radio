#!/usr/bin/env python3

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.radio.rtl_capture import capture_exact


def append_validation_manifest(metadata):
    """Append a completed RX validation capture without duplicating records."""
    manifest_path = Path("data/metadata/rx_validation_manifest.csv")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "capture_id",
        "status",
        "signal_class",
        "modulation",
        "iq_path",
        "feature_path",
        "center_frequency_hz",
        "sample_rate_sps",
        "rx_device",
        "rx_gain_db",
        "samples",
        "duration_seconds",
        "timestamp",
        "pll_warning",
        "saturated_bytes",
        "notes",
    ]

    existing_ids = set()

    if manifest_path.exists():
        with manifest_path.open("r", newline="") as f:
            reader = csv.DictReader(f)
            existing_ids = {
                row["capture_id"]
                for row in reader
                if row.get("capture_id")
            }

    if metadata["capture_id"] in existing_ids:
        raise ValueError(
            f"Capture already registered: {metadata['capture_id']}"
        )

    row = {
        "capture_id": metadata["capture_id"],
        "status": metadata["status"],
        "signal_class": metadata["signal_class"],
        "modulation": metadata["modulation"],
        "iq_path": metadata["iq_path"],
        "feature_path": metadata["feature_path"],
        "center_frequency_hz": metadata["center_frequency_hz"],
        "sample_rate_sps": metadata["sample_rate_sps"],
        "rx_device": metadata["rx_device"],
        "rx_gain_db": metadata["rx_gain_db"],
        "samples": metadata["samples"],
        "duration_seconds": metadata["duration_seconds"],
        "timestamp": metadata.get("capture_end_utc") or metadata.get("capture_timestamp_utc") or metadata.get("capture_start_utc", ""),
        "pll_warning": metadata["pll_warning"],
        "saturated_bytes": metadata.get("saturated_bytes", 0),
        "notes": metadata["notes"],
    }

    write_header = not manifest_path.exists() or manifest_path.stat().st_size == 0

    with manifest_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    print("Manifest updated:", manifest_path)

def main():
    parser = argparse.ArgumentParser(
        description="Capture and process RTL-SDR IQ dataset"
    )
    parser.add_argument("--fc", type=int, required=True)
    parser.add_argument("--fs", type=int, default=2_048_000)
    parser.add_argument("--gain", type=float, default=28.0)
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--label", default="ambient_unknown")
    parser.add_argument("--device", type=int, default=0)

    args = parser.parse_args()

    if args.fc <= 0 or args.fs <= 0 or args.duration <= 0:
        parser.error("Frequency, sample rate and duration must be positive")

    samples = int(args.fs * args.duration)
    capture_id = datetime.now().astimezone().strftime(
        "rtl_%Y%m%d_%H%M%S"
    )

    raw_dir = Path("data/raw/receiver_validation")
    metadata_dir = Path("data/metadata")
    raw_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    raw_path = raw_dir / f"{capture_id}.bin"
    metadata_path = metadata_dir / f"{capture_id}.json"

    feature_path = Path("results/features") / f"{capture_id}_features.csv"
    feature_path.parent.mkdir(parents=True, exist_ok=True)

    if raw_path.exists() or metadata_path.exists():
        raise FileExistsError("Capture ID already exists")

    command = [
        "rtl_sdr",
        "-d", str(args.device),
        "-f", str(args.fc),
        "-s", str(args.fs),
        "-g", str(args.gain),
        "-",
    ]

    print("Starting RTL-SDR capture...")
    start_time = datetime.now(timezone.utc)
    expected_bytes = samples * 2

    capture = capture_exact(
        command,
        expected_bytes=expected_bytes,
        timeout_s=args.duration + 30,
    )
    if capture.stderr:
        print(capture.stderr, end="")
    raw_path.write_bytes(capture.data)
    actual_bytes = raw_path.stat().st_size

    if actual_bytes != expected_bytes:
        raise RuntimeError(
            f"Capture failed: expected {expected_bytes} bytes, "
            f"received {actual_bytes}"
        )

    raw = np.fromfile(raw_path, dtype=np.uint8)

    if len(np.unique(raw)) < 100:
        raise RuntimeError("IQ capture has suspiciously low variation")

    saturated = int(np.count_nonzero((raw == 0) | (raw == 255)))

    print("IQ validation: PASS")
    print("Samples:", samples)
    print("Saturated bytes:", saturated)

    print("\nExtracting features...")

    subprocess.run(
        [
            sys.executable,
            "src/extract_features.py",
            "--input", str(raw_path),
            "--fc", str(args.fc),
            "--fs", str(args.fs),
        ],
        check=True,
    )

    if not feature_path.is_file():
        raise RuntimeError("Feature CSV was not generated")

    metadata = {
        "capture_id": capture_id,
        "status": "captured",
        "signal_class": args.label,
        "modulation": "unknown",
        "center_frequency_hz": args.fc,
        "sample_rate_sps": args.fs,
        "rx_device": "RTL-SDR R820T",
        "rx_gain_db": args.gain,
        "samples": samples,
        "duration_seconds": samples / args.fs,
        "iq_format": "uint8_interleaved_IQ",
        "iq_path": str(raw_path),
        "feature_path": str(feature_path),
        "capture_start_utc": start_time.isoformat(),
        "capture_end_utc": datetime.now(timezone.utc).isoformat(),
        "rtl_sdr_exit_code": capture.returncode,
        "saturated_bytes": saturated,
        "pll_warning": "PLL not locked" in capture.stderr,
        "notes": "Receive-only capture. Modulation label not independently verified."
    }

    metadata_path.write_text(json.dumps(metadata, indent=4))
    append_validation_manifest(metadata)

    print("\n========== CAPTURE COMPLETE ==========")
    print("Raw IQ:", raw_path)
    print("Features:", feature_path)
    print("Metadata:", metadata_path)


if __name__ == "__main__":
    main()
