#!/usr/bin/env python3
"""Plot results/analysis/ber_vs_snr_multimod_synthetic.csv (from scripts/ber_curves.py).

    python scripts/plot_ber_synthetic.py   -> results/figures/ber_vs_esn0_synthetic.png
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "analysis" / "ber_vs_snr_multimod_synthetic.csv"
OUT = ROOT / "results" / "figures" / "ber_vs_esn0_synthetic.png"


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = list(csv.DictReader(open(SRC)))
    colors = {"BPSK": "#2F5D8A", "QPSK": "#2E7D57", "16QAM": "#B8621B"}
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for m, col in colors.items():
        r = [x for x in rows if x["modulation"] == m]
        s = [float(x["snr_db"]) for x in r]
        ax.semilogy(s, [float(x["theory_ber"]) for x in r], "-", color=col, lw=1.1, label=f"{m} theory")
        pts = [(float(x["snr_db"]), float(x["ber"])) for x in r if float(x["ber"]) > 0]
        ax.semilogy(*zip(*pts), "o", color=col, ms=5, mec="black", mew=0.5, label=f"{m} receiver (synthetic)")
    ax.axhline(1e-3, color="#999", ls=":", lw=0.8)
    ax.set_xlabel("Es/N0 (dB)")
    ax.set_ylabel("Bit error rate")
    ax.set_ylim(1e-5, 0.5)
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=7, ncol=2)
    ax.set_title("Multimod receiver BER on synthetic AWGN frames vs theory", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT, dpi=200)
    print("wrote", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
