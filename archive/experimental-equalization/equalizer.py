#!/usr/bin/env python3
"""
Multipath Equalizer Module

Implements linear equalizers for multipath channel mitigation:
1. No equalization (baseline)
2. Zero-Forcing (ZF) equalizer
3. Linear MMSE equalizer

All equalizers operate at sample rate with fractionally-spaced taps.
"""

import numpy as np
from scipy.signal import lfilter, firwin
from dataclasses import dataclass
from typing import Optional, Tuple
from enum import Enum


class EqualizerType(Enum):
    NONE = "none"
    ZF = "zf"
    MMSE = "mmse"


@dataclass
class EqualizerConfig:
    """Configuration for linear equalizer."""
    equalizer_type: EqualizerType = EqualizerType.NONE
    num_taps: int = 31  # Number of equalizer taps (odd for symmetry)
    oversampling_factor: int = 1  # Fractionally-spaced: 1 = symbol-spaced, 2 = 2x, etc.

    def __post_init__(self):
        if self.num_taps % 2 == 0:
            raise ValueError("Number of taps must be odd for symmetric impulse response")
        if self.num_taps < 3:
            raise ValueError("Number of taps must be at least 3")
        if self.oversampling_factor < 1:
            raise ValueError("Oversampling factor must be >= 1")


@dataclass
class EqualizerResult:
    """Result of equalization."""
    equalized_signal: np.ndarray
    equalizer_taps: np.ndarray
    channel_estimate: np.ndarray
    noise_var_estimate: float
    equalizer_type: EqualizerType
    snr_before_db: float
    snr_after_db: float
    evm_before_percent: float
    evm_after_percent: float
    ber_before: float
    ber_after: float


def estimate_channel_impulse_response(
    reference: np.ndarray,
    received: np.ndarray,
    max_delay: int = 256,
    channel_length: int = 31,
) -> np.ndarray:
    """
    Estimate channel impulse response using cross-correlation and least-squares.

    Uses the known reference signal to estimate the channel taps
    via cross-correlation method (time-domain approach).

    Args:
        reference: Known transmitted signal
        received: Received signal (with multipath)
        max_delay: Maximum timing delay to search
        channel_length: Expected channel impulse response length

    Returns:
        Estimated channel impulse response (length = channel_length), centered at index 0
    """
    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)

    # First, find timing alignment using correlation
    correlation = np.correlate(received, reference, mode='valid')
    detected_delay = int(np.argmax(np.abs(correlation)))

    # Extract aligned portion
    aligned = received[detected_delay:detected_delay + len(reference)]

    if len(aligned) != len(reference):
        raise ValueError("Aligned signal length mismatch")

    # Estimate channel using least-squares in time domain
    # Build convolution matrix from reference
    N = len(reference)
    L = channel_length

    # Build Toeplitz matrix for reference signal
    # Each column is a shifted version of reference
    from scipy.linalg import toeplitz

    # First column: reference with zero-padding for pre-cursor
    # Last row: reference with zero-padding for post-cursor
    first_col = np.zeros(N + L - 1, dtype=np.complex128)
    first_col[:N] = reference
    last_row = np.zeros(L, dtype=np.complex128)
    last_row[0] = reference[0]

    # Build Toeplitz matrix (only need first L columns for channel estimation)
    T = toeplitz(first_col, last_row)[:, :L]  # Shape: (N+L-1, L)

    # But we only have N samples of aligned output, so extract middle N rows
    start_idx = (N + L - 1 - N) // 2  # Center
    T_aligned = T[start_idx:start_idx + N, :]  # Shape: (N, L)

    # Solve least squares: T_aligned * h = aligned
    # Using normal equations with regularization
    reg = 1e-6
    h_est = np.linalg.solve(
        T_aligned.conj().T @ T_aligned + 1e-6 * np.eye(L),
        T_aligned.conj().T @ aligned
    )

    return h_est


