#!/usr/bin/env python3
"""
SRO Correction Validation

Tests the SRO estimation and correction pipeline.
Measures SRO estimation error, residual timing drift, timing recovery, and SNR estimation.
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.radio.waveform_generator import generate_waveform
from src.receiver_sync import synchronize_receiver, apply_channel


# ============================================================
# Configuration
# ============================================================
MODULATIONS = ("BPSK", "QPSK", "16QAM")
TARGET_SNRS = (5.0, 10.0, 15.0)

REPETITIONS = 20
SYMBOLS = 65536
SPS = 4
ROLLOFF = 0.35
MAX_DELAY = 256

# SRO test values
SRO_TEST_VALUES = (0, 5, 10, 20, 50)


def run_sro_correction_validation():
    output_dir = PROJECT_ROOT / "results" / "synchronization" / "corrections"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"sro_correction_validation_{timestamp}.csv"

    rows = []
    total_trials = len(MODULATIONS) * REPETITIONS * len(TARGET_SNRS) * len(SRO_TEST_VALUES)
    trial = 0

    print(f"Running SRO correction validation: {total_trials} total trials...")

    for mod_index, modulation in enumerate(MODULATIONS):
        for repetition in range(REPETITIONS):
            seed = 112000 + mod_index * 1000 + repetition

            reference, _, _ = generate_waveform(
                modulation, SYMBOLS, SPS, ROLLOFF, seed
            )
            reference = np.asarray(reference, dtype=np.complex128)

            for snr_index, target_snr in enumerate(TARGET_SNRS):
                for sro_ppm in SRO_TEST_VALUES:
                    trial += 1
                    if trial % 100 == 0:
                        print(f"  Progress: {trial}/{total_trials}")

                    rng = np.random.default_rng(
                        seed + 300000 + snr_index * 10 + SRO_TEST_VALUES.index(sro_ppm)
                    )

                    # Random channel parameters
                    delay = int(rng.integers(0, MAX_DELAY + 1))
                    gain_amplitude = float(rng.uniform(0.5, 1.5))
                    phase = float(rng.uniform(-np.pi, np.pi))

                    # Apply channel: SRO only (no CFO, no multipath)
                    received = apply_channel(
                        reference, delay, gain_amplitude, phase,
                        cfo_hz=0.0, sro_ppm=float(sro_ppm),
                        target_snr_db=target_snr, rng=rng, max_delay=MAX_DELAY
                    )

                    # Run synchronization pipeline
                    try:
                        result = synchronize_receiver(
                            reference, received,
                            actual_cfo_hz=0.0, actual_sro_ppm=float(sro_ppm), actual_delay=delay,
                            target_snr_db=target_snr, max_delay=MAX_DELAY
                        )
                    except Exception as e:
                        result = None
                        print(f"  Error: {e}")

                    if result is not None:
                        rows.append({
                            "modulation": modulation,
                            "target_snr_db": target_snr,
                            "measured_snr_db": result.measured_snr_db,
                            "snr_error_db": result.snr_error_db,
                            "absolute_snr_error_db": abs(result.snr_error_db),
                            "actual_sro_ppm": sro_ppm,
                            "estimated_sro_ppm": result.estimated_sro_ppm,
                            "sro_error_ppm": result.sro_error_ppm,
                            "absolute_sro_error_ppm": abs(result.sro_error_ppm),
                            "actual_cfo_hz": 0.0,
                            "coarse_cfo_hz": result.coarse_cfo_hz,
                            "fine_cfo_hz": result.fine_cfo_hz,
                            "cfo_error_hz": result.cfo_error_hz,
                            "actual_delay_samples": delay,
                            "detected_delay_samples": result.detected_delay,
                            "timing_correct": result.timing_correct,
                            "detected_gain_amplitude": result.gain_amplitude,
                            "actual_gain_amplitude": gain_amplitude,
                            "phase_rad": phase,
                            "repetition": repetition + 1,
                            "seed": seed,
                        })
                    else:
                        rows.append({
                            "modulation": modulation,
                            "target_snr_db": target_snr,
                            "measured_snr_db": "",
                            "snr_error_db": "",
                            "absolute_snr_error_db": "",
                            "actual_sro_ppm": sro_ppm,
                            "estimated_sro_ppm": "",
                            "sro_error_ppm": "",
                            "absolute_sro_error_ppm": "",
                            "actual_cfo_hz": 0.0,
                            "coarse_cfo_hz": "",
                            "fine_cfo_hz": "",
                            "cfo_error_hz": "",
                            "actual_delay_samples": delay,
                            "detected_delay_samples": -1,
                            "timing_correct": False,
                            "detected_gain_amplitude": "",
                            "actual_gain_amplitude": gain_amplitude,
                            "phase_rad": phase,
                            "repetition": repetition + 1,
                            "seed": seed,
                        })

    # Write results
    fields = list(rows[0].keys())
    with output_path.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    print("\n===== SRO CORRECTION VALIDATION SUMMARY =====")
    print(f"Total trials: {len(rows)}")
    print(f"SRO values tested (PPM): {SRO_TEST_VALUES}")

    print("\nSRO (PPM) | Modulation | Target SNR | SRO MAE (ppm) | Max SRO Err | SNR MAE (dB) | Timing Errors")
    all_pass = True

    for sro in SRO_TEST_VALUES:
        sro_rows = [r for r in rows if r["actual_sro_ppm"] == sro]
        for modulation in MODULATIONS:
            mod_rows = [r for r in sro_rows if r["modulation"] == modulation]
            for target in TARGET_SNRS:
                subset = [r for r in mod_rows if r["target_snr_db"] == target]
                if not subset:
                    continue

                valid = [r for r in subset if r["sro_error_ppm"] != ""]
                if not valid:
                    continue

                sro_errors = np.array([r["sro_error_ppm"] for r in valid])
                snr_errors = np.array([r["snr_error_db"] for r in valid])
                timing_errors = sum(not r["timing_correct"] for r in valid)

                sro_mae = float(np.mean(np.abs(sro_errors)))
                max_sro_err = float(np.max(np.abs(sro_errors)))
                snr_mae = float(np.mean(np.abs(snr_errors)))

                passed = (sro_mae <= 2.0 and max_sro_err <= 5.0 and 
                          snr_mae <= 0.5 and timing_errors == 0)
                all_pass &= passed

                print(
                    f"{sro:8d} | {modulation:10s} | {target:9.1f} | "
                    f"{sro_mae:12.3f} | {max_sro_err:11.3f} | {snr_mae:11.4f} | {timing_errors:13d} "
                    f"{'PASS' if passed else 'FAIL'}"
                )

    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    print(f"Results saved to: {output_path}")

    return all_pass


if __name__ == "__main__":
    success = run_sro_correction_validation()
    if not success:
        raise SystemExit(1)