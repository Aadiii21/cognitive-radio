#!/usr/bin/python3

import csv
import os
import numpy as np

import packet_receiver_general as receiver
from calibrate_receiver import (
    MODULATIONS,
    build_normalized_constellation,
)

EXPERIMENTS = {
    "BPSK": np.round(np.arange(0.250, 0.3001, 0.005), 3),
    "QPSK": np.round(np.arange(0.160, 0.2001, 0.005), 3),
    "16-QAM": np.round(np.arange(0.065, 0.0851, 0.002), 3),
}

SEEDS = list(range(40, 70))

OUTPUT = "results/refined_equal_power_calibration.csv"


def main():
    os.makedirs("results", exist_ok=True)

    all_results = []

    # Resume from previously saved trials.
    if os.path.exists(OUTPUT):
        with open(OUTPUT, newline="") as file:
            all_results = list(csv.DictReader(file))

        # Restore CSV values to their correct Python types.
        for row in all_results:
            row["noise_voltage"] = float(row["noise_voltage"])
            row["seed"] = int(row["seed"])
            row["packet_success"] = (
                str(row["packet_success"]).lower() == "true"
            )

            for key in (
                "original_symbol_power",
                "normalized_symbol_power",
                "SER",
                "BER"
            ):
                if key in row and row[key] not in ("", None):
                    row[key] = float(row[key])

            row.setdefault("receiver_error", "")

        completed_keys = {
            (r["modulation"], round(r["noise_voltage"], 3), r["seed"])
            for r in all_results
        }
    else:
        completed_keys = set()

    total_trials = sum(
        len(noises) * len(SEEDS)
        for noises in EXPERIMENTS.values()
    )

    completed = 0

    print("=" * 75)
    print("REFINED EQUAL-POWER MODULATION CALIBRATION")
    print("=" * 75)
    print(f"Seeds: {SEEDS[0]}–{SEEDS[-1]}")
    print(f"Total trials: {total_trials}")

    for modulation, noise_levels in EXPERIMENTS.items():

        factory = MODULATIONS[modulation]

        constellation, points, original_power = (
            build_normalized_constellation(factory)
        )

        normalized_power = float(
            np.mean(np.abs(points) ** 2)
        )

        assert np.isclose(normalized_power, 1.0, atol=1e-6)

        (
            packet,
            training,
            sync_word,
            payload,
            pilot,
            pilot_count
        ) = receiver.build_packet(points)

        print("\n" + "=" * 75)
        print(f"MODULATION: {modulation}")
        print(f"Original power: {original_power:.6f}")
        print(f"Normalized power: {normalized_power:.6f}")
        print("=" * 75)

        for noise in noise_levels:

            group = []

            for seed in SEEDS:

                key = (modulation, round(float(noise), 3), seed)

                if key in completed_keys:
                    completed += 1
                    continue

                try:
                    result = receiver.evaluate_seed(
                        seed,
                        points,
                        constellation,
                        packet,
                        training,
                        sync_word,
                        payload,
                        pilot,
                        noise_voltage=float(noise)
                    )

                    row = {
                        "modulation": modulation,
                        "original_symbol_power": original_power,
                        "normalized_symbol_power": normalized_power,
                        "noise_voltage": float(noise),
                        "seed": seed,
                        **result,
                        "receiver_error": ""
                    }

                except RuntimeError as error:
                    row = {
                        "modulation": modulation,
                        "original_symbol_power": original_power,
                        "normalized_symbol_power": normalized_power,
                        "noise_voltage": float(noise),
                        "seed": seed,
                        "SER": float("nan"),
                        "BER": float("nan"),
                        "packet_success": False,
                        "receiver_error": str(error)
                    }

                    print(
                        f"Seed {seed} | RECEIVER FAILURE: {error}",
                        flush=True
                    )

                group.append(row)
                all_results.append(row)
                completed_keys.add(key)
                completed += 1

                # Persist every trial, including failures.
                with open(OUTPUT, "w", newline="") as file:
                    writer = csv.DictWriter(
                        file,
                        fieldnames=list(all_results[0].keys())
                    )
                    writer.writeheader()
                    writer.writerows(all_results)

            pdr = np.mean([
                r["packet_success"] for r in group
            ])

            mean_ser = np.mean([
                r["SER"] for r in group
            ])

            mean_ber = np.mean([
                r["BER"] for r in group
            ])

            print(
                f"Noise={noise:.3f} | "
                f"PDR={pdr:.1%} | "
                f"SER={mean_ser:.6f} | "
                f"BER={mean_ber:.6f} | "
                f"Progress={completed}/{total_trials}",
                flush=True
            )

            # Save after every noise group so partial work survives interruption.
            with open(OUTPUT, "w", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=list(all_results[0].keys())
                )
                writer.writeheader()
                writer.writerows(all_results)

    print("\n" + "=" * 75)
    print("REFINEMENT COMPLETE")
    print("=" * 75)

    print(
        f"{'Modulation':<12} {'Noise':>8} "
        f"{'PDR':>8} {'SER':>12} {'BER':>12}"
    )

    for modulation, noise_levels in EXPERIMENTS.items():

        for noise in noise_levels:

            group = [
                r for r in all_results
                if r["modulation"] == modulation
                and r["noise_voltage"] == float(noise)
            ]

            print(
                f"{modulation:<12} "
                f"{noise:>8.3f} "
                f"{np.mean([r['packet_success'] for r in group]):>7.1%} "
                f"{np.mean([r['SER'] for r in group]):>12.6f} "
                f"{np.mean([r['BER'] for r in group]):>12.6f}"
            )

    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
