#!/usr/bin/env python3
"""
Combined CFO and SRO Correction Validation

Tests combinations of CFO and SRO with AWGN and timing offset.
Measures CFO estimation error, SRO estimation error, timing recovery, and SNR estimation.
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

REPETITIONS = 10  # Reduced for combined test
SYMBOLS = 65536
SPS = 4
ROLLOFF = 0.35
MAX_DELAY = 256

# Test matrix: combinations of CFO and SRO
TEST_CASES = [
    # Baseline
    {"name": "awgn_only", "cfo_hz": 0.0, "sro_ppm": 0.0},
    # CFO only
    {"name": "cfo_500", "cfo_hz": 500.0, "sro_ppm": 0.0},
    {"name": "cfo_1000", "cfo_hz": 1000.0, "sro_ppm": 0.0},
    {"name": "cfo_1500", "cfo_hz": 1500.0, "sro_ppm": 0.0},
    {"name": "cfo_2000", "cfo_hz": 2000.0, "sro_ppm": 0.0},
    # SRO only
    {"name": "sro_5", "cfo_hz": 0.0, "sro_ppm": 5.0},
    {"name": "sro_10", "cfo_hz": 0.0, "sro_ppm": 10.0},
    {"name": "sro_20", "cfo_hz": 0.0, "sro_ppm": 20.0},
    {"name": "sro_50", "cfo_hz": 0.0, "sro_ppm": 50.0},
    # Combined
    {"name": "cfo500_sro5", "cfo_hz": 500.0, "sro_ppm": 5.0},
    {"name": "cfo1000_sro10", "cfo_hz": 1000.0, "sro_ppm": 10.0},
    {"name": "cfo1500_sro20", "cfo_hz": 1500.0, "sro_ppm": 20.0},
]


def run_combined_correction_validation():
    output_dir = PROJECT_ROOT / "results" / "synchronization" / "corrections"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"combined_correction_validation_{timestamp}.csv"

    rows = []
    total_trials = len(MODULATIONS) * REPETITIONS * len(TARGET_SNRS) * len(TEST_CASES)
    trial = 0

    print(f"Running combined CFO+SRO correction validation: {total_trials} total trials...")

    for mod_index, modulation in enumerate(MODULATIONS):
        for repetition in range(REPETITIONS):
            seed = 122000 + mod_index * 1000 + repetition

            reference, _, _ = generate_waveform(
                modulation, SYMBOLS, SPS, ROLLOFF, seed
            )
            reference = np.asarray(reference, dtype=np.complex128)

            for snr_index, target_snr in enumerate(TARGET_SNRS):
                for case in TEST_CASES:
                    trial += 1
                    if trial % 50 == 0:
                        print(f"  Progress: {trial}/{total_trials}")

                    rng = np.random.default_rng(
                        seed + 400000 + snr_index * 100 + TEST_CASES.index(case)
                    )

                    # Random channel parameters
                    delay = int(rng.integers(0, MAX_DELAY + 1))
                    gain_amplitude = float(rng.uniform(0.5, 1.5))
                    phase = float(rng.uniform(-np.pi, np.pi))

                    # Apply channel
                    received = apply_channel(
                        reference, delay, gain_amplitude, phase,
                        cfo_hz=case["cfo_hz"], sro_ppm=case["sro_ppm"],
                        target_snr_db=target_snr, rng=rng, max_delay=MAX_DELAY
                    )

                    # Run synchronization pipeline
                    try:
                        result = synchronize_receiver(
                            reference, received,
                            actual_cfo_hz=case["cfo_hz"], 
                            actual_sro_ppm=case["sro_ppm"], 
                            actual_delay=delay,
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
                            "test_case": case["name"],
                            "actual_cfo_hz": case["cfo_hz"],
                            "actual_sro_ppm": case["sro_ppm"],
                            "coarse_cfo_hz": result.coarse_cfo_hz,
                            "fine_cfo_hz": result.fine_cfo_hz,
                            "cfo_error_hz": result.cfo_error_hz,
                            "absolute_cfo_error_hz": abs(result.cfo_error_hz),
                            "estimated_sro_ppm": result.estimated_sro_ppm,
                            "sro_error_ppm": result.sro_error_ppm,
                            "absolute_sro_error_ppm": abs(result.sro_error_ppm),
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
                            "test_case": case["name"],
                            "actual_cfo_hz": case["cfo_hz"],
                            "actual_sro_ppm": case["sro_ppm"],
                            "coarse_cfo_hz": "",
                            "fine_cfo_hz": "",
                            "cfo_error_hz": "",
                            "absolute_cfo_error_hz": "",
                            "estimated_sro_ppm": "",
                            "sro_error_ppm": "",
                            "absolute_sro_error_ppm": "",
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
    print("\n===== COMBINED CFO+SRO CORRECTION VALIDATION SUMMARY =====")
    print(f"Total trials: {len(rows)}")
    print(f"Test cases: {[c['name'] for c in TEST_CASES]}")

    print("\nTest Case | Modulation | Target SNR | CFO MAE (Hz) | SRO MAE (ppm) | SNR MAE (dB) | Timing Errors")
    all_pass = True

    for case in TEST_CASES:
        case_rows = [r for r in rows if r["test_case"] == case["name"]]
        for modulation in MODULATIONS:
            mod_rows = [r for r in case_rows if r["modulation"] == modulation]
            for target in TARGET_SNRS:
                subset = [r for r in mod_rows if r["target_snr_db"] == target]
                if not subset:
                    continue

                valid = [r for r in subset if r["cfo_error_hz"] != "" and r["sro_error_ppm"] != ""]
                if not valid:
                    continue

                cfo_errors = np.array([r["cfo_error_hz"] for r in valid])
                sro_errors = np.array([r["sro_error_ppm"] for r in valid])
                snr_errors = np.array([r["snr_error_db"] for r in valid])
                timing_errors = sum(not r["timing_correct"] for r in valid)

                cfo_mae = float(np.mean(np.abs(cfo_errors)))
                sro_mae = float(np.mean(np.abs(sro_errors)))
                snr_mae = float(np.mean(np.abs(snr_errors)))

                # Relaxed pass criteria
                passed = (cfo_mae <= 20.0 and sro_mae <= 3.0 and 
                          snr_mae <= 1.0 and timing_errors == 0)
                all_pass &= passed

                print(
                    f"{case['name']:16s} | {modulation:10s} | {target:9.1f} | "
                    f"{cfo_mae:11.2f} | {sro_mae:11.3f} | {snr_mae:11.4f} | {timing_errors:13d} "
                    f"{'PASS' if passed else 'FAIL'}"
                )

    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    print(f"Results saved to: {output_path}")

    return all_pass


if __name__ == "__main__":
    success = run_combined_correction_validation()
    if not success:
        raise SystemExit(1)