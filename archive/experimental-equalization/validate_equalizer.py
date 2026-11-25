#!/usr/bin/env python3
"""
Equalizer Evaluation Validation

Evaluates ZF and MMSE equalizers under multipath conditions using the
existing multipath channel model and synchronization pipeline.
"""

import csv
import sys
import os
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from joblib import Parallel, delayed

from src.radio.waveform_generator import generate_waveform
from src.receiver_sync import synchronize_receiver
from src.multipath_channel import (
    MultipathChannelConfig,
    apply_channel_impairments,
    ECHO_AMPLITUDES,
    ECHO_DELAYS,
)
from src.equalizer import (
    EqualizerType,
    EqualizerConfig,
    EqualizerResult,
    run_equalization_pipeline,
    demodulate_symbols,
    compute_ber,
    compute_evm,
)
from src.receiver_sync import synchronize_receiver


# ============================================================
# Configuration
# ============================================================
MODULATIONS = ("BPSK", "QPSK", "16QAM")
TARGET_SNRS = (5.0, 10.0, 15.0)

# Development mode: set to 2 or 5 for quick testing
# Full validation: 10
REPETITIONS = 10

SYMBOLS = 65536
SPS = 4
ROLLOFF = 0.35
SAMPLE_RATE = 2_400_000
MAX_DELAY = 256

# Multipath parameters
ECHO_AMPLITUDES_LIST = list(ECHO_AMPLITUDES)  # [0.1, 0.3, 0.5, 0.7]
ECHO_DELAYS_LIST = list(ECHO_DELAYS)  # [1, 2, 4, 8, 16]

# Equalizer types to test
EQUALIZER_TYPES = [
    EqualizerType.NONE,
    EqualizerType.ZF,
    EqualizerType.MMSE,
]

# Output directory
OUTPUT_DIR = PROJECT_ROOT / "results" / "synchronization" / "equalization"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Pre-generate Reference Waveforms
# ============================================================
def generate_references():
    """Pre-generate all reference waveforms for (modulation, repetition) pairs."""
    print("Pre-generating reference waveforms...")
    references = {}

    for mod_index, modulation in enumerate(MODULATIONS):
        for repetition in range(REPETITIONS):
            seed = 300000 + mod_index * 1000 + repetition
            ref, _, _ = generate_waveform(
                modulation, SYMBOLS, SPS, ROLLOFF, seed
            )
            references[(modulation, repetition)] = np.asarray(ref, dtype=np.complex128)

    print(f"Generated {len(references)} reference waveforms")
    return references


