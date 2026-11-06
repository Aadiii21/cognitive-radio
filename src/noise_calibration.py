import csv
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FILES = [
    ROOT / "results/channel_snr_calibration.csv",
    ROOT / "results/channel_snr_extension.csv",
    ROOT / "results/channel_snr_extension_low_snr.csv",
]

def load_calibration():
    grouped = {}

    for path in FILES:
        if not path.exists():
            raise FileNotFoundError(path)

        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                modulation = row["modulation"]
                noise = float(row["noise_voltage"])
                snr = float(row["snr_db"])

                grouped.setdefault(modulation, {}).setdefault(
                    noise, []
                ).append(snr)

    result = {}

    for modulation, measurements in grouped.items():
        result[modulation] = sorted(
            (noise, float(np.mean(values)))
            for noise, values in measurements.items()
        )

    return result


CALIBRATION = load_calibration()


def noise_for_snr(target_snr_db, modulation="BPSK"):
    measurements = CALIBRATION[modulation]

    noise_values = np.array([x[0] for x in measurements])
    snr_values = np.array([x[1] for x in measurements])

    # Explicit boundary saturation, not extrapolation.
    bounded_snr = np.clip(
        float(target_snr_db),
        snr_values.min(),
        snr_values.max()
    )

    return float(np.interp(
        bounded_snr,
        snr_values[::-1],
        noise_values[::-1]
    ))


if __name__ == "__main__":
    print("CALIBRATION COVERAGE")

    for modulation, values in CALIBRATION.items():
        snrs = [x[1] for x in values]
        print(
            f"{modulation:>8}: "
            f"{min(snrs):.2f} to {max(snrs):.2f} dB"
        )

    print("\nTARGET SNR CONVERSION")

    for target in (18, 13, 9, 0, -5, 25):
        print(
            f"{target:>5} dB -> "
            f"{noise_for_snr(target):.5f}"
        )