def design_zf_equalizer(
    channel_estimate: np.ndarray,
    num_taps: int = 31,
    oversampling_factor: int = 1,
    regularization: float = 1e-6,
) -> np.ndarray:
    """
    Design Zero-Forcing equalizer taps using time-domain least-squares.

    ZF equalizer finds taps w such that w * h ≈ δ (delta function).
    Solves: min_w ||w * h - δ||^2 + reg * ||w||^2

    Args:
        channel_estimate: Estimated channel impulse response (can be centered)
        num_taps: Number of equalizer taps (odd)
        oversampling_factor: Fractionally-spaced factor
        regularization: Small regularization to avoid noise amplification

    Returns:
        Equalizer taps (length = num_taps), centered
    """
    channel_estimate = np.asarray(channel_estimate, dtype=np.complex128)

    # Find the main tap (peak) and shift channel so main tap is at index 0
    peak_idx = np.argmax(np.abs(channel_estimate))
    if peak_idx > 0:
        # Shift channel so peak is at index 0 (causal channel)
        # Use zero-padding instead of circular roll
        shifted = np.zeros_like(channel_estimate)
        if peak_idx < len(channel_estimate):
            shifted[:-peak_idx] = channel_estimate[peak_idx:]
        channel_shifted = shifted
    else:
        channel_shifted = channel_estimate.copy()

    # Truncate/pad to reasonable length
    L_h = min(len(channel_shifted), 64)  # Limit channel length
    h = channel_shifted[:L_h]

    # Build convolution matrix for channel (Toeplitz)
    from scipy.linalg import toeplitz

    L_h = len(h)
    L_w = num_taps

    # Build Toeplitz matrix for channel (so that w * h = delta)
    # First column: channel impulse response with zero padding
    first_col = np.zeros(L_h + L_w - 1, dtype=np.complex128)
    first_col[:L_h] = h
    last_row = np.zeros(L_w, dtype=np.complex128)
    last_row[0] = h[0]

    T = toeplitz(first_col, last_row)  # Shape: (L_h + L_w - 1, L_w)

    # Desired response: delta at center of equalizer output
    # The convolution w * h has length L_h + L_w - 1
    # The equalizer's center tap is at (L_w - 1) // 2
    # The channel's peak is at index 0 (after shifting)
    # So the convolution peak should be at equalizer's center: (L_w - 1) // 2
    desired = np.zeros(L_h + L_w - 1, dtype=np.complex128)
    center = (L_w - 1) // 2
    desired[center] = 1.0

    # Solve regularized least squares: T * w = desired
    reg = regularization
    w = np.linalg.solve(
        T.conj().T @ T + reg * np.eye(num_taps),
        T.conj().T @ desired
    )

    return w  # Keep complex coefficients


def design_mmse_equalizer(
    channel_estimate: np.ndarray,
    noise_variance: float,
    signal_power: float,
    num_taps: int = 31,
    oversampling_factor: int = 1,
) -> np.ndarray:
    """
    Design Linear MMSE equalizer taps.

    MMSE equalizer minimizes E[|s - w^H r|^2]:
    In time domain: min_w E[|s[n] - w^H r[n]|^2]

    Solution: w = R_rr^-1 * r_rs
    where R_rr = E[r r^H] (autocorrelation of received)
          r_rs = E[r s^*] (cross-correlation between received and source)

    For known channel h and noise variance σ²:
    R_rr = h * h^H * P_s + σ² I
    r_rs = h * P_s

    MMSE solution: w = (h * h^H * P_s + σ² I)^-1 * h * P_s

    Args:
        channel_estimate: Estimated channel impulse response
        noise_variance: Estimated noise variance
        signal_power: Estimated signal power
        num_taps: Number of equalizer taps (odd)
        oversampling_factor: Fractionally-spaced factor

    Returns:
        Equalizer taps (length = num_taps)
    """
    channel_estimate = np.asarray(channel_estimate, dtype=np.complex128)
    L_h = len(channel_estimate)
    L_w = num_taps

    # Build autocorrelation matrix of received signal
    # R_rr = h * h^H * P_s + σ² I (in Toeplitz form for convolution)
    from scipy.linalg import toeplitz

    # Autocorrelation of channel
    h = channel_estimate
    r_hh = np.correlate(h, h, mode='full')  # Autocorrelation of channel

    # Build Toeplitz matrix for R_rr
    L_r = L_h + num_taps - 1
    # We only need the central num_taps x num_taps portion

    # Build R_rr = P_s * H * H^H + σ² I
    # where H is the convolution matrix of h
    from scipy.linalg import toeplitz

    # Build convolution matrix H
    L_total = L_h + num_taps - 1
    first_col = np.zeros(L_total, dtype=np.complex128)
    first_col[:len(h)] = h
    last_row = np.zeros(num_taps, dtype=np.complex128)
    last_row[0] = h[0]
    H = toeplitz(first_col, last_row)  # Shape: (L_total, num_taps)

    # R_rr = P_s * H * H^H + σ² I
    P_s = signal_power
    sigma2 = noise_variance

    R_rr = P_s * H @ H.conj().T + sigma2 * np.eye(L_total)

    # Cross-correlation r_rs = P_s * h (padded to L_total)
    r_rs = np.zeros(L_total, dtype=np.complex128)
    start = (L_total - L_h) // 2
    r_rs[start:start+L_h] = P_s * h

    # Solve: R_rr * w = r_rs
    # But we only need the central num_taps taps
    # Extract the central num_taps x num_taps portion of R_rr
    center = L_total // 2
    half = num_taps // 2
    R_sub = R_rr[center-half:center+half+1, center-half:center+half+1]
    r_sub = r_rs[center-half:center+half+1]

    w = np.linalg.solve(R_sub + 1e-6 * np.eye(num_taps), r_sub)

    return w  # Keep complex coefficients


