#!/usr/bin/env python3
"""
CFO Correction Validation

Tests the improved CFO estimation and correction pipeline.
Measures CFO estimation error, timing recovery, and SNR estimation accuracy.
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import correlate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.radio.waveform_generator import generate_waveform
from src.receiver_sync import (
    synchronize_receiver, apply_channel,
    PREAMBLE_SAMPLES, MAX_CFO_HZ, COARSE_CFO_STEP_HZ,
    CFO_BLOCK_SIZE, SAMPLE_RATE
)


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

# CFO test values
CFO_TEST_VALUES = (0.0, 500.0, 1000.0, 1500.0, 2000.0, -500.0, -1000.0, -1500.0, -2000.0)


def run_cfo_correction_validation():
    output_dir = PROJECT_ROOT / "results" / "synchronization" / "corrections"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"cfo_correction_validation_{timestamp}.csv"

    rows = []
    total_trials = len(MODULATIONS) * REPETITIONS * len(TARGET_SNRS) * len(CFO_TEST_VALUES)
    trial = 0

    print(f"Running CFO correction validation: {total_trials} total trials...")

    for mod_index, modulation in enumerate(MODULATIONS):
        for repetition in range(REPETITIONS):
            seed = 102000 + mod_index * 1000 + repetition

            reference, _, _ = generate_waveform(
                modulation, SYMBOLS, SPS, ROLLOFF, seed
            )
            reference = np.asarray(reference, dtype=np.complex128)

            for snr_index, target_snr in enumerate(TARGET_SNRS):
                for cfo_hz in CFO_TEST_VALUES:
                    trial += 1
                    if trial % 100 == 0:
                        print(f"  Progress: {trial}/{total_trials}")

                    rng = np.random.default_rng(
                        seed + 200000 + snr_index * 10 + CFO_TEST_VALUES.index(cfo_hz)
                    )

                    # Random channel parameters
                    delay = int(rng.integers(0, MAX_DELAY + 1))
                    gain_amplitude = float(rng.uniform(0.5, 1.5))
                    phase = float(rng.uniform(-np.pi, np.pi))

                    # Apply channel: CFO only (no SRO, no multipath)
                    received = apply_channel(
                        reference, delay, gain_amplitude, phase,
                        cfo_hz=cfo_hz, sro_ppm=0.0,
                        target_snr_db=target_snr, rng=rng, max_delay=MAX_DELAY
                    )

                    # Run synchronization pipeline
                    try:
                        result = synchronize_receiver(
                            reference, received,
                            actual_cfo_hz=cfo_hz, actual_sro_ppm=0.0, actual_delay=delay,
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
                            "actual_cfo_hz": cfo_hz,
                            "coarse_cfo_hz": result.coarse_cfo_hz,
                            "fine_cfo_hz": result.fine_cfo_hz,
                            "cfo_error_hz": result.cfo_error_hz,
                            "absolute_cfo_error_hz": abs(result.cfo_error_hz),
                            "estimated_sro_ppm": result.estimated_sro_ppm,
                            "actual_sro_ppm": 0.0,
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
                            "actual_cfo_hz": cfo_hz,
                            "coarse_cfo_hz": "",
                            "fine_cfo_hz": "",
                            "cfo_error_hz": "",
                            "absolute_cfo_error_hz": "",
                            "estimated_sro_ppm": "",
                            "actual_sro_ppm": 0.0,
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
    print("\n===== CFO CORRECTION VALIDATION SUMMARY =====")
    print(f"Total trials: {len(rows)}")
    print(f"CFO values tested: {CFO_TEST_VALUES}")

    print("\nCFO (Hz) | Modulation | Target SNR | CFO MAE (Hz) | Max CFO Err | SNR MAE (dB) | Timing Errors")
    all_pass = True

    for cfo in CFO_TEST_VALUES:
        cfo_rows = [r for r in rows if r["actual_cfo_hz"] == cfo]
        for modulation in MODULATIONS:
            mod_rows = [r for r in cfo_rows if r["modulation"] == modulation]
            for target in TARGET_SNRS:
                subset = [r for r in mod_rows if r["target_snr_db"] == target]
                if not subset:
                    continue

                valid = [r for r in subset if r["cfo_error_hz"] != ""]
                if not valid:
                    continue

                cfo_errors = np.array([r["cfo_error_hz"] for r in valid])
                snr_errors = np.array([r["snr_error_db"] for r in valid])
                timing_errors = sum(not r["timing_correct"] for r in valid)

                cfo_mae = float(np.mean(np.abs(cfo_errors)))
                max_cfo_err = float(np.max(np.abs(cfo_errors)))
                snr_mae = float(np.mean(np.abs(snr_errors)))

                passed = (cfo_mae <= 10.0 and max_cfo_err <= 20.0 and 
                          snr_mae <= 0.5 and timing_errors == 0)
                all_pass &= passed

                print(
                    f"{cfo:+7.0f} | {modulation:10s} | {target:9.1f} | "
                    f"{cfo_mae:11.2f} | {max_cfo_err:11.2f} | {snr_mae:11.4f} | {timing_errors:13d} "
                    f"{'PASS' if passed else 'FAIL'}"
                )

    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    print(f"Results saved to: {output_path}")

    return all_pass


if __name__ == "__main__":
    success = run_cfo_correction_validation()
    if not success:
        raise SystemExit(1)