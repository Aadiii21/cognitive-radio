#!/usr/bin/env python3
"""
Unit tests for multipath channel model.
"""

import numpy as np
import pytest

from src.multipath_channel import (
    MultipathChannelConfig,
    apply_two_path_channel,
    apply_channel_impairments,
    compute_multipath_metrics,
    ECHO_AMPLITUDES,
    ECHO_DELAYS,
)


class TestMultipathChannelConfig:
    """Tests for MultipathChannelConfig validation."""
    
    def test_valid_config(self):
        config = MultipathChannelConfig(0.3, 4, np.pi/4)
        assert config.echo_amplitude == 0.3
        assert config.echo_delay_samples == 4
        assert config.echo_phase_rad == np.pi/4
    
    def test_zero_amplitude_allowed(self):
        config = MultipathChannelConfig(0.0, 1, 0.0)
        assert config.echo_amplitude == 0.0
    
    def test_negative_amplitude_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            MultipathChannelConfig(-0.1, 1, 0.0)
    
    def test_zero_delay_rejected(self):
        with pytest.raises(ValueError, match="at least 1"):
            MultipathChannelConfig(0.3, 0, 0.0)


class TestApplyTwoPathChannel:
    """Tests for apply_two_path_channel function."""
    
    def test_output_length(self):
        signal = np.ones(100, dtype=np.complex64)
        config = MultipathChannelConfig(0.5, 4, 0.0)
        output, _, _ = apply_two_path_channel(signal, config)
        assert len(output) == len(signal) + 4
    
    def test_direct_path_preserved(self):
        signal = np.ones(100, dtype=np.complex64)
        config = MultipathChannelConfig(0.5, 10, 0.0)
        output, _, _ = apply_two_path_channel(signal, config)
        # First 10 samples: only direct path
        assert np.allclose(output[:10], 1.0)
        # Samples 10-100: direct + echo (1.0 + 0.5 = 1.5)
        assert np.allclose(output[10:100], 1.5)
        # Echo only region (100-110)
        assert np.allclose(output[100:110], 0.5)
    
    def test_echo_phase_applied(self):
        signal = np.ones(100, dtype=np.complex64)
        config = MultipathChannelConfig(1.0, 4, np.pi/2)
        output, _, _ = apply_two_path_channel(signal, config)
        # First 4 samples: only direct path
        assert np.allclose(output[:4], 1.0)
        # Samples 4-100: direct + echo with 90° phase (1 + 1j)
        expected = 1 + 1j
        assert np.allclose(output[4:100], expected)
        # Echo only region (100-104)
        assert np.allclose(output[100:104], 1j)
    
    def test_power_gain_calculation(self):
        signal = np.ones(100, dtype=np.complex64)
        config = MultipathChannelConfig(0.5, 4, 0.0)
        _, mp_gain, _ = apply_two_path_channel(signal, config)
        # 1^2 + 0.5^2 = 1.25
        assert abs(mp_gain - 1.25) < 1e-10
    
    def test_isi_power_ratio(self):
        signal = np.ones(100, dtype=np.complex64)
        config = MultipathChannelConfig(0.5, 4, 0.0)
        _, _, isi_ratio = apply_two_path_channel(signal, config)
        # 0.5^2 / (1 + 0.5^2) = 0.25/1.25 = 0.2
        assert abs(isi_ratio - 0.2) < 1e-10
    
    def test_zero_amplitude_is_awgn_only(self):
        signal = np.ones(100, dtype=np.complex64)
        config = MultipathChannelConfig(0.0, 4, 0.0)
        output, mp_gain, isi_ratio = apply_two_path_channel(signal, config)
        assert mp_gain == 1.0
        assert isi_ratio == 0.0
        assert np.allclose(output[:100], 1.0)


class TestApplyChannelImpairments:
    """Tests for apply_channel_impairments function."""
    
    def test_output_structure(self):
        from src.radio.waveform_generator import generate_waveform
        ref, _, _ = generate_waveform("BPSK", 1000, 4, 0.35, 42)
        config = MultipathChannelConfig(0.3, 4, np.pi/4)
        rng = np.random.default_rng(42)
        
        output = apply_channel_impairments(
            ref, config, delay=10, gain_amplitude=1.0, phase=0.0,
            cfo_hz=0.0, sro_ppm=0.0, target_snr_db=10.0, rng=rng
        )
        
        assert hasattr(output, 'signal')
        assert hasattr(output, 'multipath_power_gain')
        assert hasattr(output, 'isi_power_ratio')
        assert hasattr(output, 'actual_delay')
        assert hasattr(output, 'gain_amplitude')
        assert hasattr(output, 'phase_rad')
        assert hasattr(output, 'noise_power')
        assert hasattr(output, 'target_snr_db')
    
    def test_snr_power_calculation(self):
        from src.radio.waveform_generator import generate_waveform
        ref, _, _ = generate_waveform("BPSK", 1000, 4, 0.35, 42)
        config = MultipathChannelConfig(0.3, 4, 0.0)
        rng = np.random.default_rng(42)
        
        output = apply_channel_impairments(
            ref, config, delay=0, gain_amplitude=1.0, phase=0.0,
            cfo_hz=0.0, sro_ppm=0.0, target_snr_db=10.0, rng=rng
        )
        
        # Verify noise power is reasonable for 10 dB SNR
        ref_power = float(np.mean(np.abs(ref) ** 2))
        expected_noise_power = ref_power / 10.0
        assert abs(output.noise_power - expected_noise_power) / expected_noise_power < 0.01


class TestComputeMultipathMetrics:
    """Tests for compute_multipath_metrics function."""
    
    def test_evm_calculation(self):
        ref = np.ones(100, dtype=np.complex128)
        received = np.zeros(110, dtype=np.complex128)
        received[10:110] = ref  # Perfect alignment at delay 10
        
        config = MultipathChannelConfig(0.3, 4, 0.0)
        metrics = compute_multipath_metrics(ref, received, 10, config)
        
        assert metrics["evm_percent"] == 0.0
    
    def test_evm_with_noise(self):
        ref = np.ones(100, dtype=np.complex128)
        noise = 0.1 * (np.random.randn(100) + 1j * np.random.randn(100))
        received = np.zeros(110, dtype=np.complex128)
        received[10:110] = ref + noise
        
        config = MultipathChannelConfig(0.3, 4, 0.0)
        metrics = compute_multipath_metrics(ref, received, 10, config)
        
        assert metrics["evm_percent"] > 0
        assert metrics["evm_percent"] < 20  # 0.1 noise on unit signal ~ 10% EVM


class TestPredefinedConfigs:
    """Tests for predefined channel configurations."""
    
    def test_echo_amplitudes(self):
        assert ECHO_AMPLITUDES == (0.1, 0.3, 0.5, 0.7)
    
    def test_echo_delays(self):
        assert ECHO_DELAYS == (1, 2, 4, 8, 16)
    
    def test_generate_channel_configs(self):
        from src.multipath_channel import generate_channel_configs
        configs = generate_channel_configs()
        assert len(configs) == 20  # 4 amplitudes * 5 delays
        for amp, delay in configs:
            assert amp in ECHO_AMPLITUDES
            assert delay in ECHO_DELAYS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])