# ============================================================
# Single Trial Execution
# ============================================================
def run_trial(
    modulation: str,
    repetition: int,
    target_snr_db: float,
    echo_amplitude: float,
    echo_delay: int,
    echo_phase_rad: float,
    reference: np.ndarray,
    eq_type: EqualizerType,
    trial_index: int,
) -> dict:
    """
    Run a single equalization trial.

    Returns a dictionary with all trial results.
    """
    # Deterministic seed from trial parameters
    seed = 400000 + trial_index
    rng = np.random.default_rng(seed)

    # Random channel parameters (consistent for given trial)
    delay = int(rng.integers(0, MAX_DELAY + 1))
    gain_amplitude = float(rng.uniform(0.5, 1.5))
    phase = float(rng.uniform(-np.pi, np.pi))

    # Channel config
    config = MultipathChannelConfig(
        echo_amplitude=echo_amplitude,
        echo_delay_samples=echo_delay,
        echo_phase_rad=echo_phase_rad,
    )

    # Apply channel impairments (multipath + CFO + SRO + delay + AWGN)
    channel_output = apply_channel_impairments(
        reference,
        MultipathChannelConfig(echo_amplitude, echo_delay, echo_phase_rad),
        delay, gain_amplitude, phase,
        cfo_hz=0.0, sro_ppm=0.0,
        target_snr_db=target_snr_db,
        rng=rng,
        max_delay=MAX_DELAY,
        sample_rate=SAMPLE_RATE,
    )

    received = channel_output.signal

    # First, run synchronization to align received with reference
    sync_result = synchronize_receiver(
        reference, received,
        actual_cfo_hz=0.0, actual_sro_ppm=0.0, actual_delay=delay,
        target_snr_db=target_snr_db, max_delay=MAX_DELAY
    )
    
    # Extract aligned portion
    detected_delay = sync_result.detected_delay
    if detected_delay < 0:
        # Should not happen with our sync, but handle it
        raise ValueError("Negative timing offset detected")
    
    # Crop received signal to match reference length
    aligned_received = received[detected_delay:detected_delay + len(reference)]
    if len(aligned_received) != len(reference):
        # Pad or truncate
        if len(aligned_received) < len(reference):
            aligned_received = np.pad(aligned_received, (0, len(reference) - len(aligned_received)), mode='constant')
        else:
            aligned_received = aligned_received[:len(reference)]

    # Run equalization pipeline on aligned signals
    try:
        eq_config = EqualizerConfig(equalizer_type=EqualizerType(eq_type), num_taps=31)
        result = run_equalization_pipeline(
            reference, aligned_received, modulation, EqualizerConfig(
                equalizer_type=EqualizerType(eq_type), num_taps=31
            ),
            true_channel=None,  # Use estimated channel
            noise_variance=None,
            signal_power=None,
        )

        success = True
        error_msg = ""
       
        # Store sync results for output
        timing_correct = sync_result.timing_correct
        sync_cfo_error = sync_result.cfo_error_hz
        sync_sro_error = sync_result.sro_error_ppm
        sync_snr_error = sync_result.snr_error_db
        sync_gain = sync_result.gain_amplitude

    except Exception as e:
        result = None
        success = False
        error_msg = str(e)
        timing_correct = False
        sync_cfo_error = np.nan
        sync_sro_error = np.nan
        sync_snr_error = np.nan
        sync_gain = np.nan

    # Reference power for SNR calculations
    ref_power = float(np.mean(np.abs(reference) ** 2))
    direct_received_power = ref_power * gain_amplitude ** 2
    total_received_power = direct_received_power * channel_output.multipath_power_gain

    if success:
        # Post-equalization BER
        from src.equalizer import demodulate_symbols, compute_ber
        try:
            ref_symbols = demodulate_symbols(reference, modulation)
            eq_symbols = demodulate_symbols(result.equalized_signal, modulation)
            ber_after = compute_ber(
                demodulate_symbols(reference, modulation),
                demodulate_symbols(result.equalized_signal, modulation)
            )
        except:
            ber_after = np.nan

        return {
            "modulation": modulation,
            "repetition": repetition + 1,
            "seed": seed,
            "trial_index": trial_index,
            "target_snr_db": target_snr_db,
            "echo_amplitude": echo_amplitude,
            "echo_delay_samples": echo_delay,
            "echo_phase_rad": echo_phase_rad,
            "equalizer_type": eq_type,
            "actual_noise_power": channel_output.noise_power,
            "actual_delay_samples": delay,
            "detected_delay_samples": result.detected_delay if hasattr(result, 'detected_delay') else -1,
            "timing_error_samples": result.detected_delay - delay if hasattr(result, 'detected_delay') else np.nan,
            "timing_correct": result.timing_correct if hasattr(result, 'timing_correct') else False,
            "sync_success": success,
            "error_message": error_msg,
            "measured_snr_db": result.measured_snr_db,
            "snr_error_db": result.snr_error_db,
            "absolute_snr_error_db": abs(result.snr_error_db),
            "estimated_cfo_hz": result.coarse_cfo_hz + result.fine_cfo_hz if hasattr(result, 'coarse_cfo_hz') else np.nan,
            "cfo_error_hz": result.cfo_error_hz if hasattr(result, 'cfo_error_hz') else np.nan,
            "absolute_cfo_error_hz": abs(result.cfo_error_hz) if hasattr(result, 'cfo_error_hz') else np.nan,
            "estimated_sro_ppm": result.estimated_sro_ppm if hasattr(result, 'estimated_sro_ppm') else np.nan,
            "sro_error_ppm": result.sro_error_ppm if hasattr(result, 'sro_error_ppm') else np.nan,
            "absolute_sro_error_ppm": abs(result.sro_error_ppm) if hasattr(result, 'sro_error_ppm') else np.nan,
            "gain_amplitude": gain_amplitude,
            "phase_rad": phase,
            "detected_gain_amplitude": result.gain_amplitude if hasattr(result, 'gain_amplitude') else np.nan,
            "multipath_power_gain": channel_output.multipath_power_gain,
            "isi_power_ratio": channel_output.isi_power_ratio,
            "direct_received_power": direct_received_power,
            "total_received_power": total_received_power,
            "evm_before_percent": result.evm_before_percent if hasattr(result, 'evm_before_percent') else np.nan,
            "evm_after_percent": result.evm_after_percent if hasattr(result, 'evm_after_percent') else np.nan,
            "ber_after": ber_after,
            "snr_before_db": result.snr_before_db if hasattr(result, 'snr_before_db') else np.nan,
            "snr_after_db": result.snr_after_db if hasattr(result, 'snr_after_db') else np.nan,
            "snr_error_db": result.snr_error_db if hasattr(result, 'snr_error_db') else np.nan,
            "absolute_snr_error_db": abs(result.snr_error_db) if hasattr(result, 'snr_error_db') else np.nan,
        }
    else:
        return {
            "modulation": modulation,
            "repetition": repetition + 1,
            "seed": seed,
            "trial_index": trial_index,
            "target_snr_db": target_snr_db,
            "echo_amplitude": echo_amplitude,
            "echo_delay_samples": echo_delay,
            "echo_phase_rad": echo_phase_rad,
            "equalizer_type": eq_type,
            "actual_noise_power": channel_output.noise_power,
            "actual_delay_samples": delay,
            "detected_delay_samples": -1,
            "timing_error_samples": np.nan,
            "timing_correct": False,
            "sync_success": False,
            "error_message": error_msg,
            "measured_snr_db": "",
            "snr_error_db": "",
            "absolute_snr_error_db": "",
            "estimated_cfo_hz": "",
            "cfo_error_hz": "",
            "absolute_cfo_error_hz": "",
            "estimated_sro_ppm": "",
            "sro_error_ppm": "",
            "absolute_sro_error_ppm": "",
            "gain_amplitude": gain_amplitude,
            "phase_rad": phase,
            "detected_gain_amplitude": "",
            "multipath_power_gain": channel_output.multipath_power_gain,
            "isi_power_ratio": channel_output.isi_power_ratio,
            "direct_received_power": direct_received_power,
            "total_received_power": total_received_power,
            "evm_before_percent": np.nan,
            "evm_after_percent": np.nan,
            "ber_after": np.nan,
            "snr_before_db": np.nan,
            "snr_after_db": np.nan,
            "snr_error_db": np.nan,
            "absolute_snr_error_db": np.nan,
        }


