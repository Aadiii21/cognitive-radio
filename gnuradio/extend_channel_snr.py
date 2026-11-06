import csv
import numpy as np

from measure_channel_snr import measure
from gnuradio import digital

OUTPUT = "results/channel_snr_extension_low_snr.csv"

NOISE_LEVELS = np.round(np.arange(0.300, 0.501, 0.010), 3)
SEEDS = range(40, 70)

rows = []

total = len(NOISE_LEVELS) * len(SEEDS)
completed = 0

for noise in NOISE_LEVELS:
    for seed in SEEDS:
        signal_power, noise_power, snr_db = measure(
            digital.constellation_bpsk,
            noise,
            seed
        )

        rows.append({
            "modulation": "BPSK",
            "noise_voltage": float(noise),
            "seed": seed,
            "signal_power": signal_power,
            "noise_power": noise_power,
            "snr_db": snr_db,
        })

        completed += 1

        if completed % 30 == 0:
            print(f"Progress: {completed}/{total}", flush=True)

with open(OUTPUT, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print(f"\nSaved {completed} measurements to {OUTPUT}")

for noise in NOISE_LEVELS:
    values = [
        r["snr_db"] for r in rows
        if r["noise_voltage"] == float(noise)
    ]
    print(
        f"Noise={noise:.3f} | "
        f"SNR={np.mean(values):.3f} dB | "
        f"SD={np.std(values):.3f}"
    )
