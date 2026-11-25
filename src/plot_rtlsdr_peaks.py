import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

FS = 2_048_000
N = 1_048_576

files = [
    ("results/rtl_sdr_98mhz.iq", 98e6),
    ("results/rtl_sdr_100mhz.iq", 100e6),
]

out = Path("results/figures")
out.mkdir(parents=True, exist_ok=True)

fig, axes = plt.subplots(2, 1, figsize=(12, 8))

for ax, (filename, center) in zip(axes, files):
    raw = np.fromfile(filename, dtype=np.uint8)

    iq = (
        raw[0::2].astype(np.float32) - 127.5
        + 1j * (raw[1::2].astype(np.float32) - 127.5)
    )[:N]

    window = np.hanning(N)
    spectrum = np.fft.fftshift(np.fft.fft(iq * window))
    psd = np.abs(spectrum)**2 / np.sum(window**2)
    offsets = np.fft.fftshift(np.fft.fftfreq(N, 1/FS))

    power_db = 10*np.log10(psd + 1e-20)

    ax.plot(offsets/1000, power_db, linewidth=0.7)
    ax.set_title(f"RTL-SDR spectrum around {center/1e6:.1f} MHz")
    ax.set_xlabel("Offset from tuned center (kHz)")
    ax.set_ylabel("Relative power (dB)")
    ax.grid(True, alpha=0.3)

fig.tight_layout()
fig.savefig(out / "rtl_sdr_peak_analysis.png", dpi=200)
plt.close(fig)

print("Saved results/figures/rtl_sdr_peak_analysis.png")