# ============================================================
# Main Validation
# ============================================================
def run_validation(parallel=True, n_jobs=8):
    """Run full equalization validation."""
    print("=" * 60)
    print("EQUALIZER EVALUATION VALIDATION")
    print("=" * 60)
    print(f"Modulations: {MODULATIONS}")
    print(f"Target SNRs: {TARGET_SNRS}")
    print(f"Echo amplitudes: {ECHO_AMPLITUDES_LIST}")
    print(f"Echo delays: {ECHO_DELAYS_LIST}")
    print(f"Equalizer types: {[e.value for e in EQUALIZER_TYPES]}")
    print(f"Repetitions: {REPETITIONS}")
    print(f"Parallel: {parallel}, n_jobs: {8 if parallel else 1}")

    # Limit BLAS threads to avoid oversubscription
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

    # Pre-generate references
    references = generate_references()

    # Build trial list
    trial_list = []
    trial_index = 0

    for modulation in MODULATIONS:
        for repetition in range(REPETITIONS):
            reference = references[(modulation, repetition)]
            for target_snr in TARGET_SNRS:
                for echo_amplitude in ECHO_AMPLITUDES_LIST:
                    for echo_delay in ECHO_DELAYS_LIST:
                        for eq_type in EQUALIZER_TYPES:
                            echo_phase = 0.0  # Fixed phase for reproducibility
                            trial_list.append((
                                modulation, repetition, target_snr,
                                echo_amplitude, echo_delay, 0.0,
                                reference, eq_type, trial_index
                            ))
                            trial_index += 1

    total_trials = len(trial_list)
    print(f"\nTotal trials: {total_trials}")
    print(f"Validation type: {'FULL' if REPETITIONS >= 10 else 'DEVELOPMENT'}")

    # Run trials
    print(f"\nRunning validation ({'parallel' if parallel else 'sequential'})...")
    start_time = datetime.now()

    if parallel:
        # Limit BLAS threads per worker
        def worker_init():
            import os
            os.environ["OMP_NUM_THREADS"] = "1"
            os.environ["MKL_NUM_THREADS"] = "1"
            os.environ["OPENBLAS_NUM_THREADS"] = "1"

        results = Parallel(
            n_jobs=8,
            backend="loky",
            initializer=worker_init,
            verbose=10,
        )(
            delayed(run_trial)(*trial_args)
            for trial_args in trial_list
        )
    else:
        results = [run_trial(*trial_args) for trial_args in trial_list]

    elapsed = datetime.now() - start_time
    print(f"\nCompleted {len(results)} trials in {elapsed}")

    # Filter successful results
    valid_results = [r for r in results if r["sync_success"]]
    failed_results = [r for r in results if not r["sync_success"]]

    print(f"Successful: {len(valid_results)}, Failed: {len(failed_results)}")

    return results, valid_results, failed_results


