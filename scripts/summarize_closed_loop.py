#!/usr/bin/env python3
"""Summarise all real-radio closed-loop sessions (results/hardware/closed_loop/session_*/).

Per session: rounds, switches, switches needed by the schedule, switch latency,
unnecessary switches, best-channel rounds, data BER. Pooled per safety margin:
the same with exact 95 % Clopper-Pearson intervals, and BER per modulation
against AWGN theory at the measured data Es/N0.

  python scripts/summarize_closed_loop.py
  python scripts/summarize_closed_loop.py --sessions results/hardware/closed_loop   # default

Outputs:
  results/analysis/closed_loop_sessions.csv     one row per session
  results/analysis/closed_loop_summary.json     pooled per margin, per modulation
  results/figures/closed_loop_repeatability.png per-modulation BER with 95 % CI vs theory
Only sessions with mode "real_radios" and no error are counted; others are listed as skipped.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from summarize_hardware_sweep import clopper_pearson, theory_ber  # noqa: E402

MODS = ["BPSK", "QPSK", "16-QAM"]


def _f(x):
    return None if x in ("", None, "None") else float(x)


def load_session(folder):
    rec = json.loads((folder / "session.json").read_text())
    rows = []
    if (folder / "rounds.csv").exists():
        with open(folder / "rounds.csv", newline="") as f:
            rows = list(csv.DictReader(f))
    return rec, rows


def analyse_session(rec, rows):
    n_ch = len(rec["channels_hz"])
    rpp = int(rec["rounds_per_phase"])
    sched = rec["schedule"]
    needed, latencies, unnecessary, best_ok = 0, [], 0, 0
    prev_best = 0  # controller starts on channel 0
    for p, phase in enumerate(sched):
        best = int(np.argmin(phase["attenuation_db"]))
        prow = rows[p * rpp:(p + 1) * rpp]
        if not prow:
            break
        if best != prev_best:
            needed += 1
            lat = next((i for i, r in enumerate(prow) if int(r["channel"]) == best), None)
            latencies.append(lat)
        for i, r in enumerate(prow):
            if r["action"] == "switch_channel" and not (best != prev_best and i == latencies[-1]):
                unnecessary += 1
        prev_best = best
    for r in rows:
        es = [_f(r[f"esn0_ch{c}_db"]) for c in range(n_ch)]
        es = [-99 if e is None else e for e in es]
        best_ok += int(int(r["channel"]) == int(np.argmax(es)))
    per_mod = {}
    for r in rows:
        m = r["modulation"]
        d = per_mod.setdefault(m, {"rounds": 0, "errors": 0, "bits": 0, "esn0": []})
        d["rounds"] += 1
        d["errors"] += int(_f(r["data_bit_errors"]) or 0)
        d["bits"] += int(_f(r["data_bits"]) or 0)
        if _f(r["data_esn0_db"]) is not None:
            d["esn0"].append(_f(r["data_esn0_db"]))
    errs = sum(d["errors"] for d in per_mod.values())
    bits = sum(d["bits"] for d in per_mod.values())
    return {
        "session": rec["timestamp"], "margin_db": float(rec["controller"].get("margin_db", 0.0)),
        "switch_penalty": rec["controller"]["switch_penalty"], "phases": len(sched), "rounds": len(rows),
        "switches": sum(r["action"] == "switch_channel" for r in rows), "switches_needed": needed,
        "switches_made_when_needed": sum(1 for x in latencies if x is not None),
        "max_switch_latency_rounds": max([x for x in latencies if x is not None], default=None),
        "unnecessary_switches": unnecessary, "best_channel_rounds": best_ok,
        "data_bit_errors": errs, "data_bits": bits, "data_ber": errs / bits if bits else None,
        "modulations": ";".join(f"{m}:{per_mod[m]['rounds']}" for m in MODS if m in per_mod),
        "_per_mod": per_mod,
    }


def pool(sessions):
    out = {}
    for margin in sorted({s["margin_db"] for s in sessions}):
        ss = [s for s in sessions if s["margin_db"] == margin]
        rounds = sum(s["rounds"] for s in ss)
        best = sum(s["best_channel_rounds"] for s in ss)
        errs = sum(s["data_bit_errors"] for s in ss)
        bits = sum(s["data_bits"] for s in ss)
        mods = {}
        for m in MODS:
            e = sum(s["_per_mod"].get(m, {}).get("errors", 0) for s in ss)
            b = sum(s["_per_mod"].get(m, {}).get("bits", 0) for s in ss)
            es = [x for s in ss for x in s["_per_mod"].get(m, {}).get("esn0", [])]
            if not b:
                continue
            lo, hi = clopper_pearson(e, b)
            mean_es = float(np.mean(es)) if es else None
            mods[m] = {"rounds": sum(s["_per_mod"].get(m, {}).get("rounds", 0) for s in ss),
                       "errors": e, "bits": b, "ber": e / b, "ber_ci95": [lo, hi],
                       "mean_data_esn0_db": None if mean_es is None else round(mean_es, 2),
                       # BER is convex in Es/N0, so average the per-round theory rather than use theory(mean)
                       "theory_ber_at_mean_esn0": None if not es else float(np.mean([theory_ber(m, x) for x in es]))}
        blo, bhi = clopper_pearson(best, rounds)
        lo, hi = clopper_pearson(errs, bits) if bits else (None, None)
        out[f"margin_{margin:g}_db"] = {
            "sessions": [s["session"] for s in ss], "rounds": rounds,
            "best_channel_rounds": best, "best_channel_rate": best / rounds, "best_channel_ci95": [blo, bhi],
            "switches": sum(s["switches"] for s in ss),
            "switches_needed": sum(s["switches_needed"] for s in ss),
            "switches_made_when_needed": sum(s["switches_made_when_needed"] for s in ss),
            "unnecessary_switches": sum(s["unnecessary_switches"] for s in ss),
            "data_bit_errors": errs, "data_bits": bits, "data_ber": errs / bits if bits else None,
            "data_ber_ci95": [lo, hi], "per_modulation": mods}
    return out


def plot(pooled, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.8))
    keys = list(pooled)
    w = 0.8 / max(len(keys), 1)
    for k_i, k in enumerate(keys):
        for m_i, m in enumerate(MODS):
            d = pooled[k]["per_modulation"].get(m)
            if not d:
                continue
            x = m_i + (k_i - (len(keys) - 1) / 2) * w
            y = max(d["ber"], 1e-6)
            lo, hi = max(d["ber_ci95"][0], 1e-6), max(d["ber_ci95"][1], 1e-6)
            ax.errorbar(x, y, yerr=[[y - lo], [hi - y]], fmt="o", color=f"C{k_i}", capsize=4,
                        label=k.replace("_", " ").replace(" db", " dB"))
            if d["theory_ber_at_mean_esn0"] is not None:
                ax.plot(x, max(d["theory_ber_at_mean_esn0"], 1e-6), "x", color="k", ms=8)
            ax.annotate(f"{d['errors']}/{d['bits']}\n@{d['mean_data_esn0_db']} dB", (x, hi), fontsize=7,
                        ha="center", va="bottom", xytext=(0, 3), textcoords="offset points")
    ax.plot([], [], "x", color="k", label="AWGN theory at each burst's average Es/N0 (mean over rounds)")
    h, lab = ax.get_legend_handles_labels()
    seen = {}
    for hh, ll in zip(h, lab):
        seen.setdefault(ll, hh)
    ax.legend(seen.values(), seen.keys(), loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3,
              fontsize=8, frameon=False)
    ax.set_yscale("log")
    ax.set_ylim(5e-7, 1)
    ax.set_xticks(range(len(MODS)), MODS)
    ax.set_ylabel("data BER (95 % CI; 0 errors plotted at 1e-6)")
    ax.set_title("Closed-loop demo on real radios: data BER per chosen modulation")
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessions", default=str(ROOT / "results" / "hardware" / "closed_loop"))
    ap.add_argument("--out-dir", default=str(ROOT / "results"))
    a = ap.parse_args(argv)
    sessions, skipped = [], []
    for folder in sorted(Path(a.sessions).glob("session_*")):
        if not (folder / "session.json").exists():
            skipped.append((folder.name, "no session.json"))
            continue
        rec, rows = load_session(folder)
        if rec.get("mode") != "real_radios":
            skipped.append((folder.name, f"mode {rec.get('mode')}"))
        elif rec.get("error"):
            skipped.append((folder.name, f"error: {rec['error']}"))
        elif not rows:
            skipped.append((folder.name, "no rounds"))
        else:
            sessions.append(analyse_session(rec, rows))
    for name, why in skipped:
        print(f"  skipped {name}: {why}")
    if not sessions:
        print("  No complete real-radio sessions found.")
        return 1
    out = Path(a.out_dir)
    (out / "analysis").mkdir(parents=True, exist_ok=True)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    cols = [k for k in sessions[0] if not k.startswith("_")]
    with open(out / "analysis" / "closed_loop_sessions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in sessions:
            w.writerow({k: s[k] for k in cols})
    pooled = pool(sessions)
    (out / "analysis" / "closed_loop_summary.json").write_text(json.dumps(
        {"sessions_counted": len(sessions), "skipped": [f"{n}: {w}" for n, w in skipped], "by_margin": pooled},
        indent=2))
    plot(pooled, out / "figures" / "closed_loop_repeatability.png")
    print(f"\n  {len(sessions)} real-radio sessions")
    for s in sessions:
        print(f"    {s['session']} margin {s['margin_db']:g} dB: {s['rounds']} rounds, switches {s['switches']} "
              f"(needed {s['switches_needed']}, unnecessary {s['unnecessary_switches']}), best channel "
              f"{s['best_channel_rounds']}/{s['rounds']}, BER {s['data_bit_errors']}/{s['data_bits']}, {s['modulations']}")
    for k, p in pooled.items():
        print(f"\n  {k}: best channel {p['best_channel_rounds']}/{p['rounds']} "
              f"(95 % CI {p['best_channel_ci95'][0]:.3f}-{p['best_channel_ci95'][1]:.3f}); "
              f"switches made when needed {p['switches_made_when_needed']}/{p['switches_needed']}, "
              f"unnecessary {p['unnecessary_switches']}")
        for m, d in p["per_modulation"].items():
            print(f"    {m:6s} {d['rounds']:3d} rounds  BER {d['errors']}/{d['bits']} = {d['ber']:.2e} "
                  f"(CI {d['ber_ci95'][0]:.1e}-{d['ber_ci95'][1]:.1e}); mean data Es/N0 {d['mean_data_esn0_db']} dB, "
                  f"AWGN theory {d['theory_ber_at_mean_esn0']:.1e}")
    print("\n  Wrote results/analysis/closed_loop_sessions.csv, closed_loop_summary.json, "
          "results/figures/closed_loop_repeatability.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
