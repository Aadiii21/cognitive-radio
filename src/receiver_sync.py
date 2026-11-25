#!/usr/bin/env python3
"""
Receiver Synchronization Pipeline

Implements a staged synchronization architecture:
1. Coarse CFO estimation (preamble-based)
2. Fine CFO estimation (block-wise phase slope)
3. CFO correction
4. Timing synchronization (correlation-based)
5. SRO estimation and correction (fractional resampling)
6. Reference-based SNR estimation

Designed for BPSK, QPSK, 16-QAM with RRC pulse shaping.
"""

import numpy as np
from scipy.signal import correlate
from scipy.signal import resample_poly
from dataclasses import dataclass
from typing import Optional, Tuple


# ============================================================
# Data Classes
# ============================================================
@dataclass
class SyncResult:
    """Result of synchronization pipeline."""
    timing_correct: bool
    detected_delay: int
    actual_delay: int
    coarse_cfo_hz: float
    fine_cfo_hz: float
    actual_cfo_hz: float
    cfo_error_hz: float
    estimated_sro_ppm: float
    actual_sro_ppm: float
    sro_error_ppm: float
    measured_snr_db: float
    target_snr_db: float
    snr_error_db: float
    gain_amplitude: float
    phase_rad: float


# ============================================================
# Constants
# ============================================================
SAMPLE_RATE = 2_048_000  # RTL-SDR RX sample rate (Hz)
PREAMBLE_SAMPLES = 8192
CFO_BLOCK_SIZE = 256
MAX_CFO_HZ = 5000.0
COARSE_CFO_STEP_HZ = 50.0


# ============================================================
# CFO Estimation
# ============================================================
def estimate_coarse_cfo(preamble, received, max_delay=256, sample_rate=SAMPLE_RATE):
    """
    Coarse CFO estimation using preamble correlation search.
    
    Searches over CFO candidates and finds the one that maximizes
    correlation with the known preamble.
    """
    search_length = len(preamble) + max_delay
    search_buffer = received[:search_length]
    indices = np.arange(search_length, dtype=np.float64)
    
    candidates = np.arange(-MAX_CFO_HZ, MAX_CFO_HZ + COARSE_CFO_STEP_HZ, COARSE_CFO_STEP_HZ)
    
    best_score = -np.inf
    best_delay = None
    best_cfo = 0.0
    
    for candidate in candidates:
        derotation = np.exp(-1j * 2.0 * np.pi * candidate * indices / sample_rate)
        corrected = search_buffer * derotation
        
        correlation = correlate(corrected, preamble, mode="valid", method="fft")
        delay = int(np.argmax(np.abs(correlation)))
        score = float(np.abs(correlation[delay]))
        
        if score > best_score:
            best_score = score
            best_delay = delay
            best_cfo = float(candidate)
    
    return best_delay, best_cfo


def refine_cfo(reference, received, sample_rate=SAMPLE_RATE, block_size=CFO_BLOCK_SIZE):
    """
    Fine CFO estimation from phase slope of block-wise correlations.
    
    Assumes reference and received are aligned in time.
    """
    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)
    
    if reference.shape != received.shape:
        raise ValueError("Reference and received lengths differ")
    
    phases = []
    centers = []
    weights = []
    
    for start in range(0, len(reference) - block_size + 1, block_size):
        end = start + block_size
        ref_block = reference[start:end]
        rx_block = received[start:end]
        
        correlation = np.vdot(ref_block, rx_block)
        if abs(correlation) < 1e-12:
            continue
        
        phases.append(np.angle(correlation))
        centers.append(start + (block_size - 1) / 2.0)
        weights.append(abs(correlation))
    
    if len(phases) < 10:
        raise ValueError("Insufficient correlation blocks for CFO estimation")
    
    phases = np.unwrap(np.asarray(phases))
    centers = np.asarray(centers)
    weights = np.asarray(weights)
    
    # Weighted linear regression: phase = intercept + slope * sample_index
    slope, _ = np.polyfit(centers, phases, 1, w=np.sqrt(weights))
    
    return float(slope * sample_rate / (2.0 * np.pi))


def apply_cfo_correction(signal, cfo_hz, sample_rate=SAMPLE_RATE):
    """Apply CFO correction by derotating the signal."""
    if cfo_hz == 0:
        return signal
    indices = np.arange(len(signal), dtype=np.float64)
    correction = np.exp(-1j * 2.0 * np.pi * cfo_hz * indices / sample_rate)
    return signal * correction


# ============================================================
# Timing Synchronization
# ============================================================
def estimate_timing(reference, received, max_delay=256):
    """
    Correlation-based timing estimation.
    Returns detected delay and aligned received signal.
    """
    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)
    
    if len(received) < len(reference):
        raise ValueError("Received buffer is shorter than reference")
    
    correlation = correlate(received, reference, mode="valid", method="fft")
    detected_delay = int(np.argmax(np.abs(correlation)))
    aligned = received[detected_delay:detected_delay + len(reference)]
    
    return detected_delay, aligned


