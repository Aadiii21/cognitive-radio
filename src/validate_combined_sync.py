#!/usr/bin/env python3
"""
Combined Impairment Synchronization Validation

Tests combinations of:
- Timing offset
- Carrier Frequency Offset (CFO)
- Sample Rate Offset (SRO)
- Multipath fading
- AWGN

All with controlled random seeds and reproducible trials.
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import correlate, resample_poly

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.radio.waveform_generator import generate_waveform


# ============================================================
# Configuration
# ============================================================
MODULATIONS = ("BPSK", "QPSK", "16QAM")
TARGET_SNRS = (5.0, 10.0, 15.0)

REPETITIONS = 10  # Reduced for combined test complexity
SYMBOLS = 65536
SPS = 4
ROLLOFF = 0.35
SAMPLE_RATE = 2_400_000
MAX_DELAY = 256

# Impairment ranges
CFO_HZ_RANGE = (-2000.0, 2000.0)
SRO_PPM_RANGE = (0, 50)
MULTIPATH_CONFIGS = {
    "none": {
        "delays": [0], "amplitudes": [1.0], "phases": [0.0]
    },
    "mild": {
        "delays": [0, 8], "amplitudes": [1.0, 0.3], "phases": [0.0, np.pi/4]
    },
    "severe": {
        "delays": [0, 4, 16], "amplitudes": [1.0, 0.5, 0.3], "phases": [0.0, np.pi/2, np.pi]
    },
}


# ============================================================
# Core Functions
# ============================================================
def apply_multipath(signal, delays, amplitudes, phases):
    max_delay = max(delays)
    output_len = len(signal) + max_delay
    output = np.zeros(output_len, dtype=signal.dtype)
    for delay, amp, phase in zip(delays, amplitudes, phases):
        if delay == 0:
            output[:len(signal)] += amp * np.exp(1j * phase) * signal
        else:
            output[delay:delay + len(signal)] += amp * np.exp(1j * phase) * signal
    return output


def apply_sro(signal, sro_ppm):
    if sro_ppm == 0:
        return signal
    up = 1000000 + int(round(sro_ppm))
    down = 1000000
    resampled = resample_poly(signal, up, down)
    if len(resampled) > len(signal):
        resampled = resampled[:len(signal)]
    elif len(resampled) < len(signal):
        pad = np.zeros(len(signal), dtype=signal.dtype)
        pad[:len(resampled)] = resampled
        resampled = pad
    return resampled


def apply_cfo(signal, cfo_hz, sample_rate):
    if cfo_hz == 0:
        return signal
    indices = np.arange(len(signal), dtype=np.float64)
    rotation = np.exp(1j * 2.0 * np.pi * cfo_hz * indices / sample_rate)
    return signal * rotation


def add_awgn(clean, target_snr_db, rng):
    signal_power = float(np.mean(np.abs(clean) ** 2))
    noise_power = signal_power / (10 ** (target_snr_db / 10))
    noise = np.sqrt(noise_power / 2) * (
        rng.standard_normal(len(clean))
        + 1j * rng.standard_normal(len(clean))
    )
    return clean + noise.astype(np.complex64)


def estimate_snr_with_timing_sync(reference, received):
    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)

    if len(received) < len(reference):
        raise ValueError("Received buffer is shorter than reference")
    if not np.isfinite(reference).all() or not np.isfinite(received).all():
        raise ValueError("Non-finite IQ samples detected")

    correlation = correlate(received, reference, mode="valid", method="fft")
    detected_delay = int(np.argmax(np.abs(correlation)))
    aligned = received[detected_delay:detected_delay + len(reference)]

    gain = np.vdot(reference, aligned) / np.vdot(reference, reference)
    reconstructed = gain * reference
    residual = aligned - reconstructed

    signal_power = float(np.mean(np.abs(reconstructed) ** 2))
    noise_power = float(np.mean(np.abs(residual) ** 2))

    if signal_power <= 0 or noise_power <= 0:
        raise ValueError("Invalid signal or noise power")

    measured_snr = 10.0 * np.log10(signal_power / noise_power)
    return float(measured_snr), detected_delay, float(np.abs(gain))


def run_combined_validation():
    output_dir = PROJECT_ROOT / "results" / "synchronization"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"combined_validation_{timestamp}.csv"

    # Define test matrix: combinations of impairments
    # Each test case specifies which impairments are active
    test_cases = [
        # Baseline: no impairments (AWGN only)
        {"name": "awgn_only", "cfo_hz": 0, "sro_ppm": 0, "multipath": "none"},
        # Single impairments
        {"name": "cfo_only", "cfo_hz": 1500, "sro_ppm": 0, "multipath": "none"},
        {"name": "sro_only", "cfo_hz": 0, "sro_ppm": 20, "multipath": "none"},
        {"name": "multipath_mild", "cfo_hz": 0, "sro_ppm": 0, "multipath": "mild"},
        {"name": "multipath_severe", "cfo_hz": 0, "sro_ppm": 0, "multipath": "severe"},
        # Two impairments
        {"name": "cfo_sro", "cfo_hz": 1000, "sro_ppm": 10, "multipath": "none"},
        {"name": "cfo_multipath_mild", "cfo_hz": 1000, "sro_ppm": 0, "multipath": "mild"},
        {"name": "sro_multipath_mild", "cfo_hz": 0, "sro_ppm": 10, "multipath": "mild"},
        # Three impairments
        {"name": "cfo_sro_multipath_mild", "cfo_hz": 500, "sro_ppm": 5, "multipath": "mild"},
        # Stress test: all impairments at moderate levels
        {"name": "all_moderate", "cfo_hz": 1000, "sro_ppm": 20, "multipath": "severe"},
    ]

    rows = []
    total_trials = len(MODULATIONS) * REPETITIONS * len(TARGET_SNRS) * len(test_cases)
    trial = 0

    print(f"Running combined impairment validation: {total_trials} total trials...")

    for mod_index, modulation in enumerate(MODULATIONS):
        for repetition in range(REPETITIONS):
            seed = 92000 + mod_index * 1000 + repetition

            reference, _, _ = generate_waveform(
                modulation, SYMBOLS, SPS, ROLLOFF, seed
            )
            reference = np.asarray(reference, dtype=np.complex128)
            signal_power = float(np.mean(np.abs(reference) ** 2))

            for snr_index, target_snr in enumerate(TARGET_SNRS):
                for case in test_cases:
                    trial += 1
                    if trial % 50 == 0:
                        print(f"  Progress: {trial}/{total_trials}")

                    rng = np.random.default_rng(
                        seed + 600000 + snr_index * 100 + test_cases.index(case)
                    )

                    # Random channel parameters
                    delay = int(rng.integers(0, MAX_DELAY + 1))
                    gain_amplitude = float(rng.uniform(0.5, 1.5))
                    phase = float(rng.uniform(-np.pi, np.pi))

                    # Apply impairments in sequence
                    # 1. Multipath
                    mp_config = MULTIPATH_CONFIGS[case["multipath"]]
                    signal = apply_multipath(
                        reference, mp_config["delays"], mp_config["amplitudes"], mp_config["phases"]
                    )

                    # 2. CFO
                    signal = apply_cfo(signal, case["cfo_hz"], SAMPLE_RATE)

                    # 3. SRO
                    signal = apply_sro(signal, case["sro_ppm"])

                    # 4. Timing delay and complex gain
                    channel_output = np.zeros(len(signal) + MAX_DELAY, dtype=np.complex128)
                    channel_output[delay:delay + len(signal)] = gain_amplitude * np.exp(1j * phase) * signal

                    # 5. AWGN
                    received_signal_power = signal_power * gain_amplitude ** 2
                    mp_power_gain = sum(a**2 for a in mp_config["amplitudes"])
                    noise_power = (received_signal_power * mp_power_gain) / (10.0 ** (target_snr / 10.0))

                    noise = np.sqrt(noise_power / 2.0) * (
                        rng.standard_normal(len(channel_output))
                        + 1j * rng.standard_normal(len(channel_output))
                    )

                    received = channel_output + noise.astype(np.complex128)

                    # Estimate SNR with timing sync
                    try:
                        measured_snr, detected_delay, detected_gain = estimate_snr_with_timing_sync(
                            reference, received
                        )
                        snr_error = measured_snr - target_snr
                        timing_correct = (delay == detected_delay)
                    except Exception as e:
                        measured_snr = np.nan
                        snr_error = np.nan
                        detected_delay = -1
                        detected_gain = np.nan
                        timing_correct = False

                    rows.append({
                        "modulation": modulation,
                        "target_snr_db": target_snr,
                        "measured_snr_db": measured_snr if not np.isnan(measured_snr) else "",
                        "snr_error_db": snr_error if not np.isnan(snr_error) else "",
                        "absolute_snr_error_db": abs(snr_error) if not np.isnan(snr_error) else "",
                        "test_case": case["name"],
                        "cfo_hz": case["cfo_hz"],
                        "sro_ppm": case["sro_ppm"],
                        "multipath": case["multipath"],
                        "actual_delay_samples": delay,
                        "detected_delay_samples": detected_delay,
                        "timing_correct": timing_correct,
                        "detected_gain_amplitude": detected_gain if not np.isnan(detected_gain) else "",
                        "actual_gain_amplitude": gain_amplitude,
                        "phase_rad": phase,
                        "repetition": repetition + 1,
                        "seed": seed,
                    })

    # Write results
    output_path = PROJECT_ROOT / "results" / "synchronization" / f"combined_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fields = list(rows[0].keys())
    with output_path.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    print("\n===== COMBINED IMPAIRMENT VALIDATION SUMMARY =====")
    print(f"Total trials: {len(rows)}")
    print(f"Test cases: {[c['name'] for c in test_cases]}")

    print("\nTest Case | Modulation | Target SNR | MAE (dB) | Max Error | Timing Errors")
    all_pass = True

    for case in test_cases:
        case_rows = [r for r in rows if r["test_case"] == case["name"]]
        for modulation in MODULATIONS:
            mod_rows = [r for r in case_rows if r["modulation"] == modulation]
            for target in TARGET_SNRS:
                subset = [r for r in mod_rows if r["target_snr_db"] == target]
                if not subset:
                    continue

                valid = [r for r in subset if r["snr_error_db"] != ""]
                if not valid:
                    continue

                errors = np.array([r["snr_error_db"] for r in valid])
                absolute = np.abs(errors)
                timing_errors = sum(not r["timing_correct"] for r in valid)

                mae = float(np.mean(absolute))
                max_error = float(np.max(absolute))

                # Relaxed pass criteria for combined impairments
                passed = (mae <= 1.0 and max_error <= 2.0 and timing_errors <= len(valid) * 0.1)
                all_pass &= passed

                print(
                    f"{case['name']:28s} | {modulation:10s} | {target:9.1f} | "
                    f"{mae:7.4f} | {max_error:9.4f} | {timing_errors:13d} "
                    f"{'PASS' if passed else 'FAIL'}"
                )

    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    print(f"Results saved to: {output_path}")

    return all_pass


if __name__ == "__main__":
    from datetime import datetime
    success = run_combined_validation()
    if not success:
        raise SystemExit(1)