#!/usr/bin/env python3
"""
Integrated Cognitive Radio Pipeline Entry Point

Ties together:
- RTL-SDR receiver (RTLSDRReceiver) for channel sensing
- Cognitive controller (CognitiveController) for decision making
- GNU Radio adapter (GNUradioAdapter) for command mapping
- Pluto TX adapter (PlutoTXAdapter) for waveform generation and transmission

Pipeline:
  RTL-SDR capture -> SNR measurements -> CognitiveController.decide() ->
  GNUradioAdapter.process() -> RadioCommand -> PlutoTXAdapter.configure() +
  PlutoTXAdapter.prepare() + PlutoTXAdapter.transmit()

RF transmission remains disabled by default. Hardware operation requires
explicit --enable-rf operator authorization.

Usage:
    python pipelines/integrated_pipeline.py --channels "500e6 510e6 520e6" \
        --steps 10 --modulation-bpsk --seed 42

    # Software-only test (no RF)
    python pipelines/integrated_pipeline.py --channels "500e6 510e6 520e6" \
        --steps 10 --seed 42 --test-mode

    # Hardware mode (operator action required)
    python pipelines/integrated_pipeline.py --channels "500e6 510e6 520e6" \
        --steps 10 --modulation-bpsk --enable-rf
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from src.radio.hardware_config import PLUTO_URI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Import the existing project components
from src.radio.pluto_tx_adapter import (
    PlutoTXAdapter,
    RTLSDRReceiver,
    set_rf_enabled,
    generate_waveform,
)
from src.controller_cost_aware import CognitiveController
from src.gnuradio_adapter import GNUradioAdapter, RadioCommand


# ============================================================
# Pipeline State
# ============================================================
class AdaptivePipelineState:
    """
    Maintains pipeline state across decision cycles.

    Attributes:
        controller: CognitiveController instance
        adapter: GNUradioAdapter for command mapping
        receiver: RTLSDRReceiver for channel sensing
        transmitter: PlutoTXAdapter for waveform and TX configuration
        channel_frequencies: List of channel center frequencies in Hz
        waveform_cache: Cached waveforms per modulation
        dwell_timer: Steps remaining before next channel switch
        decision_log: Per-decision trace
    """

    def __init__(
        self,
        channel_frequencies: list[float],
        controller: Optional[CognitiveController] = None,
        adapter: Optional[GNUradioAdapter] = None,
        sample_rate: int = 2_400_000,
        amplitude_scale: float = 0.1,
    ):
        self.channel_frequencies = [float(f) for f in channel_frequencies]

        self.controller = controller or CognitiveController()
        self.adapter = adapter or GNUradioAdapter(controller=self.controller)

        self.receiver = RTLSDRReceiver(
            center_frequencies=self.channel_frequencies,
            sample_rate=256_000,
            capture_samples=2048,
        )

        self.transmitter = PlutoTXAdapter(
            uri=PLUTO_URI,
            sample_rate=sample_rate,
            bandwidth=1_000_000,
            amplitude_scale=amplitude_scale,
        )

        self.dwell_timer = 0
        self.step_count = 0
        self.decision_log: list[dict] = []

        # Pre-generate waveforms for all modulations
        self._waveform_cache: dict[str, np.ndarray] = {}
        for mod in ["BPSK", "QPSK", "16QAM"]:
            iq, _, _ = generate_waveform(mod, 1000, 4, 0.35, 42)
            self._waveform_cache[mod] = iq

    def read_measurements(self) -> list[float]:
        """
        Read SNR measurements from the RTL-SDR receiver.

        Returns:
            List of channel SNR values in dB
        """
        measurements = []
        for frequency in self.channel_frequencies:
            measurement = self.receiver.measure(frequency)
            measurements.append(measurement["snr_db"])
        return measurements

    def decide(self, snr_values: list[float]) -> RadioCommand:
        """
        Run the controller decision with the given SNR measurements.

        Applies dwell-time logic: the controller cannot switch channels
        more frequently than switch_delay_steps.

        Returns:
            RadioCommand with channel, modulation, enabled state
        """
        self.step_count += 1

        # Apply dwell timer: if a switch was already announced, hold current config
        if self.dwell_timer > 0:
            self.dwell_timer -= 1
            # Hold: use current channel's SNR for decision
            snr_values = [
                snr_values[self.controller.current_channel]
            ]

        command = self.adapter.process(snr_values)

        # Log decision
        self.decision_log.append({
            "step": self.step_count,
            "snr_values_hz": [round(s, 3) for s in snr_values],
            "command_channel": command.channel,
            "command_modulation": command.modulation,
            "command_enabled": command.enabled,
            "command_action": command.action,
            "dwell_timer_remaining": self.dwell_timer,
            "timestamp": datetime.now().isoformat(),
        })

        return command

    def prepare_waveform(self, command: RadioCommand) -> np.ndarray:
        """
        Prepare the waveform for the given command.

        Args:
            command: RadioCommand from controller

        Returns:
            Complex64 IQ waveform, NOT amplitude-scaled.

        TX amplitude scaling is owned by PlutoTXAdapter.prepare(), which
        applies self.transmitter.amplitude_scale exactly once. Scaling here as
        well (as before 2026-11-23) made the transmitted level
        amplitude_scale**2, i.e. 0.01 instead of 0.1 (-40 dBFS, not -20).
        """
        modulation = command.modulation
        if modulation not in self._waveform_cache:
            iq, _, _ = generate_waveform(modulation, 1000, 4, 0.35, 42)
            self._waveform_cache[modulation] = iq

        return self._waveform_cache[modulation].copy()

    def configure_transmitter(self, command: RadioCommand) -> dict:
        """
        Configure the transmitter for the given command.

        Args:
            command: RadioCommand with channel and modulation

        Returns:
            Configuration dict
        """
        return {
            "frequency_hz": self.channel_frequencies[command.channel],
            "modulation": command.modulation,
            "channel_index": command.channel,
            "command_enabled": command.enabled,
        }

    def step(self) -> dict:
        """
        Execute one pipeline step.

        Returns:
            Dictionary with step results
        """
        # Read measurements
        snr_measurements = self.read_measurements()

        # Decide
        command = self.decide(snr_measurements)

        # Prepare waveform
        waveform = self.prepare_waveform(command)

        # Configure transmitter
        config = self.configure_transmitter(command)

        return {
            "step": self.step_count,
            "snr_measurements": snr_measurements,
            "command": command,
            "waveform_samples": len(waveform),
            "transmitter_config": config,
        }

    def close(self):
        """Release all pipeline resources."""
        self.transmitter.close()
        self.receiver.cleanup()


# ============================================================
# Software-Only Pipeline Runner
# ============================================================
def run_software_pipeline(
    channel_frequencies: list[float],
    steps: int,
    seed: int = 42,
    test_mode: bool = False,
) -> dict:
    """
    Run the pipeline in software-only mode.

    This does NOT transmit RF. It only simulates the closed-loop
    decision process using synthetic measurements.

    Args:
        channel_frequencies: List of channel center frequencies
        steps: Number of decision cycles
        seed: Random seed for reproducible measurements
        test_mode: If True, no hardware operations performed

    Returns:
        Complete pipeline results
    """
    rng = np.random.default_rng(seed)

    # Create pipeline state
    state = AdaptivePipelineState(
        channel_frequencies=channel_frequencies,
        sample_rate=2_400_000,
        amplitude_scale=0.1,
    )

    # Collect results
    results = {
        "timestamp": datetime.now().isoformat(),
        "steps": steps,
        "channels_hz": channel_frequencies,
        "decisions": [],
        "measurements": [],
        "configs": [],
    }

    for i in range(steps):
        # Generate synthetic SNR based on random walk
        base_snr = rng.uniform(0, 20)
        drift = 0.1 * (rng.random() - 0.5)
        snr = base_snr + drift

        # Simulate per-channel measurements (simplified model)
        measurements = [max(snr - rng.uniform(0, 2), -10) for _ in channel_frequencies]

        # Decide
        decision = state.decide(measurements)

        # Store
        results["decisions"].append({
            "step": i,
            "measurements": measurements,
            "command": {
                "channel": decision.channel,
                "modulation": decision.modulation,
                "enabled": decision.enabled,
                "action": decision.action,
            },
        })

        results["measurements"].append(measurements)
        results["configs"].append({
            "frequency_hz": channel_frequencies[decision.channel],
            "modulation": decision.modulation,
            "enabled": decision.enabled,
        })

    state.close()

    return results


# ============================================================
# Hardware Pipeline Runner
# ============================================================
PIPELINE_RF_DISABLED_MESSAGE = (
    "integrated_pipeline RF transmission is disabled: a hardware closed loop is out of "
    "project scope (owner decision, 2026-11-23). Use scripts/run_hardware_experiment.py "
    "--enable-rf --freq <Hz> --rf-path conducted --attenuator-db <dB> for physical tests."
)

def run_hardware_pipeline(
    channel_frequencies: list[float],
    steps: int,
    seed: int = 42,
    enable_rf: bool = False,
) -> dict:
    """
    Run the pipeline with actual hardware.

    Requires:
    - Physical RTL-SDR device connected
    - Physical Pluto SDR connected
    - Safe conducted RF path
    - Regulatory authorization for transmission frequency

    Args:
        channel_frequencies: List of channel center frequencies
        steps: Number of decision cycles
        seed: Random seed for reproducible measurements
        enable_rf: If True, enable RF transmission (operator authorized)

    Returns:
        Complete pipeline results
    """
    # RF transmission from the pipeline is disabled (owner decision,
    # 2026-11-23); a hardware closed loop is out of project scope. It
    # used blocking transmit() (TX stops before RX), unframed waveforms and
    # RTLSDRReceiver.detect_signal(), whose "SNR" always reports detected.
    # Physical tests: scripts/run_hardware_experiment.py.
    if enable_rf:
        raise ValueError(PIPELINE_RF_DISABLED_MESSAGE)
    set_rf_enabled(False)
    if not enable_rf:
        print("=" * 60)
        print("  ADAPTIVE PIPELINE - SOFTWARE MODE")
        print("=" * 60)
        print("  RF TRANSMISSION: DISABLED")
        print("  Use --enable-rf to enable transmission (requires operator)")
        print("=" * 60)
        # Run software simulation only
        return run_software_pipeline(
            channel_frequencies=channel_frequencies,
            steps=steps,
            seed=seed,
        )

    print("=" * 60)
    print("  ADAPTIVE PIPELINE - RADIO MODE")
    print("=" * 60)
    channels_mhz = [f / 1e6 for f in channel_frequencies]
    print(f"  Channels: {' '.join(f'{c:.3f}' for c in channels_mhz)} MHz")
    print(f"  Steps   : {steps}")
    print(f"  RF enabled: YES (operator-authorized)")
    print("=" * 60)

    rng = np.random.default_rng(seed)

    # Setup pipeline
    state = AdaptivePipelineState(
        channel_frequencies=channel_frequencies,
        sample_rate=2_400_000,
        amplitude_scale=0.1,
    )

    results = {
        "timestamp": datetime.now().isoformat(),
        "steps": steps,
        "channels_hz": channel_frequencies,
        "decisions": [],
        "measurements": [],
        "configs": [],
    }

    for i in range(steps):
        # Read actual measurements
        snr_measurements = state.read_measurements()

        # Decide
        decision = state.decide(snr_measurements)

        # Prepare waveform
        waveform = state.prepare_waveform(decision)

        # Configure transmitter
        config = state.configure_transmitter(decision)

        # Store
        results["decisions"].append({
            "step": i,
            "measurements": snr_measurements,
            "command": {
                "channel": decision.channel,
                "modulation": decision.modulation,
                "enabled": decision.enabled,
                "action": decision.action,
            },
        })

        results["measurements"].append(snr_measurements)
        results["configs"].append({
            "frequency_hz": config["frequency_hz"],
            "modulation": config["modulation"],
            "enabled": config["command_enabled"],
        })

        # Transmit (this is the RF hardware path)
        if decision.enabled:
            state.transmitter.prepare(waveform)
            tx_result = state.transmitter.transmit()
            print(f"  Step {i}: TX={decision.modulation} ch={decision.channel} "
                  f"SNR={snr_measurements[decision.channel]:.2f}dB")
        else:
            print(f"  Step {i}: Hold ch={decision.channel} "
                  f"SNR={snr_measurements[decision.channel]:.2f}dB")

    state.close()
    return results


# ============================================================
# Entry Point
# ============================================================
def main():
    """Command-line entry point for the adaptive pipeline."""
    parser = argparse.ArgumentParser(
        description="Integrated Cognitive Radio Pipeline"
    )
    parser.add_argument(
        "--channels",
        type=float,
        nargs="+",
        required=True,
        help="Channel center frequencies in Hz (space-separated, e.g. 500e6 510e6 520e6)",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=10,
        help="Number of decision cycles",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--modulation-bpsk",
        action="store_true",
        help="Default modulation: BPSK (software test only)",
    )
    parser.add_argument(
        "--enable-rf",
        action="store_true",
        help="Enable RF transmission (operator authorization required)",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run software-only test (no hardware, no RF)",
    )

    args = parser.parse_args()

    # Safety check: the pipeline's RF path is disabled (see run_hardware_pipeline).
    if args.enable_rf:
        raise SystemExit(PIPELINE_RF_DISABLED_MESSAGE)
    if args.enable_rf and not args.test_mode:
        print("\nWARNING: RF transmission will be enabled.")
        print("This requires physical safety and regulatory checks first.")
        response = input("Operator confirms: (y/N) ")
        if response.lower() != "y":
            print("Aborted. RF remains disabled.")
            args.enable_rf = False

    if args.test_mode or not args.enable_rf:
        set_rf_enabled(False)
        print("\nRF TRANSMISSION STATUS: DISABLED (operator-controlled)")
    else:
        set_rf_enabled(True)
        print("\nRF TRANSMISSION STATUS: ENABLED (operator-authorized)")

    # Run pipeline
    results = run_hardware_pipeline(
        channel_frequencies=args.channels,
        steps=args.steps,
        seed=args.seed,
        enable_rf=args.enable_rf,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("  PIPELINE SUMMARY")
    print("=" * 60)
    print(f"  Steps       : {results['steps']}")
    channels_mhz = [f / 1e6 for f in results["channels_hz"]]
    print(f"  Channels    : {' '.join(f'{c:.3f}' for c in channels_mhz)} MHz")
    print(f"  Modulations : {set(d['command']['modulation'] for d in results['decisions'])}")
    print(f"  Enabled     : {sum(1 for d in results['decisions'] if d['command']['enabled'])}/{results['steps']}")
    print("=" * 60)

    # Save results
    output_dir = Path("results/pipeline")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"pipeline_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_file.write_text(json.dumps(results, indent=4))

    print(f"  Results saved: {output_file}")


if __name__ == "__main__":
    main()
