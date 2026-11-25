#!/usr/bin/env python3

import csv
import os
import numpy as np

import packet_receiver_general as receiver
from calibrate_receiver import (
    MODULATIONS,
    build_normalized_constellation,
)

OUTPUT = "results/expanded_equal_power_calibration.csv"

SEEDS = list(range(40, 70))

NOISE_LEVELS = np.round(
    np.arange(0.02, 0.441, 0.02), 3
).tolist()

NOISE_LEVELS.append(0.45)

FIELDNAMES = [
    "modulation",
    "original_symbol_power",
    "normalized_symbol_power",
    "noise_voltage",
    "seed",
    "received_symbols",
    "sync_position",
    "sync_score",
    "pilot_blocks",
    "phase_range_degrees",
    "amplitude_variation",
    "payload_symbols",
    "symbol_errors",
    "bit_errors",
    "SER",
    "BER",
    "packet_success",
    "receiver_error",
]


def load_existing():
    if not os.path.exists(OUTPUT):
        return [], set()

    with open(OUTPUT, newline="") as f:
        rows = list(csv.DictReader(f))

    completed = set()

    for row in rows:
        key = (
            row["modulation"],
            round(float(row["noise_voltage"]), 3),
            int(row["seed"]),
        )
        completed.add(key)

    return rows, completed


def save_rows(rows):
    with open(OUTPUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main():
    os.makedirs("results", exist_ok=True)

    all_results, completed_keys = load_existing()

    total = len(MODULATIONS) * len(NOISE_LEVELS) * len(SEEDS)
    completed = len(completed_keys)

    print("=" * 75)
    print("EXPANDED EQUAL-POWER PACKET CALIBRATION")
    print("=" * 75)
    print(f"Noise range: {NOISE_LEVELS[0]:.3f}–{NOISE_LEVELS[-1]:.3f}")
    print(f"Noise points: {len(NOISE_LEVELS)}")
    print(f"Seeds: {SEEDS[0]}–{SEEDS[-1]}")
    print(f"Total planned trials: {total}")
    print(f"Previously completed: {completed}")
    print(f"Remaining: {total - completed}")

    for modulation, factory in MODULATIONS.items():

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
            pilot_count,
        ) = receiver.build_packet(points)

        print("\n" + "=" * 75)
        print(f"MODULATION: {modulation}")
        print(f"Original power: {original_power:.6f}")
        print(f"Normalized power: {normalized_power:.6f}")
        print("=" * 75)

        for noise in NOISE_LEVELS:

            for seed in SEEDS:

                key = (modulation, round(noise, 3), seed)

                if key in completed_keys:
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
                        noise_voltage=float(noise),
                    )

                    row = {
                        "modulation": modulation,
                        "original_symbol_power": original_power,
                        "normalized_symbol_power": normalized_power,
                        "noise_voltage": float(noise),
                        "seed": seed,
                        **result,
                        "receiver_error": "",
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
                        "receiver_error": str(error),
                    }

                    print(
                        f"RECEIVER ERROR | {modulation} | "
                        f"noise={noise:.3f} | seed={seed}: {error}",
                        flush=True,
                    )

                all_results.append(row)
                completed_keys.add(key)
                completed += 1

                # Save every trial so interrupted runs can resume.
                save_rows(all_results)

            group = [
                r for r in all_results
                if r["modulation"] == modulation
                and float(r["noise_voltage"]) == float(noise)
            ]

            if group:
                pdr = np.mean([
                    str(r["packet_success"]).lower() == "true"
                    for r in group
                ])

                ser = np.array([
                    float(r["SER"])
                    for r in group
                    if r.get("SER") not in ("", None)
                ], dtype=float)

                ber = np.array([
                    float(r["BER"])
                    for r in group
                    if r.get("BER") not in ("", None)
                ], dtype=float)

                mean_ser = np.nanmean(ser) if len(ser) else float("nan")
                mean_ber = np.nanmean(ber) if len(ber) else float("nan")

                print(
                    f"{modulation:>8} | "
                    f"noise={noise:.3f} | "
                    f"PDR={pdr:.1%} | "
                    f"SER={mean_ser:.6f} | "
                    f"BER={mean_ber:.6f} | "
                    f"Progress={completed}/{total}",
                    flush=True,
                )

    print("\n" + "=" * 75)
    print("EXPANDED CALIBRATION COMPLETE")
    print(f"Saved: {OUTPUT}")
    print(f"Completed trials: {len(completed_keys)}/{total}")
    print("=" * 75)


if __name__ == "__main__":
    main()