# ============================================================
# SRO Estimation and Correction
# ============================================================
def estimate_sro_from_timing_drift(reference, received, max_delay=256, 
                                    sample_rate=SAMPLE_RATE, block_size=16384):
    """
    Estimate SRO by measuring timing drift across the signal.
    
    Computes correlation peaks in blocks and fits a line to the
    detected delays vs block index. The slope gives SRO.
    """
    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)
    
    if len(received) < len(reference):
        raise ValueError("Received buffer is shorter than reference")
    
    # Split into blocks and find timing in each
    delays = []
    centers = []
    
    for start in range(0, len(reference) - block_size + 1, block_size):
        end = min(start + block_size, len(reference))
        ref_block = reference[start:end]
        rx_search = received[start:start + block_size + max_delay]
        
        if len(rx_search) < len(ref_block):
            break
        
        correlation = correlate(rx_search, ref_block, mode="valid", method="fft")
        if len(correlation) == 0:
            continue
        
        delay = int(np.argmax(np.abs(correlation)))
        delays.append(delay)
        centers.append(start + (end - start) / 2.0)
    
    if len(delays) < 5:
        return 0.0  # Insufficient blocks
    
    delays = np.asarray(delays, dtype=np.float64)
    centers = np.asarray(centers, dtype=np.float64)
    
    # Linear fit: delay = offset + SRO * sample_index / sample_rate
    # SRO in samples per sample = (delay_slope * sample_rate) / (sample_index_scale)
    # delay_slope is in samples per sample index
    # So SRO in ppm = (delay_slope * sample_rate / sample_index_spacing) * 1e6
    # Actually: delay[i] = delay_0 + SRO * center[i] / 1e6
    # slope = SRO / 1e6
    slope, _ = np.polyfit(centers, delays, 1)
    sro_ppm = slope * 1e6
    
    return float(sro_ppm)


SRO_CORRECTION_MIN_PPM = 1e-3  # below this the correction is a no-op


def apply_sro_correction(signal, sro_ppm, sample_rate=SAMPLE_RATE):
    """
    Correct a sampling-rate offset of `sro_ppm` (as produced by add_sro and
    estimated by estimate_sro_from_timing_drift).

    add_sro models rx[m] = x(m / (1 + eps)), eps = sro_ppm * 1e-6, so the
    correction evaluates rx at t = n * (1 + eps) to recover x[n]. Cubic-spline
    interpolation on the (oversampled) complex baseband; output length is the
    input length, with samples beyond the end of the input set to zero.

    The previous version ignored `sro_ppm` and always resampled by the fixed
    ratio 2083333/2048000 (1.7 %) whenever the estimate was not exactly 0.
    Nominal TX/RX rate conversion is a different operation (see
    src/radio/bpsk_receiver.convert_rate, which uses the actual rates).

    `sample_rate` is accepted for API compatibility; the correction is
    dimensionless.
    """
    from scipy.interpolate import CubicSpline

    signal = np.asarray(signal)
    if abs(sro_ppm) < SRO_CORRECTION_MIN_PPM:
        return signal
    eps = float(sro_ppm) * 1e-6
    n = np.arange(len(signal), dtype=np.float64)
    t = n * (1.0 + eps)
    valid = t <= n[-1]
    out = np.zeros(len(signal), dtype=np.complex128)
    out[valid] = (CubicSpline(n, signal.real)(t[valid])
                  + 1j * CubicSpline(n, signal.imag)(t[valid]))
    return out.astype(signal.dtype if np.iscomplexobj(signal) else np.complex128)


# ============================================================
# SNR Estimation
# ============================================================
def estimate_snr(reference, received):
    """Reference-based SNR estimation after synchronization."""
    gain = np.vdot(reference, received) / np.vdot(reference, reference)
    reconstructed = gain * reference
    residual = received - reconstructed
    
    signal_power = float(np.mean(np.abs(reconstructed) ** 2))
    noise_power = float(np.mean(np.abs(residual) ** 2))
    
    if signal_power <= 0 or noise_power <= 0:
        raise ValueError("Invalid signal or noise power")
    
    return float(10.0 * np.log10(signal_power / noise_power)), float(np.abs(gain))


