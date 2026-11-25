#!/usr/bin/env python3
"""
Focused integration tests for the adaptive cognitive radio pipeline.

Tests verify:
1. Receiver measurements change controller decisions
2. Controller decisions change waveform modulation and selected frequency
3. Dwell-time and switching behaviour
4. Hybrid adaptation (modulation + channel simultaneously)

All tests use controlled synthetic measurements. No physical hardware required.
"""

import pytest

import numpy as np

from src.controller_cost_aware import CognitiveController
from src.gnuradio_adapter import GNUradioAdapter, RadioCommand
from src.radio.pluto_tx_adapter import RTLSDRReceiver
from pipelines.integrated_pipeline import AdaptivePipelineState


# ============================================================
# Test: Controller responds to SNR changes
# ============================================================
class TestControllerSNRResponsiveness:
    """Test that the controller changes modulation and channel based on SNR."""

    def test_better_snr_selects_higher_modulation(self):
        """Higher SNR in the current channel should select higher modulation."""
        controller = CognitiveController()
        adapter = GNUradioAdapter(controller=controller)

        # Low SNR => BPSK
        cmd_low = adapter.process([3.0])
        assert cmd_low.modulation == "BPSK"

        # High SNR => 16-QAM
        cmd_high = adapter.process([20.0])
        assert cmd_high.modulation == "16-QAM"

    def test_cross_channel_better_utility_selects_other_channel(self):
        """Better utility on another channel should switch."""
        adapter = GNUradioAdapter()

        # Channel 0: low SNR, Channel 1: high SNR
        cmd = adapter.process([3.0, 20.0])
        assert cmd.channel == 1
        assert cmd.modulation == "16-QAM"

    def test_hold_current_channel_when_no_improvement(self):
        """Controller should not switch channels faster than switch_delay_steps."""
        controller = CognitiveController(initial_channel=0, switch_delay_steps=3)

        # Same SNR on all channels -> no improvement -> stays
        # Note: this tests the controller directly, not the pipeline state
        cmd = controller.decide([10.0, 10.0, 10.0])
        assert cmd.channel == 0
        assert cmd.action == "stay"


# ============================================================
# Test: Integrated pipeline state
# ============================================================
class TestAdaptivePipelineState:
    """Test the integrated pipeline state machine."""

    def test_state_creates_all_components(self):
        """State creates receiver, transmitter, and controller."""
        state = AdaptivePipelineState(
            channel_frequencies=[500e6, 510e6, 520e6],
        )

        assert state.controller is not None
        assert state.adapter is not None
        assert state.receiver is not None
        assert state.transmitter is not None
        assert state.receiver.center_frequencies == [500e6, 510e6, 520e6]

    def test_state_reads_measurements(self):
        """State reads measurements from receiver."""
        state = AdaptivePipelineState(
            channel_frequencies=[500e6, 510e6],
        )

        # Mock the receiver's capture_iq to return synthetic IQ
        # instead of trying to use the rtl_sdr command
        def mock_capture_iq(frequency):
            # Return synthetic noise-like IQ data
            rng = np.random.default_rng(int(frequency) % 1000)
            return (rng.normal(0, 0.1, 2048) + 1j * rng.normal(0, 0.1, 2048)).astype(np.complex64)

        state.receiver.capture_iq = mock_capture_iq
        state.receiver._device_initialized = True

        measurements = state.read_measurements()

        assert len(measurements) == 2
        assert all(isinstance(s, float) for s in measurements)

    def test_state_decides(self):
        """State decision flow works end-to-end."""
        state = AdaptivePipelineState(
            channel_frequencies=[500e6, 510e6],
        )

        # Initialize the receiver (normally done by the pipeline)
        state.receiver._device_initialized = True

        # Mock the receiver to return controlled SNR values
        state.read_measurements = lambda: [15.0, 5.0]

        command = state.decide([15.0, 5.0])

        assert command is not None
        assert command.channel == 0
        # 15 dB SNR above QPSK threshold (8 dB) but below 16-QAM threshold (16 dB)
        # -> QPSK is the best expected delivered data
        assert command.modulation == "QPSK"
        assert command.enabled is True

    def test_state_prepares_waveform(self):
        """State prepares correct waveform for command."""
        state = AdaptivePipelineState(
            channel_frequencies=[500e6],
        )

        command = RadioCommand(
            channel=0,
            modulation="BPSK",
            modulation_index=0,
            enabled=True,
            action="stay",
            estimated_snr=15.0,
            expected_utility=8.0,
        )

        waveform = state.prepare_waveform(command)

        assert waveform is not None
        assert waveform.dtype == np.complex64
        # Waveform should be cached after first use
        assert state._waveform_cache["BPSK"] is not None

    def test_state_configures_transmitter(self):
        """State configures transmitter correctly."""
        state = AdaptivePipelineState(
            channel_frequencies=[500e6, 510e6],
        )

        command = RadioCommand(
            channel=1,
            modulation="QPSK",
            modulation_index=1,
            enabled=True,
            action="stay",
            estimated_snr=10.0,
            expected_utility=6.0,
        )

        config = state.configure_transmitter(command)

        assert config["frequency_hz"] == 510e6
        assert config["modulation"] == "QPSK"
        assert config["channel_index"] == 1
        assert config["command_enabled"] is True

    def test_state_step(self):
        """State step executes full pipeline cycle."""
        state = AdaptivePipelineState(
            channel_frequencies=[500e6],
        )

        # Mock receiver
        state.read_measurements = lambda: [10.0]

        result = state.step()

        assert result["step"] == 1
        assert result["command"] is not None
        assert result["waveform_samples"] > 0
        assert "frequency_hz" in result["transmitter_config"]