def apply_equalizer(signal: np.ndarray, equalizer_taps: np.ndarray) -> np.ndarray:
    """
    Apply FIR equalizer to signal.

    Args:
        signal: Input signal
        equalizer_taps: Equalizer filter coefficients (centered at 0 delay)

    Returns:
        Equalized signal (same length as input)
    """
    # Use convolution - equalizer_taps is centered at index len(taps)//2
    # We need to compensate for the filter delay
    # mode='full' then extract the correct portion
    full_conv = np.convolve(signal, equalizer_taps, mode='full')

    # The filter has its main tap at center, so it introduces delay of len(taps)//2
    # We need to extract the portion that aligns with the input
    delay = len(equalizer_taps) // 2
    start = delay
    end = start + len(signal)

    if len(full_conv) >= end:
        return full_conv[start:end]
    else:
        # Pad if needed
        padded = np.zeros(len(signal), dtype=signal.dtype)
        available = min(len(full_conv) - delay, len(signal))
        if available > 0:
            padded[:available] = full_conv[delay:delay+available]
        return padded


def compute_ber(reference_symbols: np.ndarray, detected_symbols: np.ndarray) -> float:
    """Compute Bit Error Rate."""
    if len(reference_symbols) != len(detected_symbols):
        raise ValueError("Symbol arrays must have same length")
    errors = np.sum(reference_symbols != detected_symbols)
    return errors / len(reference_symbols)


def compute_evm(reference: np.ndarray, received: np.ndarray) -> float:
    """
    Compute Error Vector Magnitude (EVM) in percent.

    EVM = sqrt(E[|received - ideal|^2] / E[|ideal|^2]) * 100%
    """
    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)

    if len(reference) != len(received):
        raise ValueError("Reference and received must have same length")

    # Estimate channel gain
    gain = np.vdot(reference, received) / np.vdot(reference, reference)
    ideal = gain * reference

    error_vectors = received - ideal
    evm = np.sqrt(
        np.mean(np.abs(error_vectors) ** 2) / np.mean(np.abs(ideal) ** 2)
    )

    return float(evm * 100)  # Percentage


def demodulate_symbols(signal: np.ndarray, modulation: str, sps: int = 4) -> np.ndarray:
    """
    Simple symbol demodulation for BER calculation.

    Performs matched filtering and symbol-rate sampling.
    """
    from scipy.signal import convolve

    # Generate matched filter (RRC)
    from src.radio.waveform_generator import rrc_filter
    rrc_taps = rrc_filter(beta=0.35, sps=sps)

    # Matched filter
    filtered = convolve(signal, rrc_taps, mode='same')

    # Sample at symbol rate (assuming timing is already aligned)
    symbols = filtered[::sps]

    # Decision
    if modulation == "BPSK":
        return np.sign(np.real(symbols)).astype(int)
    elif modulation == "QPSK":
        return (np.sign(np.real(symbols)) + 1j * np.sign(np.imag(symbols))) / np.sqrt(2)
    elif modulation == "16QAM":
        # Simplified 16-QAM decision
        real_levels = np.array([-3, -1, 1, 3])
        imag_levels = np.array([-3, -1, 1, 3])

        real_idx = np.argmin(np.abs(np.real(symbols)[:, None] - real_levels[None, :]), axis=1)
        imag_idx = np.argmin(np.abs(np.imag(symbols)[:, None] - imag_levels[None, :]), axis=1)

        return (real_levels[real_idx] + 1j * imag_levels[imag_idx]) / np.sqrt(10)
    else:
        raise ValueError(f"Unsupported modulation: {modulation}")


