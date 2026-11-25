import csv
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib.pyplot as plt

ROOT = Path("results")
OUT = ROOT / "figures" / "faculty"
OUT.mkdir(parents=True, exist_ok=True)

MODELS = {
    "BPSK": (42.198029, -153.934945),
    "QPSK": (180.955965, -994.912015),
    "16-QAM": (79.256161, -1032.793196),
}

MODULATIONS = ["BPSK", "QPSK", "16-QAM"]

def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

# -------------------------------------------------
# FIGURE 1: Empirical packet success + logistic fit
# -------------------------------------------------

data = read_csv(ROOT / "expanded_equal_power_calibration.csv")

empirical = defaultdict(list)

for row in data:
    modulation = row["modulation"]
    noise = float(row["noise_voltage"])
    success = row["packet_success"].strip().lower() == "true"
    empirical[(modulation, noise)].append(int(success))

plt.figure(figsize=(10, 6))

x = np.linspace(0.02, 0.45, 500)

for modulation in MODULATIONS:
    points = sorted(
        (noise, np.mean(values))
        for (mod, noise), values in empirical.items()
        if mod == modulation
    )

    px, py = zip(*points)
    intercept, slope = MODELS[modulation]
    z = np.clip(intercept + slope * x, -40, 40)
    probability = 1 / (1 + np.exp(-z))

    plt.scatter(px, py, s=22, alpha=0.7,
                label=f"{modulation} empirical")
    plt.plot(x, probability, linewidth=2,
             label=f"{modulation} logistic fit")

plt.xlabel("GNU Radio noise voltage")
plt.ylabel("Packet success probability")
plt.title("Packet Success Probability vs Noise Voltage")
plt.ylim(-0.05, 1.05)
plt.grid(alpha=0.3)
plt.legend(ncol=2)
plt.tight_layout()
plt.savefig(OUT / "01_packet_success_calibration.png", dpi=300)
plt.close()

# -------------------------------------------------
# FIGURE 2: SNR vs noise voltage
# -------------------------------------------------

snr_data = {}

for filename in [
    "channel_snr_calibration.csv",
    "channel_snr_extension.csv",
    "channel_snr_extension_low_snr.csv",
    "channel_snr_extension_modulations.csv",
]:
    path = ROOT / filename
    if not path.exists():
        continue

    for row in read_csv(path):
        key = (
            row["modulation"],
            float(row["noise_voltage"]),
            int(row["seed"])
        )
        snr_data[key] = float(row["snr_db"])

grouped = defaultdict(list)

for (modulation, noise, seed), snr in snr_data.items():
    grouped[(modulation, noise)].append(snr)

plt.figure(figsize=(10, 6))

for modulation in MODULATIONS:
    points = sorted(
        (noise, np.mean(values))
        for (mod, noise), values in grouped.items()
        if mod == modulation
    )

    px, py = zip(*points)
    plt.plot(px, py, marker="o", markersize=3,
             linewidth=2, label=modulation)

plt.xlabel("GNU Radio noise voltage")
plt.ylabel("Measured SNR (dB)")
plt.title("SNR vs Noise Voltage for Different Modulations")
plt.grid(alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig(OUT / "02_snr_noise_comparison.png", dpi=300)
plt.close()

print("Generated:")
for path in sorted(OUT.glob("*.png")):
    print(path)