# ============================================================
# Test: Dwell-time and switching behaviour
# ============================================================
class TestDwellTimeAndSwitching:
    """Test dwell-time and switching behaviour."""

    def test_switch_delay_prevents_rapid_switching(self):
        """Controller should not switch channels faster than switch_delay_steps."""
        controller = CognitiveController(initial_channel=0, switch_delay_steps=3)

        # Same SNR on all channels -> no improvement -> stays
        for i in range(5):
            cmd = controller.decide([10.0, 10.0])
            assert cmd.channel == 0

    def test_switch_to_better_channel_after_delay(self):
        """Switch to better channel after delay."""
        controller = CognitiveController(initial_channel=0, switch_delay_steps=1)

        # Channel 0 is bad, Channel 1 is good
        cmd = controller.decide([3.0, 20.0])
        assert cmd.channel == 1
        assert cmd.action == "switch_channel"

        # Next decision: still good -> should stay on channel 1
        cmd2 = controller.decide([10.0, 20.0])
        assert cmd2.channel == 1

    def test_switch_only_if_improvement_exceeds_penalty(self):
        """Switch only if improvement exceeds the minimum utility gain."""
        controller = CognitiveController(
            initial_channel=0,
            switch_penalty=0.5,  # Heavy penalty
            min_utility_gain=0.5,
        )

        # Channel 0: 10 dB, Channel 1: 12 dB (slightly better but heavy penalty)
        cmd = controller.decide([10.0, 12.0])
        assert cmd.channel == 0
        assert cmd.action == "stay"


# ============================================================
# Test: Adaptive behaviour
# ============================================================
class TestAdaptiveBehaviour:
    """Test adaptive behaviour with controlled synthetic measurements."""

    def test_modulation_improves_with_snr(self):
        """As SNR increases, modulation should improve from BPSK to QPSK to 16-QAM."""
        adapter = GNUradioAdapter()

        cmd0 = adapter.process([0.0])
        assert cmd0.modulation == "BPSK"

        cmd8 = adapter.process([8.0])
        assert cmd8.modulation == "QPSK"

        cmd16 = adapter.process([16.0])
        assert cmd16.modulation == "16-QAM"

    def test_modulation_deteriorates_with_snr(self):
        """As SNR decreases, modulation should drop to lower-order."""
        adapter = GNUradioAdapter()

        cmd16 = adapter.process([20.0])
        assert cmd16.modulation == "16-QAM"

        cmd4 = adapter.process([4.0])
        assert cmd4.modulation == "BPSK"

        cmd_neg = adapter.process([-5.0])
        assert cmd_neg.enabled is False

    def test_hyper_modulation_selects_highest_available(self):
        """At sufficient SNR, controller selects highest modulation."""
        adapter = GNUradioAdapter()

        cmd = adapter.process([30.0])
        assert cmd.modulation == "16-QAM"
        assert cmd.enabled is True

    def test_channel_switching_with_interference(self):
        """Channel switching when interference increases on current channel."""
        adapter = GNUradioAdapter()

        # Start on channel 0
        cmd = adapter.process([20.0, 3.0])
        assert cmd.channel == 0

        # Channel 0 interference increases, channel 1 is better
        cmd = adapter.process([3.0, 20.0])
        assert cmd.channel == 1


