from dataclasses import dataclass

from src.calibrated_controller import CalibratedCognitiveController
from src.radio import SimulatedRadio
from src.switching import SwitchingDelay


@dataclass
class ExperimentSummary:
    elapsed_steps: int
    attempted_packets: int
    successful_packets: int
    delivered_bytes: int
    transmission_steps: int
    unavailable_steps: int
    pdr: float
    throughput_bytes_per_step: float
    availability: float
    channel_switches: int


def run_experiment(
    steps=500,
    seed=2026,
    volatility=1.5,
    burst_probability=0.08,
    payload_size=256,
    switch_delay_steps=2,
):
    if steps <= 0:
        raise ValueError("steps must be positive.")

    if payload_size <= 0:
        raise ValueError("payload_size must be positive.")

    radio = SimulatedRadio(
        seed=seed,
        volatility=volatility,
        burst_probability=burst_probability,
    )

    controller = CalibratedCognitiveController()
    switching_delay = SwitchingDelay(switch_delay_steps)

    attempted_packets = 0
    successful_packets = 0
    delivered_bytes = 0
    transmission_steps = 0
    unavailable_steps = 0
    channel_switches = 0

    try:
        for step in range(steps):
            measurements = radio.measure_channels()

            # A switching interruption blocks transmission and
            # controller decisions until the countdown finishes.
            if switching_delay.is_active:
                switching_delay.consume_step()
                unavailable_steps += 1
                continue

            channel_snrs = [
                measurement.snr_db
                for measurement in measurements
            ]

            decision = controller.decide(channel_snrs)

            if decision.action == "switch_channel":
                channel_switches += 1
                radio.set_channel(decision.channel)
                radio.set_modulation(decision.modulation)

                switching_delay.start()

                # The switch-initiation step is also unavailable.
                if switching_delay.consume_step():
                    unavailable_steps += 1
                    continue

            radio.set_channel(decision.channel)
            radio.set_modulation(decision.modulation)

            result = radio.transmit_packet(bytes(payload_size))

            attempted_packets += 1
            transmission_steps += 1
            successful_packets += int(result.success)
            delivered_bytes += result.delivered_bytes

            if (step + 1) % 100 == 0:
                pdr = (
                    successful_packets / attempted_packets
                    if attempted_packets else 0.0
                )

                availability = transmission_steps / (step + 1)

                print(
                    f"Step {step + 1:4d}/{steps} | "
                    f"Channel {decision.channel} | "
                    f"{decision.modulation:6s} | "
                    f"SNR {decision.estimated_snr:6.2f} dB | "
                    f"PDR {pdr:.3f} | "
                    f"Availability {availability:.3f} | "
                    f"Switches {channel_switches}"
                )

    finally:
        radio.close()

    pdr = (
        successful_packets / attempted_packets
        if attempted_packets else 0.0
    )

    throughput = delivered_bytes / steps
    availability = transmission_steps / steps

    return ExperimentSummary(
        elapsed_steps=steps,
        attempted_packets=attempted_packets,
        successful_packets=successful_packets,
        delivered_bytes=delivered_bytes,
        transmission_steps=transmission_steps,
        unavailable_steps=unavailable_steps,
        pdr=pdr,
        throughput_bytes_per_step=throughput,
        availability=availability,
        channel_switches=channel_switches,
    )


if __name__ == "__main__":
    summary = run_experiment()

    print("\n========== EXPERIMENT SUMMARY ==========")
    print(f"Elapsed steps:      {summary.elapsed_steps}")
    print(f"Attempted packets:  {summary.attempted_packets}")
    print(f"Successful packets: {summary.successful_packets}")
    print(f"Delivered data:     {summary.delivered_bytes} bytes")
    print(f"Transmission steps: {summary.transmission_steps}")
    print(f"Unavailable steps:  {summary.unavailable_steps}")
    print(f"PDR:                {summary.pdr:.4f}")
    print(
        "Throughput:         "
        f"{summary.throughput_bytes_per_step:.2f} bytes/step"
    )
    print(f"Availability:       {summary.availability:.4f}")
    print(f"Channel switches:   {summary.channel_switches}")