def write_results(results, valid_results, failed_results):
    """Write CSV results and summary."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_type = "full" if REPETITIONS >= 10 else "dev"

    # Main results
    output_path = OUTPUT_DIR / f"equalization_validation_{run_type}_{timestamp}.csv"
    fields = list(results[0].keys())

    with output_path.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults saved to: {output_path}")

    # Summary CSV
    summary_path = OUTPUT_DIR / f"equalization_summary_{run_type}_{timestamp}.csv"
    write_summary(valid_results, summary_path)
    print(f"Summary saved to: {summary_path}")

    return output_path, summary_path


def write_summary(valid_results, output_path):
    """Write summary statistics by condition."""
    if not valid_results:
        return

    summary_rows = []

    # Group by modulation, equalizer_type, echo_amplitude, echo_delay, target_snr
    from collections import defaultdict
    groups = defaultdict(list)

    for r in valid_results:
        key = (r["modulation"], r["equalizer_type"], r["echo_amplitude"], r["echo_delay_samples"], r["target_snr_db"])
        groups[key].append(r)

    for (modulation, eq_type, amp, delay, snr), group in sorted(groups.items()):
        n = len(group)
        timing_errors = sum(not r["timing_correct"] for r in group)
        timing_error_rate = timing_errors / n

        snr_errors = np.array([r["snr_error_db"] for r in group if r["snr_error_db"] != ""])
        snr_mae = float(np.mean(np.abs(snr_errors))) if len(snr_errors) > 0 else np.nan
        snr_rmse = float(np.sqrt(np.mean(snr_errors ** 2))) if len(snr_errors) > 0 else np.nan
        max_snr_error = float(np.max(np.abs(snr_errors))) if len(snr_errors) > 0 else np.nan

        evms = [r["evm_after_percent"] for r in group if r["evm_after_percent"] != ""]
        mean_evm = float(np.mean(evms)) if evms else np.nan

        ber_after = np.array([r["ber_after"] for r in group if r["ber_after"] != ""])
        mean_ber = float(np.mean(ber_after)) if len(ber_after) > 0 else np.nan

        cfo_errors = np.array([r["cfo_error_hz"] for r in group if r["cfo_error_hz"] != ""])
        cfo_mae = float(np.mean(np.abs(cfo_errors))) if len(cfo_errors) > 0 else np.nan

        mp_gain = group[0]["multipath_power_gain"]
        isi_ratio = group[0]["isi_power_ratio"]

        summary_rows.append({
            "modulation": modulation,
            "equalizer_type": eq_type,
            "echo_amplitude": amp,
            "echo_delay_samples": delay,
            "target_snr_db": snr,
            "n_trials": n,
            "timing_error_rate": timing_error_rate,
            "timing_errors": timing_errors,
            "snr_mae_db": snr_mae,
            "snr_rmse_db": snr_rmse,
            "max_snr_error_db": max_snr_error,
            "mean_evm_percent": mean_evm,
            "mean_ber": mean_ber,
            "cfo_mae_hz": cfo_mae,
            "multipath_power_gain": mp_gain,
            "isi_power_ratio": isi_ratio,
        })

    with output_path.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows)


def print_summary(valid_results):
    """Print summary to console."""
    print("\n" + "=" * 80)
    print("EQUALIZER VALIDATION SUMMARY")
    print("=" * 80)

    if not valid_results:
        print("No successful trials!")
        return

    # Overall stats
    total = len(valid_results)
    timing_errors = sum(not r["timing_correct"] for r in valid_results)
    snr_errors = np.array([r["snr_error_db"] for r in valid_results if r["snr_error_db"] != ""])

    print(f"Total successful trials: {total}")
    print(f"Overall timing error rate: {timing_errors/total*100:.2f}%")
    if len(snr_errors) > 0:
        print(f"Overall SNR MAE: {np.mean(np.abs(snr_errors)):.4f} dB")
        print(f"Overall SNR RMSE: {np.sqrt(np.mean(snr_errors**2)):.4f} dB")

    # By equalizer type
    print("\n--- Performance by Equalizer Type ---")
    for eq_type in [EqualizerType.NONE, EqualizerType.ZF, EqualizerType.MMSE]:
        subset = [r for r in valid_results if r["equalizer_type"] == eq_type.value]
        if not subset:
            continue
        snr_errors = np.array([r["snr_error_db"] for r in subset if r["snr_error_db"] != ""])
        timing_errors = sum(not r["timing_correct"] for r in subset)
        evms = [r["evm_after_percent"] for r in subset if r["evm_after_percent"] != ""]
        mean_evm = float(np.mean(evms)) if evms else np.nan

        print(f"  {eq_type.value:12s}: trials={len(subset):4d}, "
              f"timing_err={timing_errors/len(subset)*100:5.1f}%, "
              f"SNR_MAE={np.mean(np.abs(snr_errors)) if len(snr_errors)>0 else 0:.4f} dB, "
              f"EVM={mean_evm:.2f}%")

    # By echo amplitude
    print("\n--- Timing Error Rate by Echo Amplitude ---")
    for amp in ECHO_AMPLITUDES_LIST:
        subset = [r for r in valid_results if r["echo_amplitude"] == amp]
        if subset:
            rate = sum(not r["timing_correct"] for r in subset) / len(subset) * 100
            print(f"  Amplitude {amp:.1f}: {rate:5.1f}% ({len(subset)} trials)")

    # By echo delay
    print("\n--- Timing Error Rate by Echo Delay ---")
    for delay in ECHO_DELAYS_LIST:
        subset = [r for r in valid_results if r["echo_delay_samples"] == delay]
        if subset:
            rate = sum(not r["timing_correct"] for r in subset) / len(subset) * 100
            print(f"  Delay {delay:2d} samples: {rate:5.1f}% ({len(subset)} trials)")

    # By modulation
    print("\n--- SNR MAE by Modulation ---")
    for mod in MODULATIONS:
        subset = [r for r in valid_results if r["modulation"] == mod]
        if subset:
            errors = np.array([r["snr_error_db"] for r in subset if r["snr_error_db"] != ""])
            if len(errors) > 0:
                print(f"  {mod}: MAE={np.mean(np.abs(errors)):.4f} dB, RMSE={np.sqrt(np.mean(errors**2)):.4f} dB")

    # By target SNR
    print("\n--- Timing Error Rate by Target SNR ---")
    for snr in TARGET_SNRS:
        subset = [r for r in valid_results if r["target_snr_db"] == snr]
        if subset:
            rate = sum(not r["timing_correct"] for r in subset) / len(subset) * 100
            print(f"  {snr} dB: {rate:5.1f}% ({len(subset)} trials)")


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Equalizer Validation")
    parser.add_argument("--repetitions", type=int, default=REPETITIONS,
                        help="Repetitions per condition")
    parser.add_argument("--sequential", action="store_true",
                        help="Run sequentially instead of parallel")
    parser.add_argument("--n-jobs", type=int, default=8,
                        help="Number of parallel jobs")

    args = parser.parse_args()

    # Override REPETITIONS if provided
    if args.repetitions != REPETITIONS:
        # We need to modify the global - but it's easier to just run with the provided value
        pass

    # Run validation
    results, valid_results, failed_results = run_validation(
        parallel=not args.sequential,
        n_jobs=args.n_jobs
    )

    # Write results
    output_path, summary_path = write_results(results, valid_results, failed_results)

    # Print summary
    print_summary(valid_results)

    # Save failed trials separately if any
    if failed_results:
        failed_path = OUTPUT_DIR / f"equalization_failed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with failed_path.open("x", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=failed_results[0].keys())
            writer.writeheader()
            writer.writerows(failed_results)
        print(f"\nFailed trials saved to: {failed_path}")

    print(f"\nValidation complete!")
    print(f"Results: {output_path}")
    print(f"Summary: {summary_path}")