# ============================================================
# Test: Hybrid adaptation (modulation + channel)
# ============================================================
class TestHybridAdaptation:
    """Test hybrid adaptation combining channel and modulation switching."""

    def test_hybrid_decides_channel_and_modulation(self):
        """Hybrid adaptation should produce both channel and modulation commands."""
        adapter = GNUradioAdapter()

        cmd = adapter.process([25.0, 5.0])

        assert cmd.channel == 0
        assert cmd.modulation == "16-QAM"
        assert cmd.enabled is True

    def test_hybrid_switches_channel_and_modulation(self):
        """Channel and modulation both change under differing conditions."""
        adapter = GNUradioAdapter()

        # Initial: strong channel 0, high SNR -> 16-QAM on ch 0
        cmd1 = adapter.process([25.0, 5.0])
        assert cmd1.channel == 0
        assert cmd1.modulation == "16-QAM"

        # Later: channel 0 degrades, channel 1 is strong -> switch to ch 1 + 16-QAM
        cmd2 = adapter.process([3.0, 25.0])
        assert cmd2.channel == 1
        assert cmd2.modulation == "16-QAM"


# ============================================================
# Test: Receiver measurements affect controller
# ============================================================
class TestReceiverFeedingController:
    """Test that receiver measurements feed into controller decisions."""

    def test_receiver_measurements_change_decisions(self):
        """Different SNR measurements should produce different commands."""
        adapter = GNUradioAdapter()

        cmd_low = adapter.process([0.0, 0.0])
        cmd_high = adapter.process([20.0, 20.0])

        assert cmd_low.modulation != cmd_high.modulation

    def test_receiver_channels_affect_channel_selection(self):
        """Per-channel measurements should affect channel selection."""
        adapter = GNUradioAdapter()

        # Best channel is 0
        cmd0 = adapter.process([20.0, 5.0])
        assert cmd0.channel == 0

        # Best channel is 1
        cmd1 = adapter.process([5.0, 20.0])
        assert cmd1.channel == 1

    def test_synthetic_measurements_flow_through_pipeline(self):
        """Synthetic measurements flow through the integrated pipeline."""
        from pipelines.integrated_pipeline import AdaptivePipelineState

        state = AdaptivePipelineState(
            channel_frequencies=[500e6, 510e6],
        )

        # Initialize the receiver (normally done by the pipeline runtime)
        state.receiver._device_initialized = True

        # Mock read_measurements to return controlled values
        state.read_measurements = lambda: [15.0, 5.0]

        # Measure
        snr = state.read_measurements()
        assert len(snr) == 2

        # Decide
        command = state.decide(snr)
        assert command.channel == 0
        assert command.modulation == "QPSK"
        assert command.enabled is True


# ============================================================
# Test: No transmission during tests
# ============================================================
class TestNoTransmissionDuringTests:
    """Ensure no RF transmission occurs during tests."""

    def test_rf_disabled_by_default(self):
        from src.radio.pluto_tx_adapter import RF_ENABLED
        assert RF_ENABLED is False

    def test_set_rf_enabled_changes_state(self):
        import src.radio.pluto_tx_adapter as pta
        assert pta.RF_ENABLED is False
        pta.set_rf_enabled(True)
        assert pta.RF_ENABLED is True
        pta.set_rf_enabled(False)
        assert pta.RF_ENABLED is False

    def test_software_pipeline_does_not_transmit(self):
        """Software pipeline does not transmit."""
        import src.radio.pluto_tx_adapter as pta
        from pipelines.integrated_pipeline import run_software_pipeline

        assert pta.RF_ENABLED is False

        results = run_software_pipeline(
            channel_frequencies=[500e6],
            steps=5,
            seed=42,
            test_mode=True,
        )

        assert len(results["decisions"]) == 5
        # Check that no RF was enabled
        assert pta.RF_ENABLED is False


