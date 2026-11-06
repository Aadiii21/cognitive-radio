#!/usr/bin/python3

import csv
import os
import numpy as np

import packet_receiver_general as receiver
from gnuradio import digital


MODULATIONS = {
    "BPSK": digital.constellation_bpsk,
    "QPSK": digital.constellation_qpsk,
    "16-QAM": digital.constellation_16qam,
}

NOISE_LEVELS = [
    0.045, 0.055, 0.065, 0.075,
    0.085, 0.100, 0.125, 0.160,
    0.200, 0.250, 0.300
]

SEEDS = list(range(40, 50))


def build_normalized_constellation(factory):
    original = factory().base()

    original_points = np.asarray(
        original.points(),
        dtype=np.complex128
    )

    original_power = np.mean(np.abs(original_points) ** 2)

    normalized_points = (
        original_points / np.sqrt(original_power)
    )

    constellation = digital.constellation_calcdist(
        normalized_points.tolist(),
        original.pre_diff_code(),
        original.rotational_symmetry(),
        original.dimensionality(),
        digital.constellation_calcdist.NO_NORMALIZATION
    ).base()

    points = np.asarray(
        constellation.points(),
        dtype=np.complex64
    )

    measured_power = np.mean(np.abs(points) ** 2)

    assert np.isclose(measured_power, 1.0, atol=1e-6)
    assert np.allclose(
        points,
        normalized_points,
        atol=1e-6
    )

    return constellation, points, original_power


def main():

    all_results = []

    for modulation, factory in MODULATIONS.items():

        constellation, points, original_power = (
            build_normalized_constellation(factory)
        )

        normalized_power = np.mean(np.abs(points) ** 2)

        (
            packet,
            training,
            sync_word,
            payload,
            pilot,
            pilot_count
        ) = receiver.build_packet(points)

        print("\n" + "=" * 75)
        print(f"CALIBRATING {modulation}")
        print("=" * 75)

        print(f"Original symbol power:   {original_power:.6f}")
        print(f"Normalized symbol power: {normalized_power:.6f}")
        print(f"Constellation size:      {len(points)}")

        for noise in NOISE_LEVELS:

            group = []

            print(f"\nNoise voltage: {noise:.3f}")

            for seed in SEEDS:

                result = receiver.evaluate_seed(
                    seed,
                    points,
                    constellation,
                    packet,
                    training,
                    sync_word,
                    payload,
                    pilot,
                    noise_voltage=noise
                )

                row = {
                    "modulation": modulation,
                    "original_symbol_power": original_power,
                    "normalized_symbol_power": normalized_power,
                    "noise_voltage": noise,
                    **result
                }

                group.append(row)
                all_results.append(row)

                print(
                    f"Seed {seed} | "
                    f"SER={result['SER']:.5f} | "
                    f"BER={result['BER']:.5f} | "
                    f"{'PASS' if result['packet_success'] else 'FAIL'}"
                )

            print(
                f"PDR={np.mean([r['packet_success'] for r in group]):.1%} | "
                f"Mean SER={np.mean([r['SER'] for r in group]):.6f} | "
                f"Mean BER={np.mean([r['BER'] for r in group]):.6f}"
            )

    os.makedirs("results", exist_ok=True)

    output = "results/equal_power_modulation_calibration.csv"

    with open(output, "w", newline="") as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(all_results[0].keys())
        )

        writer.writeheader()
        writer.writerows(all_results)

    print("\n" + "=" * 75)
    print("EQUAL-POWER CALIBRATION SUMMARY")
    print("=" * 75)

    print(
        f"{'Modulation':<12} {'Noise':>8} "
        f"{'PDR':>10} {'SER':>12} {'BER':>12}"
    )

    for modulation in MODULATIONS:

        for noise in NOISE_LEVELS:

            group = [
                r for r in all_results
                if r["modulation"] == modulation
                and r["noise_voltage"] == noise
            ]

            print(
                f"{modulation:<12} "
                f"{noise:>8.3f} "
                f"{np.mean([r['packet_success'] for r in group]):>9.1%} "
                f"{np.mean([r['SER'] for r in group]):>12.6f} "
                f"{np.mean([r['BER'] for r in group]):>12.6f}"
            )

    print(f"\nSaved: {output}")


if __name__ == "__main__":
    main()
