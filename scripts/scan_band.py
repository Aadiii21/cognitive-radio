#!/usr/bin/env python3
"""Passive scan of 865-868 MHz with the RTL-SDR (receive only, nothing is transmitted).

Measures the real noise floor and any real activity on the three demo channels
(865.7 / 866.5 / 867.3 MHz), independently of the scripted TX attenuation used
in the closed-loop demo. It answers: do the real channels differ, and is
anything else using them?

  # scan for 3 minutes (Pluto connected but its TX LO powered down, or unplugged)
  python scripts/scan_band.py --minutes 3

  # re-plot an existing rtl_power CSV
  python scripts/scan_band.py --input results/hardware/band_scan/scan_<stamp>/rtl_power.csv

Before scanning it checks that the Pluto TX LO is powered down, because a
running Pluto would show up in the scan as "activity". If the Pluto is not
reachable (unplugged) the scan goes ahead.

Outputs (results/hardware/band_scan/scan_<stamp>/):
  rtl_power.csv   raw rtl_power output
  scan.png        mean / max spectrum with the channel bands, and a waterfall
  summary.json    per-channel mean power, power above the band floor, busy fraction
"""
import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "hardware" / "band_scan"
CHANNELS_HZ = [865_700_000, 866_500_000, 867_300_000]
HALF_BW_HZ = 352_000           # occupied half-bandwidth of the demo frames (520.8 kBd, RRC 0.35)
BAND_HZ = (865_000_000, 868_000_000)
BUSY_THRESHOLD_DB = 6.0         # a sweep counts as "busy" on a channel if its in-band mean is this far above the floor


def parse_rtl_power(path):
    """rtl_power CSV -> (freqs_hz [n_bins], power_db [n_sweeps, n_bins], times [n_sweeps])."""
    sweeps = {}
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if len(row) < 7:
                continue
            key = (row[0].strip(), row[1].strip())
            lo, step = float(row[2]), float(row[4])
            vals = [float(x) for x in row[6:] if x.strip() not in ("", "nan", "-nan")]
            fr = lo + (np.arange(len(vals)) + 0.5) * step
            sweeps.setdefault(key, []).append((fr, np.array(vals)))
    if not sweeps:
        raise ValueError(f"No rtl_power rows in {path}")
    keys = sorted(sweeps)
    ref_f = np.concatenate([fr for fr, _ in sweeps[keys[0]]])
    order = np.argsort(ref_f)
    ref_f = ref_f[order]
    spectra, times = [], []
    for k in keys:
        fr = np.concatenate([fr for fr, _ in sweeps[k]])
        pw = np.concatenate([p for _, p in sweeps[k]])
        if len(fr) != len(ref_f):          # incomplete last sweep (scan stopped mid-sweep)
            continue
        spectra.append(pw[np.argsort(fr)])
        times.append(" ".join(k))
    return ref_f, np.array(spectra), times


def channel_stats(freqs, power, channels=CHANNELS_HZ, half_bw=HALF_BW_HZ):
    """Per-channel statistics. Floor = median over the whole 865-868 MHz band, all sweeps."""
    in_band = (freqs >= BAND_HZ[0]) & (freqs <= BAND_HZ[1])
    floor_db = float(np.median(power[:, in_band]))
    lin = 10 ** (power / 10)
    out = []
    for c, f in enumerate(channels):
        m = (freqs >= f - half_bw) & (freqs <= f + half_bw)
        per_sweep_db = 10 * np.log10(lin[:, m].mean(axis=1))
        out.append({
            "channel": c, "centre_mhz": f / 1e6,
            "mean_power_db": round(float(10 * np.log10(lin[:, m].mean())), 2),
            "above_floor_db": round(float(10 * np.log10(lin[:, m].mean())) - floor_db, 2),
            "peak_bin_db": round(float(power[:, m].max()), 2),
            "sweep_std_db": round(float(per_sweep_db.std()), 2),
            "busy_fraction": round(float(np.mean(per_sweep_db > floor_db + BUSY_THRESHOLD_DB)), 4),
        })
    return floor_db, out


