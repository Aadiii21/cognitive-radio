#!/usr/bin/env python3

import csv
import numpy as np
from pathlib import Path

from measure_channel_snr import measure
from gnuradio import digital

OUTPUT = Path("results/channel_snr_extension_modulations.csv")

MODULATIONS = {
    "QPSK": digital.constellation_qpsk,
    "16-QAM": digital.constellation_16qam,
}

NOISE_LEVELS = list(np.round(np.arange(0.12, 0.441, 0.02), 3))
NOISE_LEVELS.append(0.45)

SEEDS = range(40, 70)

FIELDS = [
    "modulation",
    "noise_voltage",
    "seed",
    "signal_power",
    "noise_power",
    "snr_db",
]


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    total = len(MODULATIONS) * len(NOISE_LEVELS) * len(SEEDS)
    completed = 0

    print("=" * 72)
    print("EXTENDED MODULATION SNR CALIBRATION")
    print("=" * 72)
    print(f"Modulations: {list(MODULATIONS)}")
    print(f"Noise levels: {len(NOISE_LEVELS)}")
    print(f"Seeds per level: {len(SEEDS)}")
    print(f"Total measurements: {total}")

    for name, factory in MODULATIONS.items():
        print(f"\nCalibrating {name}", flush=True)

        for noise in NOISE_LEVELS:
            group = []

            for seed in SEEDS:
                signal_power, noise_power, snr_db = measure(
                    factory,
                    noise,
                    seed
                )

                row = {
                    "modulation": name,
                    "noise_voltage": float(noise),
                    "seed": seed,
                    "signal_power": signal_power,
                    "noise_power": noise_power,
                    "snr_db": snr_db,
                }

                rows.append(row)
                group.append(snr_db)
                completed += 1

                if completed % 30 == 0:
                    print(
                        f"Progress: {completed}/{total}",
                        flush=True
                    )

            print(
                f"Noise={noise:.3f} | "
                f"Mean SNR={np.mean(group):.3f} dB | "
                f"SD={np.std(group):.3f} dB",
                flush=True
            )

    with OUTPUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print("\n" + "=" * 72)
    print(f"Saved {len(rows)} measurements to {OUTPUT}")
    print("=" * 72)


if __name__ == "__main__":
    main()
