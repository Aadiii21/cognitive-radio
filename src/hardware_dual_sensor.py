import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from src.radio.rtl_sdr_sensor import RTLSDRSensor
from src.radio.pluto_sensor import PlutoSensor
from src.controller_cost_aware import CognitiveController


FREQUENCIES = [
    500_000_000,
    501_000_000,
    502_000_000,
]


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Dual-SDR hardware sensing and controller experiment"
    )

    parser.add_argument(
        "--controller-source",
        choices=["rtl", "pluto"],
        default="rtl",
        help="Sensor used by the cognitive controller",
    )

    parser.add_argument(
        "--output-dir",
        default="results",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rtl = None
    pluto = None

    try:
        print("\nInitializing RTL-SDR...")
        rtl = RTLSDRSensor(
            center_frequencies=FREQUENCIES,
            sample_rate=2_048_000,
            gain=28,
            bandwidth=180_000,
            capture_samples=262_144,
        )

        print("\nInitializing Pluto...")
        pluto = PlutoSensor(
            center_frequencies=FREQUENCIES,
            sample_rate=2_400_000,
            gain=30,
            bandwidth=180_000,
            capture_samples=262_144,
        )

        # Acquire measurements independently.
        print("\n========== RTL-SDR ACQUISITION ==========")
        rtl_measurements = rtl.measure_channels()

        print("\n========== PLUTO ACQUISITION ==========")
        pluto_measurements = pluto.measure_channels()

        sensor_results = {
            "rtl": rtl_measurements,
            "pluto": pluto_measurements,
        }

        # Preserve both measurement streams.
        measurement_rows = []

        acquisition_time = timestamp()

        for source, measurements in sensor_results.items():
            for measurement in measurements:
                measurement_rows.append({
                    "timestamp_utc": acquisition_time,
                    "sensor": source,
                    "channel_index": measurement.channel_index,
                    "center_frequency_hz": FREQUENCIES[
                        measurement.channel_index
                    ],
                    "snr_db": measurement.snr_db,
                    "timestamp_step": measurement.timestamp_step,
                    "received_power_dbm": measurement.received_power_dbm,
                    "noise_floor_dbm": measurement.noise_floor_dbm,
                })

        measurement_fields = [
            "timestamp_utc",
            "sensor",
            "channel_index",
            "center_frequency_hz",
            "snr_db",
            "timestamp_step",
            "received_power_dbm",
            "noise_floor_dbm",
        ]

        measurement_path = output_dir / "dual_sensor_measurements.csv"

        write_csv(
            measurement_path,
            measurement_rows,
            measurement_fields,
        )

        # Select one sensor as the controller input.
        selected_measurements = sensor_results[args.controller_source]

        selected_measurements = sorted(
            selected_measurements,
            key=lambda item: item.channel_index,
        )

        expected_indices = list(range(len(FREQUENCIES)))
        actual_indices = [
            item.channel_index for item in selected_measurements
        ]

        if actual_indices != expected_indices:
            raise RuntimeError(
                f"Incomplete or unordered measurements: {actual_indices}"
            )

        channel_snrs = [
            item.snr_db for item in selected_measurements
        ]

        controller = CognitiveController()
        decision = controller.decide(channel_snrs)

        decision_time = timestamp()

        decision_row = {
            "timestamp_utc": decision_time,
            "controller_source": args.controller_source,
            "input_snr_db": ";".join(
                f"{value:.4f}" for value in channel_snrs
            ),
            "selected_channel": decision.channel,
            "selected_frequency_hz": FREQUENCIES[decision.channel],
            "modulation": decision.modulation,
            "data_rate": decision.data_rate,
            "action": decision.action,
            "estimated_snr_db": decision.estimated_snr,
            "expected_utility": decision.expected_utility,
        }

        decision_fields = list(decision_row.keys())

        decision_path = output_dir / "dual_sensor_decisions.csv"

        write_csv(
            decision_path,
            [decision_row],
            decision_fields,
        )

        print("\n========== CONTROLLER DECISION ==========")
        print("Measurement source:", args.controller_source)
        print("Channel SNRs:", channel_snrs)
        print("Selected channel:", decision.channel)
        print("Selected frequency:", FREQUENCIES[decision.channel] / 1e6, "MHz")
        print("Modulation:", decision.modulation)
        print("Action:", decision.action)
        print("Expected utility:", decision.expected_utility)

        print("\n========== OUTPUT FILES ==========")
        print("Measurements:", measurement_path)
        print("Decision:", decision_path)

    finally:
        if rtl is not None:
            rtl.close()

        if pluto is not None:
            pluto.close()


if __name__ == "__main__":
    main()