# ============================================================
# Full Synchronization Pipeline
# ============================================================
def synchronize_receiver(reference, received, 
                          actual_cfo_hz=0.0, actual_sro_ppm=0.0, actual_delay=0,
                          target_snr_db=10.0, max_delay=256, sample_rate=SAMPLE_RATE):
    """
    Complete synchronization pipeline:
    1. Coarse CFO acquisition (joint with timing)
    2. CFO correction on full received signal
    3. SRO estimation on CFO-corrected signal
    4. SRO correction on full CFO-corrected signal
    5. Fine timing sync after SRO correction
    6. Fine CFO estimation on aligned signal
    7. Fine CFO correction (no re-timing needed)
    8. SNR estimation
    """
    # Stage 1: Coarse CFO + timing
    preamble = reference[:PREAMBLE_SAMPLES]
    coarse_delay, coarse_cfo = estimate_coarse_cfo(
        preamble, received, max_delay, sample_rate
    )
    
    # Stage 2: CFO correction on full received signal
    cfo_corrected = apply_cfo_correction(received, coarse_cfo, sample_rate)
    
    # Stage 3: SRO estimation on CFO-corrected signal
    estimated_sro = estimate_sro_from_timing_drift(reference, cfo_corrected, max_delay, sample_rate)
    
    # Stage 4: SRO correction on full CFO-corrected signal
    sro_corrected = apply_sro_correction(cfo_corrected, estimated_sro, sample_rate)
    
    # Stage 5: Fine timing sync after SRO correction
    fine_delay, aligned = estimate_timing(reference, sro_corrected, max_delay)
    
    # Stage 6: Fine CFO estimation on aligned signal
    fine_cfo = refine_cfo(reference, aligned, sample_rate)
    
    # Stage 7: Apply fine CFO correction (no re-timing needed)
    fine_corrected = apply_cfo_correction(aligned, fine_cfo, sample_rate)
    
    # Stage 8: SNR estimation
    measured_snr, gain_amp = estimate_snr(reference, fine_corrected)
    
    return SyncResult(
        timing_correct=(fine_delay == actual_delay),
        detected_delay=fine_delay,
        actual_delay=actual_delay,
        coarse_cfo_hz=coarse_cfo,
        fine_cfo_hz=fine_cfo,
        actual_cfo_hz=actual_cfo_hz,
        cfo_error_hz=(coarse_cfo + fine_cfo) - actual_cfo_hz,
        estimated_sro_ppm=estimated_sro,
        actual_sro_ppm=actual_sro_ppm,
        sro_error_ppm=estimated_sro - actual_sro_ppm,
        measured_snr_db=measured_snr,
        target_snr_db=target_snr_db,
        snr_error_db=measured_snr - target_snr_db,
        gain_amplitude=gain_amp,
        phase_rad=0.0  # Not tracked in this simplified version
    )


# ============================================================
# Utility: Add Impairments
# ============================================================
def add_cfo(signal, cfo_hz, sample_rate=SAMPLE_RATE):
    """Apply CFO to signal."""
    if cfo_hz == 0:
        return signal
    indices = np.arange(len(signal), dtype=np.float64)
    rotation = np.exp(1j * 2.0 * np.pi * cfo_hz * indices / sample_rate)
    return signal * rotation


def add_sro(signal, sro_ppm, sample_rate=SAMPLE_RATE):
    """Apply SRO to signal."""
    if sro_ppm == 0:
        return signal
    up = 1_000_000 + int(round(sro_ppm))
    down = 1_000_000
    resampled = resample_poly(signal, up, down)
    if len(resampled) > len(signal):
        resampled = resampled[:len(signal)]
    elif len(resampled) < len(signal):
        pad = np.zeros(len(signal), dtype=signal.dtype)
        pad[:len(resampled)] = resampled
        resampled = pad
    return resampled


def add_timing_delay(signal, delay, max_delay=256):
    """Add timing delay to signal."""
    output = np.zeros(len(signal) + max_delay, dtype=signal.dtype)
    output[delay:delay + len(signal)] = signal
    return output


def add_awgn(signal, target_snr_db, rng):
    """Add AWGN to achieve target SNR."""
    signal_power = float(np.mean(np.abs(signal) ** 2))
    noise_power = signal_power / (10 ** (target_snr_db / 10))
    noise = np.sqrt(noise_power / 2) * (
        rng.standard_normal(len(signal)) + 1j * rng.standard_normal(len(signal))
    )
    return signal + noise.astype(np.complex128)


def apply_channel(reference, delay, gain_amplitude, phase, cfo_hz, sro_ppm, 
                  target_snr_db, rng, max_delay=256):
    """Apply all channel impairments and noise."""
    # Base signal
    signal = reference.copy()
    
    # Apply CFO
    signal = add_cfo(signal, cfo_hz)
    
    # Apply SRO
    signal = add_sro(signal, sro_ppm)
    
    # Apply complex gain
    signal = gain_amplitude * np.exp(1j * phase) * signal
    
    # Add timing delay
    signal = add_timing_delay(signal, delay, max_delay)
    
    # Add AWGN
    signal_power = float(np.mean(np.abs(reference) ** 2))
    received_signal_power = signal_power * gain_amplitude ** 2
    noise_power = received_signal_power / (10.0 ** (target_snr_db / 10.0))
    noise = np.sqrt(noise_power / 2.0) * (
        rng.standard_normal(len(signal)) + 1j * rng.standard_normal(len(signal))
    )
    
    return signal + noise.astype(np.complex128)