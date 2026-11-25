#!/usr/bin/env python3
"""Prepare framed multi-modulation SDR experiments and controller decisions.

Physical OTA transmission is intentionally not performed by this preparation
runner. The legacy physical runner is explicitly for conducted loopback and
must not be treated as an OTA runner.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime
from pathlib import Path

# Make `src` importable when run as `python scripts/run_multimod_experiment.py`
# (same approach as scripts/run_hardware_experiment.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.radio.multimod_frame import save_framed_waveform, SUPPORTED
from src.radio.cognitive_controller import CognitiveRadioController

def main():
    p = argparse.ArgumentParser(description="Prepare BPSK/QPSK/16-QAM framed SDR waveforms")
    p.add_argument("--modulations", nargs="+", choices=SUPPORTED, default=list(SUPPORTED))
    p.add_argument("--output-dir", default="results/baseband/multimod")
    p.add_argument("--symbols", type=int, default=65536)
    p.add_argument("--payload-bytes", type=int, default=128)
    p.add_argument("--sps", type=int, default=4)
    p.add_argument("--sample-rate", type=int, default=2083333)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--snr", nargs="*", type=float,
                   help="Optional measured per-channel SNRs to obtain one controller decision")
    p.add_argument("--enable-rf", action="store_true",
                   help="RF is deliberately unavailable in this preparation-only runner")
    args = p.parse_args()
    if args.enable_rf:
        p.error("This runner only prepares waveforms. The existing hardware runner is conducted-only; an OTA runner requires a separately reviewed and authorized RF configuration.")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for mod in args.modulations:
        iq_path, meta_path, meta, _ = save_framed_waveform(
            output, mod, payload_bytes=args.payload_bytes, total_symbols=args.symbols,
            sps=args.sps, sample_rate=args.sample_rate, seed=args.seed
        )
        records.append({
            "modulation": mod, "iq_file": str(iq_path), "metadata_file": str(meta_path),
            "samples": meta["samples"], "payload_bits": meta["payload_bits"],
            "burst_symbols": meta["burst_symbols"], "peak_amplitude": meta["peak_amplitude"]
        })
        print(f"{mod:5s} prepared: {iq_path} ({meta['samples']} complex samples)")
    result = {"timestamp": datetime.now().isoformat(), "records": records}
    if args.snr is not None:
        decision = CognitiveRadioController().decide(args.snr)
        result["controller_decision"] = decision.__dict__
        print("Controller decision:", json.dumps(decision.__dict__))
    manifest = output / "multimod_manifest.json"
    manifest.write_text(json.dumps(result, indent=2))
    print("Manifest:", manifest)
    print("RF status: NOT TRANSMITTED")

if __name__ == "__main__":
    main()