def run_equalization_pipeline(
    reference: np.ndarray,
    received: np.ndarray,
    modulation: str,
    config: EqualizerConfig,
    true_channel: Optional[np.ndarray] = None,
    noise_variance: Optional[float] = None,
    signal_power: Optional[float] = None,
) -> EqualizerResult:
    """
    Run complete equalization pipeline.

    Args:
        reference: Known transmitted signal (time-aligned)
        received: Received signal (time-aligned to reference)
        modulation: Modulation type (BPSK, QPSK, 16QAM)
        config: Equalizer configuration
        true_channel: True channel impulse response (for perfect CSI)
        noise_variance: Estimated noise variance (for MMSE)
        signal_power: Estimated signal power (for MMSE)

    Returns:
        EqualizerResult with all metrics
    """
    # Ensure alignment
    if len(reference) != len(received):
        raise ValueError("Reference and received must have same length")

    # Baseline metrics (no equalization)
    snr_before = 10 * np.log10(
        np.mean(np.abs(reference)**2) / np.mean(np.abs(received - reference)**2)
    )
    evm_before = compute_evm(reference, received)

    # Demodulate for BER (using simple decision)
    try:
        ref_symbols = demodulate_symbols(reference, modulation)
        rx_symbols = demodulate_symbols(received, modulation)
        ber_before = compute_ber(ref_symbols, rx_symbols)
    except:
        ber_before = np.nan
        ref_symbols = None

    if config.equalizer_type == EqualizerType.NONE:
        return EqualizerResult(
            equalized_signal=received,
            equalizer_taps=np.array([1.0]),
            channel_estimate=np.array([1.0]),
            noise_var_estimate=0.0,
            equalizer_type=EqualizerType.NONE,
            snr_before_db=snr_before,
            snr_after_db=snr_before,
            evm_before_percent=evm_before,
            evm_after_percent=evm_before,
            ber_before=ber_before,
            ber_after=ber_before,
        )

    # Use true channel if provided, otherwise estimate
    if true_channel is not None:
        channel_estimate = true_channel
    else:
        channel_estimate = estimate_channel_impulse_response(reference, received)

    # Estimate noise variance and signal power if not provided
    if noise_variance is None:
        # Estimate from residual after channel compensation
        residual = received - np.convolve(reference, channel_estimate, mode='same')[:len(reference)]
        noise_variance = float(np.mean(np.abs(residual)**2))

    if signal_power is None:
        signal_power = float(np.mean(np.abs(reference)**2))

    # Design equalizer
    if config.equalizer_type == EqualizerType.ZF:
        equalizer_taps = design_zf_equalizer(
            channel_estimate,
            num_taps=config.num_taps,
            oversampling_factor=config.oversampling_factor,
        )
    elif config.equalizer_type == EqualizerType.MMSE:
        equalizer_taps = design_mmse_equalizer(
            channel_estimate,
            noise_variance=noise_variance,
            signal_power=signal_power,
            num_taps=config.num_taps,
            oversampling_factor=config.oversampling_factor,
        )
    else:
        raise ValueError(f"Unknown equalizer type: {config.equalizer_type}")

    # Apply equalization
    equalized = apply_equalizer(received, equalizer_taps)

    # Post-equalization metrics
    snr_after = 10 * np.log10(
        np.mean(np.abs(reference)**2) / np.mean(np.abs(equalized - reference)**2)
    )
    evm_after = compute_evm(reference, equalized)

    # Post-equalization BER
    if ref_symbols is not None:
        try:
            eq_symbols = demodulate_symbols(equalized, modulation)
            ber_after = compute_ber(ref_symbols, eq_symbols)
        except:
            ber_after = np.nan
    else:
        ber_after = np.nan

    return EqualizerResult(
        equalized_signal=equalized,
        equalizer_taps=equalizer_taps,
        channel_estimate=channel_estimate,
        noise_var_estimate=noise_variance,
        equalizer_type=config.equalizer_type,
        snr_before_db=snr_before,
        snr_after_db=snr_after,
        evm_before_percent=evm_before,
        evm_after_percent=evm_after,
        ber_before=ber_before,
        ber_after=ber_after,
    )


if __name__ == "__main__":
    # Quick test
    import numpy as np
    from src.radio.waveform_generator import generate_waveform
    from src.multipath_channel import MultipathChannelConfig, apply_two_path_channel

    # Generate reference
    ref, symbols, _ = generate_waveform("BPSK", 1000, 4, 0.35, 42)

    # Apply multipath
    config = MultipathChannelConfig(0.5, 4, 0.0)
    mp_signal, _, _ = apply_two_path_channel(ref, config)

    # Add noise
    rng = np.random.default_rng(42)
    noise = 0.1 * (rng.standard_normal(len(mp_signal)) + 1j * rng.standard_normal(len(mp_signal)))
    received = mp_signal + noise

    # Align (simple delay compensation)
    delay = 4
    received_aligned = received[delay:delay+len(ref)]

    # Test equalizers
    for eq_type in [EqualizerType.NONE, EqualizerType.ZF, EqualizerType.MMSE]:
        config = EqualizerConfig(equalizer_type=eq_type, num_taps=31)
        result = run_equalization_pipeline(ref, received_aligned, "BPSK", config)
        print(f"{eq_type.value}: SNR before={result.snr_before_db:.2f}, after={result.snr_after_db:.2f}, "
              f"EVM before={result.evm_before_percent:.2f}%, after={result.evm_after_percent:.2f}%, "
              f"BER before={result.ber_before}, after={result.ber_after}")