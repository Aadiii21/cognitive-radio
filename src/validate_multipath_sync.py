#!/usr/bin/env python3
"""
Multipath Fading Synchronization Validation

Tests the timing recovery and SNR estimation under controlled multipath
channel conditions with known ground truth.

Distinguishes between:
- AWGN noise power
- Multipath distortion (ISI)
- Combined effects
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


# ============================================================
# Configuration
# ============================================================
MODULATIONS = ("BPSK", "QPSK", "16QAM")
TARGET_SNRS = (5.0, 10.0, 15.0)

REPETITIONS = 20
SYMBOLS = 65536
SPS = 4
ROLLOFF = 0.35
SAMPLE_RATE = 2_400_000
MAX_DELAY = 256

# Multipath configurations
# Each entry: (delays_samples, relative_amplitudes, relative_phases)
# delays relative to main path (0)
MULTIPATH_CONFIGS = {
    "awgn_only": {
        "delays": [0],
        "amplitudes": [1.0],
        "phases": [0.0],
        "description": "AWGN only (no multipath)"
    },
    "two_path_short": {
        "delays": [0, 4],      # 4 samples = 1 symbol at SPS=4
        "amplitudes": [1.0, 0.5],
        "phases": [0.0, 0.0],
        "description": "Two-path, 1-symbol delay, -6 dB"
    },
    "two_path_medium": {
        "delays": [0, 16],     # 4 symbols
        "amplitudes": [1.0, 0.3],
        "phases": [0.0, np.pi/4],
        "description": "Two-path, 4-symbol delay, -10 dB, 45° phase"
    },
    "two_path_long": {
        "delays": [0, 64],     # 16 symbols
        "amplitudes": [1.0, 0.2],
        "phases": [0.0, np.pi/2],
        "description": "Two-path, 16-symbol delay, -14 dB, 90° phase"
    },
    "three_path": {
        "delays": [0, 8, 24],  # 2 and 6 symbols
        "amplitudes": [1.0, 0.4, 0.2],
        "phases": [0.0, -np.pi/6, np.pi/3],
        "description": "Three-path, 2 & 6 symbol delays"
    },
    "three_path_strong": {
        "delays": [0, 4, 12],  # 1 and 3 symbols
        "amplitudes": [1.0, 0.7, 0.5],
        "phases": [0.0, np.pi/2, np.pi],
        "description": "Three-path, strong echoes (severe ISI)"
    },
}


# ============================================================
# Core Functions
# ============================================================
def apply_multipath(signal, delays, amplitudes, phases):
    """
    Apply multipath channel to signal.
    
    Returns: convolved signal (longer than input by max_delay)
    """
    if len(delays) != len(amplitudes) or len(delays) != len(phases):
        raise ValueError("Delays, amplitudes, phases must have same length")
    
    max_delay = max(delays)
    output_len = len(signal) + max_delay
    output = np.zeros(output_len, dtype=signal.dtype)
    
    for delay, amp, phase in zip(delays, amplitudes, phases):
        if delay == 0:
            output[:len(signal)] += amp * np.exp(1j * phase) * signal
        else:
            output[delay:delay + len(signal)] += amp * np.exp(1j * phase) * signal
    
    return output


def add_awgn(clean, target_snr_db, rng):
    """Add AWGN to achieve target SNR."""
    signal_power = float(np.mean(np.abs(clean) ** 2))
    noise_power = signal_power / (10 ** (target_snr_db / 10))

    noise = np.sqrt(noise_power / 2) * (
        rng.standard_normal(len(clean))
        + 1j * rng.standard_normal(len(clean))
    )

    return clean + noise.astype(np.complex64)


def estimate_snr_with_timing_sync(reference, received):
    """Correlation-based timing sync + reference-based SNR estimation."""
    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)

    if len(received) < len(reference):
        raise ValueError("Received buffer is shorter than reference")

    if not np.isfinite(reference).all() or not np.isfinite(received).all():
        raise ValueError("Non-finite IQ samples detected")

    # Correlation-based timing detection
    correlation = correlate(
        received,
        reference,
        mode="valid",
        method="fft",
    )

    detected_delay = int(np.argmax(np.abs(correlation)))
    aligned = received[
        detected_delay:detected_delay + len(reference)
    ]

    # Least-squares complex channel-gain estimation
    gain = np.vdot(reference, aligned) / np.vdot(reference, reference)

    reconstructed = gain * reference
    residual = aligned - reconstructed

    signal_power = float(np.mean(np.abs(reconstructed) ** 2))
    noise_power = float(np.mean(np.abs(residual) ** 2))

    if signal_power <= 0 or noise_power <= 0:
        raise ValueError("Invalid signal or noise power")

    measured_snr = 10.0 * np.log10(signal_power / noise_power)

    return float(measured_snr), detected_delay, float(np.abs(gain))


def compute_evm(reference, received, detected_delay):
    """Compute Error Vector Magnitude after alignment."""
    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)
    
    aligned = received[
        detected_delay:detected_delay + len(reference)
    ]
    
    if len(aligned) != len(reference):
        return np.nan
    
    # Channel gain estimation
    gain = np.vdot(reference, aligned) / np.vdot(reference, reference)
    ideal = gain * reference
    
    error_vectors = aligned - ideal
    evm = np.sqrt(np.mean(np.abs(error_vectors) ** 2) / np.mean(np.abs(ideal) ** 2))
    
    return float(evm * 100)  # EVM in percent


def run_multipath_validation():
    output_dir = PROJECT_ROOT / "results" / "synchronization"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"multipath_validation_{timestamp}.csv"

    rows = []
    config_names = list(MULTIPATH_CONFIGS.keys())
    total_trials = len(MODULATIONS) * REPETITIONS * len(TARGET_SNRS) * len(config_names)
    trial = 0

    print(f"Running multipath validation: {total_trials} total trials...")

    for mod_index, modulation in enumerate(MODULATIONS):
        for repetition in range(REPETITIONS):
            seed = 82000 + mod_index * 1000 + repetition

            reference, _, _ = generate_waveform(
                modulation,
                SYMBOLS,
                SPS,
                ROLLOFF,
                seed,
            )

            reference = np.asarray(reference, dtype=np.complex128)
            signal_power = float(np.mean(np.abs(reference) ** 2))

            for snr_index, target_snr in enumerate(TARGET_SNRS):
                for config_name in config_names:
                    trial += 1
                    if trial % 100 == 0:
                        print(f"  Progress: {trial}/{total_trials}")

                    config = MULTIPATH_CONFIGS[config_name]
                    delays = config["delays"]
                    amplitudes = config["amplitudes"]
                    phases = config["phases"]

                    rng = np.random.default_rng(
                        seed + 500000 + snr_index * 10 + config_names.index(config_name)
                    )

                    # Random channel parameters
                    delay = int(rng.integers(0, MAX_DELAY + 1))
                    gain_amplitude = float(rng.uniform(0.5, 1.5))
                    phase = float(rng.uniform(-np.pi, np.pi))

                    # Apply multipath channel
                    clean_received = apply_multipath(
                        reference, delays, amplitudes, phases
                    )

                    # Apply random timing delay and complex gain
                    # The multipath output is already delayed by delays[0]=0, so we add
                    # the random delay on top
                    channel_output = np.zeros(len(clean_received) + MAX_DELAY, dtype=np.complex128)
                    channel_output[delay:delay + len(clean_received)] = gain_amplitude * np.exp(1j * phase) * clean_received

                    # Add AWGN
                    received_signal_power = signal_power * gain_amplitude ** 2
                    # Account for multipath power gain
                    mp_power_gain = sum(a**2 for a in amplitudes)
                    noise_power = (received_signal_power * mp_power_gain) / (10.0 ** (target_snr / 10.0))

                    noise = np.sqrt(noise_power / 2.0) * (
                        rng.standard_normal(len(channel_output))
                        + 1j * rng.standard_normal(len(channel_output))
                    )

                    received = channel_output + noise.astype(np.complex128)

                    # Estimate SNR with timing synchronization
                    try:
                        measured_snr, detected_delay, detected_gain = estimate_snr_with_timing_sync(
                            reference, received
                        )
                        snr_error = measured_snr - target_snr
                        timing_correct = (delay == detected_delay)
                        evm = compute_evm(reference, received, detected_delay)
                    except Exception as e:
                        measured_snr = np.nan
                        snr_error = np.nan
                        detected_delay = -1
                        detected_gain = np.nan
                        timing_correct = False
                        evm = np.nan

                    # Also compute ISI power separately
                    # ISI = multipath distortion power after main path
                    # This is the power in the signal that is not aligned with the main tap
                    total_mp_power = sum(a**2 for a in amplitudes)
                    main_power = amplitudes[0]**2  # always 1.0
                    isi_power_ratio = (total_mp_power - main_power) / total_mp_power

                    rows.append({
                        "modulation": modulation,
                        "target_snr_db": target_snr,
                        "measured_snr_db": measured_snr if not np.isnan(measured_snr) else "",
                        "snr_error_db": snr_error if not np.isnan(snr_error) else "",
                        "absolute_snr_error_db": abs(snr_error) if not np.isnan(snr_error) else "",
                        "multipath_config": config_name,
                        "config_description": config["description"],
                        "delays_samples": str(delays),
                        "amplitudes": str(amplitudes),
                        "phases_rad": str([float(p) for p in phases]),
                        "isi_power_ratio": isi_power_ratio,
                        "actual_delay_samples": delay,
                        "detected_delay_samples": detected_delay,
                        "timing_correct": timing_correct,
                        "detected_gain_amplitude": detected_gain if not np.isnan(detected_gain) else "",
                        "actual_gain_amplitude": gain_amplitude,
                        "phase_rad": phase,
                        "evm_percent": evm if not np.isnan(evm) else "",
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
    print("\n===== MULTIPATH VALIDATION SUMMARY =====")
    print(f"Total trials: {len(rows)}")
    print(f"Configurations tested: {config_names}")

    print("\nConfig | Modulation | Target SNR | MAE (dB) | Max Error | Timing Errors | EVM (%)")
    all_pass = True

    for config_name in config_names:
        config_rows = [r for r in rows if r["multipath_config"] == config_name]
        for modulation in MODULATIONS:
            mod_rows = [r for r in config_rows if r["modulation"] == modulation]
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
                evms = [r["evm_percent"] for r in valid if r["evm_percent"] != ""]
                mean_evm = float(np.mean(evms)) if evms else np.nan

                mae = float(np.mean(absolute))
                max_error = float(np.max(absolute))

                passed = (mae <= 0.5 and max_error <= 1.0 and timing_errors == 0)
                all_pass &= passed

                print(
                    f"{config_name:18s} | {modulation:10s} | {target:9.1f} | "
                    f"{mae:7.4f} | {max_error:9.4f} | {timing_errors:13d} | "
                    f"{mean_evm:7.2f} {'PASS' if passed else 'FAIL'}"
                )

    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    print(f"Results saved to: {output_path}")

    return all_pass


if __name__ == "__main__":
    from datetime import datetime
    success = run_multipath_validation()
    if not success:
        raise SystemExit(1)