#!/usr/bin/env python3
"""
Multipath Channel Model

Implements a two-path channel model for receiver validation:
y[n] = x[n] + a * e^(j*phi) * x[n-d] + w[n]

Parameters:
- Direct path amplitude: 1.0 (normalized)
- Echo amplitude: configurable (0.1, 0.3, 0.5, 0.7)
- Echo delay: configurable in samples (1, 2, 4, 8, 16)
- Echo phase: random per trial
- AWGN: added separately with controlled power

This module is independent of the receiver synchronization pipeline.
"""

import numpy as np
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class MultipathChannelConfig:
    """Configuration for a two-path multipath channel."""
    echo_amplitude: float  # Relative to direct path (1.0)
    echo_delay_samples: int  # Delay in samples
    echo_phase_rad: float  # Phase in radians

    def __post_init__(self):
        if self.echo_amplitude < 0:
            raise ValueError("Echo amplitude must be non-negative")
        if self.echo_delay_samples < 1:
            raise ValueError("Echo delay must be at least 1 sample")


@dataclass
class ChannelOutput:
    """Output from channel simulation."""
    signal: np.ndarray  # Complex signal with multipath + delay + gain
    multipath_power_gain: float  # Sum of squared amplitudes
    isi_power_ratio: float  # Echo power / total power
    actual_delay: int  # Random timing delay applied
    gain_amplitude: float  # Random channel gain
    phase_rad: float  # Random channel phase
    noise_power: float  # AWGN power added
    target_snr_db: float  # Target SNR in dB (referenced to direct path)


def apply_two_path_channel(
    signal: np.ndarray,
    config: MultipathChannelConfig,
) -> Tuple[np.ndarray, float, float]:
    """
    Apply two-path multipath channel to signal.
    
    y[n] = x[n] + a * e^(j*phi) * x[n-d]
    
    Args:
        signal: Input complex signal
        config: Channel configuration
        
    Returns:
        (output_signal, multipath_power_gain, isi_power_ratio)
        - output_signal: Convolved signal (len + echo_delay)
        - multipath_power_gain: Total power gain from multipath (sum a^2)
        - isi_power_ratio: Echo power / total multipath power
    """
    echo_amp = config.echo_amplitude
    echo_delay = config.echo_delay_samples
    echo_phase = config.echo_phase_rad
    
    max_delay = echo_delay
    output_len = len(signal) + max_delay
    output = np.zeros(output_len, dtype=signal.dtype)
    
    # Direct path (delay 0, amplitude 1, phase 0)
    output[:len(signal)] += signal
    
    # Echo path
    if echo_delay == 0:
        output[:len(signal)] += echo_amp * np.exp(1j * echo_phase) * signal
    else:
        output[echo_delay:echo_delay + len(signal)] += echo_amp * np.exp(1j * echo_phase) * signal
    
    # Power calculations
    direct_power = 1.0
    echo_power = echo_amp ** 2
    total_mp_power = direct_power + echo_power
    isi_power_ratio = echo_power / total_mp_power
    
    return output, total_mp_power, isi_power_ratio


