#!/usr/bin/env python3
"""Hardware BER table and figure from the OTA run records (no hardware needed).

    python scripts/summarize_hardware_sweep.py

Reads every results/hardware/experiment_results/*.json made with a
multimod_frame_v1 waveform and writes:
  results/analysis/hardware_ber_runs.csv          one row per run
  results/figures/hardware_ber_vs_theory.png      measured BER vs AWGN theory
Es/N0 per run is the linear mean of the per-frame data-aided SNR. Runs with
zero errors are drawn at the 95 % upper bound (3 / bits) with a down arrow.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy.special import erfc

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "hardware" / "experiment_results"
CSV_OUT = ROOT / "results" / "analysis" / "hardware_ber_runs.csv"
FIG_OUT = ROOT / "results" / "figures" / "hardware_ber_vs_theory.png"
MODS = ("BPSK", "QPSK", "16QAM")


def q(x):
    return 0.5 * erfc(x / np.sqrt(2))


def theory_ber(mod, esn0_db):
    g = 10 ** (np.asarray(esn0_db, dtype=float) / 10)
    if mod == "BPSK":
        return q(np.sqrt(2 * g))
    if mod == "QPSK":
        return q(np.sqrt(g))
    return 0.75 * q(np.sqrt(g / 5))      # Gray 16-QAM, nearest-neighbour approximation


def collect(runs_dir=RUNS):
    rows = []
    for p in sorted(runs_dir.glob("*.json")):
        r = json.loads(p.read_text())
        rx = r.get("receiver") or {}
        if r.get("waveform_format") != "multimod_frame_v1" or not rx.get("frames"):
            continue
        frames = rx["frames"]
        esn0 = 10 * np.log10(np.mean([10 ** (f["snr_db"] / 10) for f in frames]))
        errs, bits = int(rx["total_payload_bit_errors"]), int(rx["total_payload_bits_compared"])
        corr = r.get("rf_path_correction") or {}
        rows.append({
            "run": p.stem.replace("experiment_result_", ""),
            "modulation": rx["modulation"],
            "pluto_attenuation_db": r.get("tx", {}).get("requested_attenuation_db"),
            "rx_gain_db": (r.get("rx") or {}).get("gain_db", (r.get("derived_configuration") or {}).get("rx_gain_db")),
            "frames": len(frames),
            "mean_esn0_db": round(float(esn0), 2),
            "bit_errors": errs, "bits": bits,
            "measured_ber": errs / bits if bits else None,
            "ber_95_upper_if_zero": round(3 / bits, 6) if bits and errs == 0 else "",
            "theory_ber_awgn": float(theory_ber(rx["modulation"], esn0)),
            "rf_path": corr.get("actual_type") or (r.get("rf_path") or {}).get("type"),
        })
    return rows


def plot(rows, path=FIG_OUT):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"BPSK": "#2F5D8A", "QPSK": "#2E7D57", "16QAM": "#B8621B"}
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    s = np.linspace(0, 26, 200)
    for m in MODS:
        ax.semilogy(s, theory_ber(m, s), color=colors[m], lw=1.2, label=f"{m} theory (AWGN)")
        pts = [r for r in rows if r["modulation"] == m]
        hit = [(r["mean_esn0_db"], r["measured_ber"]) for r in pts if r["bit_errors"] > 0]
        zero = [(r["mean_esn0_db"], 3 / r["bits"]) for r in pts if r["bit_errors"] == 0]
        if hit:
            ax.scatter(*zip(*hit), color=colors[m], edgecolor="black", s=40, zorder=3, label=f"{m} measured")
        if zero:
            ax.scatter(*zip(*zero), color=colors[m], marker="v", s=40, alpha=0.6, zorder=3,
                       label=f"{m} 0 errors (95 % bound)")
    ax.axhline(1e-3, color="#999999", ls=":", lw=0.8)
    ax.set_ylim(1e-5, 0.5)
    ax.set_xlim(0, 26)
    ax.set_xlabel("Receiver Es/N0 (dB, measured per run)")
    ax.set_ylabel("Bit error rate")
    ax.set_title("OTA hardware BER vs AWGN theory (Pluto -> RTL-SDR, 866 MHz)", fontsize=10)
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=7, ncol=2, loc="upper right")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    plt.close(fig)


def main():
    rows = collect()
    if not rows:
        sys.exit(f"No multimod_frame_v1 run records in {RUNS}")
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    plot(rows)
    for r in rows:
        print(f"  {r['run']}  {r['modulation']:5s} att {r['pluto_attenuation_db']:>2}  Es/N0 {r['mean_esn0_db']:5.1f} dB  "
              f"{r['bit_errors']:4d}/{r['bits']}  theory {r['theory_ber_awgn']:.1e}")
    print(f"{len(rows)} runs -> {CSV_OUT.relative_to(ROOT)}, {FIG_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