# ============================================================
# Test: Pipeline integration
# ============================================================
class TestPipelineIntegration:
    """End-to-end integration tests."""

    def test_pipeline_creates_and_closes(self):
        """Pipeline creates and closes cleanly."""
        state = AdaptivePipelineState(
            channel_frequencies=[500e6, 510e6],
            sample_rate=2_400_000,
        )

        # Mock the receiver's capture_iq to return synthetic IQ
        def mock_capture_iq(frequency):
            rng = np.random.default_rng(int(frequency) % 1000)
            return (rng.normal(0, 0.1, 2048) + 1j * rng.normal(0, 0.1, 2048)).astype(np.complex64)

        state.receiver.capture_iq = mock_capture_iq
        state.receiver._device_initialized = True

        # Run a few steps
        for i in range(3):
            result = state.step()
            assert result["step"] == i + 1

        state.close()
        assert state.transmitter._closed is True

    def test_pipeline_decision_log(self):
        """Pipeline decision log is populated."""
        from pipelines.integrated_pipeline import AdaptivePipelineState

        state = AdaptivePipelineState(
            channel_frequencies=[500e6],
        )

        # Mock receiver
        state.read_measurements = lambda: [10.0]

        for i in range(5):
            state.step()

        assert len(state.decision_log) == 5
        assert state.decision_log[0]["step"] == 1
        assert state.decision_log[4]["step"] == 5

    def test_pipeline_waveform_cache(self):
        """Pipeline caches waveforms by modulation."""
        state = AdaptivePipelineState(
            channel_frequencies=[500e6],
        )

        # Use BPSK
        cmd1 = RadioCommand(
            channel=0, modulation="BPSK", modulation_index=0,
            enabled=True, action="stay", estimated_snr=15.0, expected_utility=8.0,
        )
        wf1 = state.prepare_waveform(cmd1)
        assert wf1.dtype == np.complex64

        # Use QPSK
        cmd2 = RadioCommand(
            channel=0, modulation="QPSK", modulation_index=1,
            enabled=True, action="stay", estimated_snr=10.0, expected_utility=6.0,
        )
        wf2 = state.prepare_waveform(cmd2)
        assert wf2.dtype == np.complex64

        # Waveform cache should have both
        assert "BPSK" in state._waveform_cache
        assert "QPSK" in state._waveform_cache


# ============================================================
# Test: Signal detection
# ============================================================
class TestSignalDetection:
    """Test signal detection and SNR estimation."""

    def test_detect_signal_returns_expected_fields(self):
        """Detector returns all expected fields."""
        receiver = RTLSDRReceiver(
            center_frequencies=[500e6],
            sample_rate=256_000,
            capture_samples=1024,
        )

        iq = np.random.randn(1024).astype(np.complex64)
        result = receiver.detect_signal(iq, 500e6)

        assert "detected" in result
        assert "snr_db" in result
        assert "ber" in result
        assert "pdr" in result
        assert "frequency_offset_hz" in result

    def test_detect_signal_ber_between_0_and_1(self):
        """BER is between 0 and 1."""
        receiver = RTLSDRReceiver(
            center_frequencies=[500e6],
            sample_rate=256_000,
            capture_samples=1024,
        )

        iq = np.random.randn(1024).astype(np.complex64)
        result = receiver.detect_signal(iq, 500e6)

        assert 0.0 <= result["ber"] <= 1.0
        assert 0.0 <= result["pdr"] <= 1.0


# ============================================================
# Test: Waveform generation
# ============================================================
class TestWaveformGeneration:
    """Test waveform generation for adaptive pipeline."""

    def test_waveform_generates_correct_modulation(self):
        from src.radio.pluto_tx_adapter import generate_waveform

        iq, symbols, taps = generate_waveform("BPSK", 500, 4, 0.35, 42)
        assert iq.shape == (2000,)
        assert iq.dtype == np.complex64

    def test_waveform_definitions(self):
        from src.radio.pluto_tx_adapter import generate_waveform

        iq, _, _ = generate_waveform("BPSK", 1000, 4, 0.35, 42)
        assert np.mean(np.abs(iq) ** 2) > 0.9

    def test_waveform_consistency(self):
        from src.radio.pluto_tx_adapter import generate_waveform

        iq1, _, _ = generate_waveform("BPSK", 1000, 4, 0.35, 42)
        iq2, _, _ = generate_waveform("BPSK", 1000, 4, 0.35, 42)
        np.testing.assert_array_equal(iq1, iq2)


def test_tx_amplitude_is_scaled_exactly_once():
    """Regression: the pipeline used to pre-scale, then prepare() scaled again."""
    state = AdaptivePipelineState(channel_frequencies=[500e6, 510e6])
    cmd = RadioCommand(channel=0, modulation="QPSK", modulation_index=1, enabled=True,
                       action="stay", estimated_snr=10.0, expected_utility=6.0)
    waveform = state.prepare_waveform(cmd)
    np.testing.assert_allclose(waveform, state._waveform_cache["QPSK"])
    state.transmitter.prepare(waveform)
    scale = state.transmitter.amplitude_scale
    assert np.max(np.abs(state.transmitter._prepared_iq)) == pytest.approx(
        scale * np.max(np.abs(waveform)), rel=1e-6)


def test_pipeline_rf_path_is_disabled():
    """Owner decision 2026-11-23: no RF from the pipeline (hardware closed loop out of scope)."""
    from pipelines.integrated_pipeline import run_hardware_pipeline
    import src.radio.pluto_tx_adapter as pta
    with pytest.raises(ValueError, match="disabled"):
        run_hardware_pipeline(channel_frequencies=[866e6], steps=1, enable_rf=True)
    assert not pta.RF_ENABLED
