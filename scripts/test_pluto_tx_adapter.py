#!/usr/bin/env python3
"""
Hardware Test Script: Pluto TX Adapter over-the-air demonstration.

Usage:
  1. Software-only test (no hardware):
     python scripts/test_pluto_tx_adapter.py --test-mode

  2. Hardware transmission (operator CONFIRMS SAFTY first):
     python scripts/pluto_to_rtl_sdr_demo.py --modulation BPSK --symbols 65536 --seed 42 --enable-rf

Safety Notes:
  - RF transmission is disabled by default. Use --enable-rf to enable.
  - Operator must confirm:
    * Safe conducted RF path (attenuator)
    * Minimum 30 dB attenuation between TX and RX
    * Regulatory authorization for transmission frequency
    * No RF radiation hazards; antenna not connected
  - Do NOT connect Pluto TX directly to RTL-SDR RX without an isolator/attenuator.
  - All hardware tests are opt-in and operator-controlled.

Requirements:
  - GNU Radio 3.10.x
  - libiio (for Pluto SDR)
  - ADALM-Pluto (AD9363A) via USB
  - RTL-SDR (RTL2838/R820T) via USB
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.radio.pluto_tx_adapter import (
    PlutoTXAdapter,
    RTLSDRReceiver,
    generate_waveform,
    set_rf_enabled,
)


def print_safety_checklist():
    """Print safety checklist before hardware operation."""
    print("\n" + "=" * 60)
    print("  SAFETY CHECKLIST")
    print("=" * 60)
    print("  Before enabling RF transmission, confirm:")
    print("  [ ] A safe conducted RF path is in place (attenuator)")
    print("  [ ] Minimum 30 dB attenuation between TX and RX")
    print("  [ ] Regulatory authorization for transmission frequency")
    print("  [ ] No RF radiation hazards; antenna not connected")
    print("  [ ] USB cables secured and devices powered")
    print("  [ ] Emergency stop procedure known")
    print("  [ ] All equipment grounded")
    print("  [ ] Receiver gain set safely (no saturation)")
    print("=" * 60)
    print()


def run_hardware_test(args):
    """
    Run the hardware transmission test.

    This function is called only when --enable-rf is specified.
    It performs actual RF transmission and verification.
    """
    print("=" * 60)
    print("  PLUTO TX ADAPTER — HARDWARE TRANSMISSION")
    print("=" * 60)
    print(f"  Modulation    : {args.modulation}")
    print(f"  Symbols       : {args.symbols}")
    print(f"  Sample rate   : 2400000 SPS")
    print(f"  Center freq   : {args.frequency / 1e6:.3f} MHz")
    print(f"  Attenuation   : {args.attenuation} dB")
    print(f"  RF enabled    : YES")
    print("=" * 60)

    # Generate waveform
    iq, symbols, taps = generate_waveform(
        args.modulation, args.symbols, args.sps, args.beta, args.seed
    )

    # Prepare for TX
    prepared = (iq * args.amplitude_scale).astype(np.complex64)
    peak = float(np.max(np.abs(prepared)))
    if peak > 0.25:
        raise ValueError(f"Peak {peak:.4f} exceeds limit 0.25")

    # Configure Pluto adapter
    adapter = PlutoTXAdapter()
    adapter.configure(args.frequency, args.attenuation)
    adapter.prepare(prepared)

    # Transmit
    print("\nTransmitting...")
    try:
        adapter.transmit()
    except Exception as e:
        print(f"\nTX transmission error: {e}")
        print("This may be due to missing hardware or GNU Radio IIO support.")
        print("The waveform generation still succeeded.")
        adapter.close()
        raise

    print(f"\n===== TX COMPLETE =====")
    print(f"  Samples       : {len(prepared)}")
    print(f"  Frequency     : {args.frequency / 1e6:.3f} MHz")
    print(f"  Attenuation   : {args.attenuation} dB")

    # Verify with RTL-SDR receiver
    print("\nVerifying with RTL-SDR...")
    receiver = RTLSDRReceiver(
        center_frequencies=[args.frequency],
        sample_rate=256_000,
        capture_samples=2048,
    )
    measurement = receiver.measure(args.frequency)

    print(f"\n===== RTL-SDR VERIFICATION =====")
    print(f"  Detected      : {measurement['detected']}")
    print(f"  SNR           : {measurement['snr_db']:.2f} dB")
    print(f"  BER (est.)    : {measurement['ber']:.4f}")
    print(f"  PDR           : {measurement['pdr']:.2f}")

    # Save results
    results_dir = Path("results/hardware/pluto_tx")
    results_dir.mkdir(parents=True, exist_ok=True)
    result_file = results_dir / f"pluto_tx_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    results = {
        "timestamp": datetime.now().isoformat(),
        "modulation": args.modulation,
        "symbols": args.symbols,
        "samples": args.symbols,
        "frequency_hz": args.frequency,
        "attenuation_db": args.attenuation,
        "amplitude_scale": args.amplitude_scale,
        "rf_enabled": True,
        "detection": {
            "detected": measurement["detected"],
            "signal_power_db": measurement["signal_power_db"],
            "snr_db": measurement["snr_db"],
            "ber": measurement["ber"],
            "pdr": measurement["pdr"],
            "frequency_offset_hz": measurement["frequency_offset_hz"],
        },
        "status": "complete" if measurement["detected"] else "partial",
    }

    result_file.write_text(json.dumps(results, indent=4))

    print(f"\n===== RESULTS SAVED =====")
    print(f"  File          : {result_file}")
    print(f"  Status        : {'DETECTED' if measurement['detected'] else 'NOT DETECTED'}")

    if not measurement["detected"]:
        print("  WARNING: Signal not detected on RTL-SDR.")
        print("  Possible causes:")
        print("    - Insufficient attenuation (signal too weak)")
        print("    - Frequency mismatch")
        print("    - RF path not connected")
        print("    - Regulatory/operational restrictions")

    return measurement["detected"]


def run_software_test(args):
    """Run software-only test without hardware."""
    print("=" * 60)
    print("  PLUTO TX ADAPTER — SOFTWARE TEST")
    print("=" * 60)
    print("  Mode          : SOFTWARE ONLY (no RF)")
    print(f"  Modulation    : {args.modulation}")
    print(f"  Symbols       : {args.symbols}")
    print(f"  Sample rate   : 2400000 SPS")
    print("  RF transmission: DISABLED (safe)")
    print("=" * 60)

    # Generate waveform
    iq, symbols, taps = generate_waveform(
        args.modulation, args.symbols, args.sps, args.beta, args.seed
    )

    # Save to disk
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{args.modulation.lower()}_seed{args.seed}"
    iq_path = output_dir / f"{stem}.cf32"
    metadata_path = output_dir / f"{stem}.json"

    iq.tofile(iq_path)

    metadata = {
        "modulation": args.modulation,
        "symbols": args.symbols,
        "samples": len(iq),
        "samples_per_symbol": args.sps,
        "sample_rate_sps": 2400000,
        "symbol_rate_sps": 2400000 / args.sps,
        "rolloff": args.beta,
        "filter": "root-raised-cosine",
        "filter_taps": len(taps),
        "seed": args.seed,
        "iq_format": "complex64 interleaved float32",
        "average_power": float(np.mean(np.abs(iq) ** 2)),
        "peak_amplitude": float(np.max(np.abs(iq))),
        "iq_file": str(iq_path),
        "rf_transmission_enabled": False,
    }

    metadata_path.write_text(json.dumps(metadata, indent=4))

    print(f"\n===== SOFTWARE TEST COMPLETE =====")
    print(f"  IQ waveform : {iq_path}")
    print(f"  Metadata    : {metadata_path}")
    print(f"  Samples     : {len(iq)}")
    print(f"  Average power: {metadata['average_power']:.6f}")
    print(f"  Peak amplitude: {metadata['peak_amplitude']:.6f}")
    print("  RF output   : DISABLED")


def main():
    """CLI entry point for the hardware test script."""
    parser = argparse.ArgumentParser(
        description="Pluto-to-RTL-SDR Hardware Transmission Test"
    )
    parser.add_argument(
        "--modulation",
        choices=["BPSK", "QPSK", "16QAM"],
        default="BPSK",
        help="Modulation format (default: BPSK)",
    )
    parser.add_argument("--symbols", type=int, default=65536,
                        help="Number of symbols (default: 65536)")
    parser.add_argument("--sps", type=int, default=4,
                        help="Samples per symbol (default: 4)")
    parser.add_argument("--beta", type=float, default=0.35,
                        help="RRC roll-off factor (default: 0.35)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("--output", default="results/baseband/prepared",
                        help="Output directory for software test (default: results/baseband/prepared)")
    parser.add_argument(
        "--frequency",
        type=int,
        default=500_000_000,
        help="TX center frequency in Hz (default: 500 MHz)",
    )
    parser.add_argument(
        "--attenuation",
        type=int,
        default=30,
        help="TX attenuation in dB (default: 30)",
    )
    parser.add_argument(
        "--amplitude-scale",
        type=float,
        default=0.1,
        help="TX amplitude scale (default: 0.1)",
    )
    parser.add_argument(
        "--enable-rf",
        action="store_true",
        help="Enable RF transmission (DEFAULT: disabled for safety)",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run in software-only test mode (no hardware)",
    )

    args = parser.parse_args()

    # RF transmission from this legacy script is disabled (owner decision,
    # 2026-11-23): it used a 500 MHz default, a blocking transmit() that stops
    # TX before the RTL-SDR captures, no band check and no attenuator gate.
    # Physical tests go through scripts/run_hardware_experiment.py.
    if args.enable_rf:
        raise SystemExit(
            "--enable-rf is disabled in this legacy script. Use "
            "scripts/run_hardware_experiment.py --enable-rf --freq <Hz> "
            "--rf-path conducted --attenuator-db <dB> instead."
        )
    set_rf_enabled(False)

    if args.test_mode:
        run_software_test(args)
    elif args.enable_rf:
        print_safety_checklist()
        run_hardware_test(args)
    else:
        run_software_test(args)


if __name__ == "__main__":
    main()
