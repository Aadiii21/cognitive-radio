import numpy as np
import matplotlib.pyplot as plt

FS = 2.048e6
N = 262144

captures = [
    ("results/rtl_sdr_100mhz.iq", 100e6),
    ("results/rtl_sdr_98mhz.iq", 98e6),
]

fig, axes = plt.subplots(2, 1, figsize=(11, 8))

for ax, (filename, center_freq) in zip(axes, captures):
    raw = np.fromfile(filename, dtype=np.uint8)

    iq = (
        raw[0::2].astype(np.float32) - 127.5
        + 1j * (raw[1::2].astype(np.float32) - 127.5)
    )

    iq = iq[:N]
    window = np.hanning(N)

    spectrum = np.fft.fftshift(
        np.fft.fft(iq * window)
    )

    power_db = 20 * np.log10(
        np.abs(spectrum) / (np.sum(window)) + 1e-12
    )

    freq = (
        np.fft.fftshift(np.fft.fftfreq(N, 1 / FS))
        + center_freq
    ) / 1e6

    ax.plot(freq, power_db, linewidth=0.7)
    ax.set_title(f"RTL-SDR Spectrum around {center_freq/1e6:.0f} MHz")
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Relative magnitude (dB)")
    ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig(
    "results/figures/rtl_sdr_iq_comparison.png",
    dpi=300
)