def plot_scan(freqs, power, stats, floor_db, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11.5, 7.5), sharex=True,
                                 gridspec_kw={"height_ratios": [1, 1.2]})
    fm = freqs / 1e6
    a1.plot(fm, 10 * np.log10((10 ** (power / 10)).mean(axis=0)), lw=0.8, label="mean over sweeps")
    a1.plot(fm, power.max(axis=0), lw=0.6, alpha=0.6, label="max over sweeps")
    a1.axhline(floor_db, ls="--", lw=0.8, color="grey", label=f"band floor (median) {floor_db:.1f} dB")
    for s in stats:
        for ax in (a1, a2):
            ax.axvspan(s["centre_mhz"] - HALF_BW_HZ / 1e6, s["centre_mhz"] + HALF_BW_HZ / 1e6,
                       color="C2", alpha=0.12 if ax is a1 else 0.0, lw=0)
            ax.axvline(s["centre_mhz"] - HALF_BW_HZ / 1e6, color="C2", lw=0.6, alpha=0.7)
            ax.axvline(s["centre_mhz"] + HALF_BW_HZ / 1e6, color="C2", lw=0.6, alpha=0.7)
        a1.text(s["centre_mhz"], a1.get_ylim()[1], f"ch{s['channel']}\n{s['above_floor_db']:+.1f} dB",
                ha="center", va="top", fontsize=8)
    a1.set_ylabel("power (dB, rtl_power scale)")
    a1.set_title("Passive RTL-SDR scan, 865-868 MHz (no transmission). Shaded: demo channel bands")
    a1.grid(alpha=0.3)
    a1.legend(loc="lower center", bbox_to_anchor=(0.5, -0.32), ncol=3, fontsize=8, frameon=False)
    im = a2.imshow(power, aspect="auto", origin="lower", extent=[fm[0], fm[-1], 0, len(power)],
                   cmap="viridis", interpolation="nearest")
    a2.set_ylabel("sweep number")
    a2.set_xlabel("frequency (MHz)")
    fig.colorbar(im, cax=a2.inset_axes([1.01, 0, 0.015, 1]), label="dB")   # keeps both x axes aligned
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def pluto_lo_check(uri):
    """True if the Pluto TX LO is powered down, False if on, None if the Pluto can't be reached."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from run_channel_switching_demo import read_lo_powerdown
        return bool(read_lo_powerdown(uri))
    except Exception:
        return None


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--minutes", type=float, default=3.0)
    p.add_argument("--start-hz", type=float, default=864_500_000)
    p.add_argument("--stop-hz", type=float, default=868_500_000)
    p.add_argument("--bin-hz", type=float, default=2_000)
    p.add_argument("--interval-s", type=float, default=2.0, help="rtl_power integration time per sweep")
    p.add_argument("--gain", type=float, default=28.0)
    p.add_argument("--crop", type=float, default=0.3, help="rtl_power -c: drop this fraction at hop edges")
    p.add_argument("--rtl-device", type=int, default=0)
    p.add_argument("--pluto-uri", default="ip:192.168.2.1")
    p.add_argument("--allow-pluto-on", action="store_true", help="scan even if the Pluto TX LO is on")
    p.add_argument("--input", default=None, help="re-analyse an existing rtl_power CSV instead of scanning")
    return p


def main(argv=None, run=subprocess.run, lo_check=pluto_lo_check):
    a = build_parser().parse_args(argv)
    if a.input:
        csv_path = Path(a.input)
        out = csv_path.parent
    else:
        if not 0.2 <= a.minutes <= 60:
            print("  --minutes must be between 0.2 and 60.")
            return 2
        lo = lo_check(a.pluto_uri)
        if lo is False and not a.allow_pluto_on:
            print("  NOT SCANNING: the Pluto TX LO is ON, so the Pluto itself would appear in the scan.\n"
                  "  Run: iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 1")
            return 2
        print("  Pluto: " + {True: "TX LO powered down (good)", None: "not reachable (fine if unplugged)",
                             False: "TX LO ON (allowed by --allow-pluto-on)"}[lo])
        out = OUT / f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        out.mkdir(parents=True, exist_ok=True)
        csv_path = out / "rtl_power.csv"
        cmd = ["rtl_power", "-f", f"{int(a.start_hz)}:{int(a.stop_hz)}:{int(a.bin_hz)}",
               "-g", f"{a.gain:g}", "-i", f"{a.interval_s:g}", "-e", f"{int(round(a.minutes * 60))}",
               "-c", f"{a.crop:g}", "-d", str(a.rtl_device), str(csv_path)]
        print(f"  Receive only. Scanning {a.start_hz / 1e6:.1f}-{a.stop_hz / 1e6:.1f} MHz for "
              f"{a.minutes:g} min:\n    " + " ".join(cmd), flush=True)
        r = run(cmd)
        if getattr(r, "returncode", 0) != 0 and not csv_path.exists():
            print("  rtl_power failed (is the RTL-SDR plugged in and not used by another program?)")
            return 1
    freqs, power, times = parse_rtl_power(csv_path)
    floor_db, stats = channel_stats(freqs, power)
    plot_scan(freqs, power, stats, floor_db, out / "scan.png")
    rec = {"input": str(csv_path.name), "sweeps": len(power), "first_sweep": times[0], "last_sweep": times[-1],
           "freq_range_mhz": [round(freqs[0] / 1e6, 4), round(freqs[-1] / 1e6, 4)],
           "bin_hz": round(float(np.median(np.diff(freqs))), 1), "gain_db": a.gain,
           "band_floor_db": round(floor_db, 2), "busy_threshold_db": BUSY_THRESHOLD_DB,
           "channel_half_bandwidth_hz": HALF_BW_HZ, "channels": stats,
           "note": "Receive only; rtl_power dB scale is relative (uncalibrated)."}
    (out / "summary.json").write_text(json.dumps(rec, indent=2))
    print(f"\n  {len(power)} sweeps, band floor {floor_db:.1f} dB (relative)")
    for s in stats:
        print(f"    ch{s['channel']} {s['centre_mhz']:.1f} MHz: {s['above_floor_db']:+.2f} dB vs floor, "
              f"sweep-to-sweep std {s['sweep_std_db']:.2f} dB, busy {100 * s['busy_fraction']:.1f} % of sweeps")
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"  Results: {shown}/ (rtl_power.csv, scan.png, summary.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
