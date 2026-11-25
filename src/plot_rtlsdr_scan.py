import csv
import numpy as np
import matplotlib.pyplot as plt

filename = "results/rtl_sdr_fm_scan.csv"

frequencies = []
powers = []

with open(filename, newline="") as f:
    reader = csv.reader(f)

    for row in reader:
        if not row:
            continue

        start = float(row[2])
        stop = float(row[3])
        bin_size = float(row[4])
        values = np.array([float(x) for x in row[6:]])

        centers = start + (np.arange(len(values)) + 0.5) * bin_size

        frequencies.extend(centers / 1e6)
        powers.extend(values)

frequencies = np.array(frequencies)
powers = np.array(powers)

order = np.argsort(frequencies)
frequencies = frequencies[order]
powers = powers[order]

plt.figure(figsize=(12, 6))
plt.plot(frequencies, powers, linewidth=0.8)

plt.xlabel("Frequency (MHz)")
plt.ylabel("Received power (dBFS, rtl_power scale)")
plt.title("RTL-SDR Spectrum Scan: 88–108 MHz")
plt.grid(alpha=0.3)
plt.tight_layout()

plt.savefig(
    "results/figures/faculty/rtl_sdr_fm_spectrum.png",
    dpi=300
)

plt.show()