def apply_channel_impairments(
    reference: np.ndarray,
    config: MultipathChannelConfig,
    delay: int,
    gain_amplitude: float,
    phase: float,
    cfo_hz: float,
    sro_ppm: float,
    target_snr_db: float,
    rng: np.random.Generator,
    max_delay: int = 256,
    sample_rate: float = 2_400_000,
) -> ChannelOutput:
    """
    Apply all channel impairments to reference signal.
    
    Order: multipath -> CFO -> SRO -> gain/phase -> timing delay -> AWGN
    
    SNR is defined relative to direct path signal power after gain.
    """
    from src.receiver_sync import add_cfo, add_sro, add_timing_delay
    
    # 1. Apply multipath
    mp_signal, mp_power_gain, isi_power_ratio = apply_two_path_channel(
        reference, config
    )
    
    # 2. Apply CFO
    signal = add_cfo(mp_signal, cfo_hz, sample_rate)
    
    # 3. Apply SRO
    signal = add_sro(signal, sro_ppm, sample_rate)
    
    # 4. Apply complex gain
    signal = gain_amplitude * np.exp(1j * phase) * signal
    
    # 5. Add timing delay
    signal = add_timing_delay(signal, delay, max_delay)
    
    # 6. Add AWGN
    # SNR is referenced to direct path power after gain
    ref_power = float(np.mean(np.abs(reference) ** 2))
    direct_received_power = ref_power * gain_amplitude ** 2
    
    # Total received power includes multipath
    total_received_power = direct_received_power * mp_power_gain
    
    # Noise power to achieve target SNR on direct path
    noise_power = direct_received_power / (10.0 ** (target_snr_db / 10.0))
    
    noise = np.sqrt(noise_power / 2.0) * (
        rng.standard_normal(len(signal)) + 1j * rng.standard_normal(len(signal))
    )
    
    received = signal + noise.astype(np.complex128)
    
    return ChannelOutput(
        signal=received,
        multipath_power_gain=mp_power_gain,
        isi_power_ratio=isi_power_ratio,
        actual_delay=delay,
        gain_amplitude=gain_amplitude,
        phase_rad=phase,
        noise_power=noise_power,
        target_snr_db=target_snr_db,
    )


def compute_multipath_metrics(
    reference: np.ndarray,
    received: np.ndarray,
    detected_delay: int,
    config: MultipathChannelConfig,
) -> dict:
    """
    Compute multipath-specific metrics.
    
    Returns dict with:
    - evm_percent: Error vector magnitude
    - isi_power_estimate: Estimated ISI power from residual
    """
    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)
    
    aligned = received[detected_delay:detected_delay + len(reference)]
    
    if len(aligned) != len(reference):
        return {"evm_percent": np.nan, "isi_power_estimate": np.nan}
    
    # Channel gain estimation
    gain = np.vdot(reference, aligned) / np.vdot(reference, reference)
    ideal = gain * reference
    
    # EVM
    error_vectors = aligned - ideal
    evm = np.sqrt(
        np.mean(np.abs(error_vectors) ** 2) / np.mean(np.abs(ideal) ** 2)
    )
    
    # ISI power estimate: residual after subtracting ideal single-path signal
    # This includes both noise and ISI
    residual_power = float(np.mean(np.abs(error_vectors) ** 2))
    
    return {
        "evm_percent": float(evm * 100),
        "residual_power": residual_power,
    }


# Predefined channel configurations for validation
ECHO_AMPLITUDES = (0.1, 0.3, 0.5, 0.7)
ECHO_DELAYS = (1, 2, 4, 8, 16)

def generate_channel_configs() -> list:
    """Generate all combinations of echo amplitude and delay with random phases."""
    configs = []
    for amp in ECHO_AMPLITUDES:
        for delay in ECHO_DELAYS:
            configs.append((amp, delay))
    return configs


if __name__ == "__main__":
    # Quick test
    from src.radio.waveform_generator import generate_waveform
    import numpy as np
    
    ref, _, _ = generate_waveform("BPSK", 1000, 4, 0.35, 42)
    config = MultipathChannelConfig(0.3, 4, np.pi/4)
    
    out, mp_gain, isi_ratio = apply_two_path_channel(ref, config)
    print(f"Input len: {len(ref)}, Output len: {len(out)}")
    print(f"MP gain: {mp_gain:.4f}, ISI ratio: {isi_ratio:.4f}")
    
    # Test channel output
    rng = np.random.default_rng(42)
    ch_out = apply_channel_impairments(
        ref, config, delay=10, gain_amplitude=1.0, phase=0.0,
        cfo_hz=0.0, sro_ppm=0.0, target_snr_db=10.0, rng=rng
    )
    print(f"Channel output len: {len(ch_out.signal)}")
    print(f"MP gain: {ch_out.multipath_power_gain:.4f}")
    print(f"ISI ratio: {ch_out.isi_power_ratio:.4f}")
    print(f"Noise power: {ch_out.noise_power:.6f}")