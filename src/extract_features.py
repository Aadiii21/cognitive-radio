
import argparse
import csv
from pathlib import Path

import numpy as np
from scipy.signal import welch, spectrogram


def load_iq(filename):
    raw = np.fromfile(filename, dtype=np.uint8)

    if len(raw) < 2 or len(raw) % 2:
        raise ValueError("Invalid IQ file")

    iq = raw.reshape(-1, 2).astype(np.float64)
    iq = (iq - 127.5) / 127.5

    return iq[:, 0] + 1j * iq[:, 1]


def estimate_features(samples, fs, fc):
    # Average power spectral density
    freq, psd = welch(
        samples,
        fs=fs,
        nperseg=16384,
        return_onesided=False,
        scaling="density"
    )

    freq = np.fft.fftshift(freq)
    psd = np.fft.fftshift(psd)

    psd = np.maximum(psd, 1e-20)
    psd_db = 10 * np.log10(psd)

    # Ignore the receiver's DC region
    dc_mask = np.abs(freq) < 10000

    search_psd = psd.copy()
    search_psd[dc_mask] = 0

    peak_idx = np.argmax(search_psd)
    peak_offset = freq[peak_idx]
    peak_frequency = fc + peak_offset

    # Estimate background outside the detected signal
    peak_mask = np.abs(freq - peak_offset) < 150000

    noise_mask = ~(peak_mask | dc_mask)

    if np.count_nonzero(noise_mask) < 10:
        raise ValueError("Insufficient noise-only bins")

    noise_floor = np.median(psd[noise_mask])

    peak_psd = psd[peak_idx]

    peak_psd_db = 10 * np.log10(peak_psd)
    noise_floor_db = 10 * np.log10(noise_floor)

    peak_to_floor = peak_psd_db - noise_floor_db

    # Estimate occupied bandwidth using noise-subtracted power
    signal_mask = np.abs(freq - peak_offset) < 250000
    signal_mask &= ~dc_mask

    signal_power = np.maximum(
        psd[signal_mask] - noise_floor, 0
    )

    signal_freq = freq[signal_mask]

    total_power = np.sum(signal_power)

    if total_power <= 0:
        raise ValueError("No detectable signal power")

    order = np.argsort(signal_freq)
    signal_freq = signal_freq[order]
    signal_power = signal_power[order]

    cumulative = np.cumsum(signal_power)
    cumulative /= cumulative[-1]

    low_idx = np.searchsorted(cumulative, 0.005)
    high_idx = np.searchsorted(cumulative, 0.995)

    occupied_bandwidth = (
        signal_freq[high_idx] - signal_freq[low_idx]
    )

    # Spectral flatness over detected signal region
    positive_signal = psd[signal_mask]

    spectral_flatness = (
        np.exp(np.mean(np.log(positive_signal)))
        / np.mean(positive_signal)
    )

    # Spectral kurtosis from multiple time segments
    sk_freq, _, frames = spectrogram(
        samples,
        fs=fs,
        nperseg=8192,
        noverlap=4096,
        return_onesided=False,
        mode="psd",
        scaling="density"
    )

    sk_freq = np.fft.fftshift(sk_freq)
    frames = np.fft.fftshift(frames, axes=0)

    mean_power = np.mean(frames, axis=1)
    mean_squared_power = np.mean(frames ** 2, axis=1)

    sk_per_bin = (
        mean_squared_power /
        np.maximum(mean_power ** 2, 1e-20)
        - 2
    )

    sk_signal_mask = (
        np.abs(sk_freq - peak_offset) < 250000
    )

    sk_signal_mask &= np.abs(sk_freq) >= 10000

    spectral_kurtosis = np.median(
        sk_per_bin[sk_signal_mask]
    )

    return {
        "peak_frequency_MHz": peak_frequency / 1e6,
        "peak_PSD_dB_per_Hz": peak_psd_db,
        "noise_floor_dB_per_Hz": noise_floor_db,
        "peak_to_floor_dB": peak_to_floor,
        "occupied_bandwidth_kHz": occupied_bandwidth / 1e3,
        "spectral_flatness": spectral_flatness,
        "spectral_kurtosis_median": spectral_kurtosis,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--input", required=True)
    parser.add_argument("--fc", type=float, required=True)
    parser.add_argument("--fs", type=float, default=2.048e6)

    args = parser.parse_args()

    samples = load_iq(args.input)

    features = estimate_features(
        samples,
        args.fs,
        args.fc
    )

    print("\n===== SDR SIGNAL FEATURES =====")

    for name, value in features.items():
        print(f"{name:32s}: {value:.4f}")

    output = Path("results/features")
    output.mkdir(parents=True, exist_ok=True)

    input_stem = Path(args.input).stem
    csv_path = output / f"{input_stem}_features.csv"

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=features.keys()
        )
        writer.writeheader()
        writer.writerow(features)

    print(f"\nSaved: {csv_path}")


if __name__ == "__main__":
    main()
