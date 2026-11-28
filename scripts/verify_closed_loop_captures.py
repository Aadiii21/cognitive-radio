#!/usr/bin/env python3
"""Offline audit of real closed-loop sessions (no hardware).

For every complete real-radio session in results/hardware/closed_loop/:
  1. RE-DECODE  every saved raw capture (.cu8) with the same receiver and compare
                Es/N0, frame count and bit errors with rounds.csv.
  2. READBACK   check every capture sidecar: the Pluto LO, gain and rate read back
                during the burst match the frequency / attenuation of that burst.
  3. REPLAY     feed the logged probe Es/N0 values to a fresh controller and check
                it makes the same channel / modulation / action in every round.

  python scripts/verify_closed_loop_captures.py
  python scripts/verify_closed_loop_captures.py --sessions DIR   # e.g. an unpacked backup

Raw captures are large and are kept out of git; without them step 1 is reported as
"not available" and steps 2-3 still run. Output: results/analysis/closed_loop_verification.json
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import run_channel_switching_demo as demo  # noqa: E402
from src.calibrated_controller import CalibratedCognitiveController  # noqa: E402

hx = demo.hx


def _f(x):
    return None if x in ("", None, "None") else float(x)


def load_waveforms():
    return {m: hx.load_waveform(demo.WAVEFORM_DIR / f) for m, f in demo.WAVEFORMS.items()}


def capture_tags(row, n_ch):
    r = int(row["round"])
    tags = [(f"r{r:02d}_probe_ch{c}", "BPSK", c) for c in range(n_ch)]
    tags.append((f"r{r:02d}_data_ch{row['channel']}_{row['modulation']}", row["modulation"], int(row["channel"])))
    return tags


def redecode(cap_dir, tag, modulation, waveforms):
    raw_path, side_path = cap_dir / f"{tag}.cu8", cap_dir / f"{tag}.json"
    if not raw_path.exists():
        return None
    side = json.loads(side_path.read_text())
    raw = np.fromfile(raw_path, dtype=np.uint8)
    _, _, spec = waveforms[modulation]
    _, d = hx.process_capture(hx.unpack_rtl_u8(raw), spec, side["tx_sample_rate_hz"], side["rx_sample_rate_hz"], 0.6)
    return demo.frame_stats(d)


def check_readback(side, freq_hz, att_db):
    rb = side.get("tx_readback") or {}
    probs = []
    if abs(float(rb.get("tx_lo_hz", -1)) - freq_hz) > 1:
        probs.append(f"LO {rb.get('tx_lo_hz')} != {freq_hz}")
    if abs(float(rb.get("tx_hardwaregain_db", 1)) + float(att_db)) > 0.25:
        probs.append(f"gain {rb.get('tx_hardwaregain_db')} != -{att_db}")
    if abs(float(rb.get("tx_sample_rate_hz", 0)) - demo.TX_RATE) > 5:
        probs.append(f"rate {rb.get('tx_sample_rate_hz')}")
    if abs(float(side.get("rx_center_frequency_hz", -1)) - freq_hz) > 1:
        probs.append("RX frequency mismatch")
    return probs


def verify_session(folder, waveforms, tol_db=0.02):
    rec = json.loads((folder / "session.json").read_text())
    with open(folder / "rounds.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    chans = rec["channels_hz"]
    n_ch = len(chans)
    cap_dir = folder / "captures"
    ctl = rec["controller"]
    margin = float(ctl.get("margin_db", 0.0))
    controller = CalibratedCognitiveController(initial_channel=0, switch_delay_steps=ctl["switch_delay_steps"],
                                               switch_penalty=ctl["switch_penalty"],
                                               min_utility_gain=ctl["min_utility_gain"])
    out = {"session": rec["timestamp"], "margin_db": margin, "rounds": len(rows), "captures_checked": 0,
           "captures_missing": 0, "decode_mismatches": [], "readback_problems": [], "replay_mismatches": [],
           "max_esn0_diff_db": 0.0}
    for row in rows:
        # replay the decision from the logged probe measurements
        es = [_f(row[f"esn0_ch{c}_db"]) for c in range(n_ch)]
        dec = controller.decide([demo.esn0_to_controller_snr(e, margin) for e in es])
        got = (dec.channel, dec.modulation, dec.action)
        want = (int(row["channel"]), row["modulation"], row["action"])
        if got != want:
            out["replay_mismatches"].append({"round": row["round"], "replayed": got, "logged": want})
        for tag, mod, c in capture_tags(row, n_ch):
            side_path = cap_dir / f"{tag}.json"
            if not side_path.exists():
                out["captures_missing"] += 1
                continue
            side = json.loads(side_path.read_text())
            att = row[f"att_ch{c}_db"]
            for p in check_readback(side, chans[c], float(att)):
                out["readback_problems"].append(f"{tag}: {p}")
            fs = redecode(cap_dir, tag, mod, waveforms)
            if fs is None:
                continue
            out["captures_checked"] += 1
            if "probe" in tag:
                logged = (_f(row[f"esn0_ch{c}_db"]), int(float(row[f"frames_ch{c}"] or 0)), None)
            else:
                logged = (_f(row["data_esn0_db"]), int(float(row["data_frames"] or 0)),
                          None if _f(row["data_bit_errors"]) is None else int(float(row["data_bit_errors"])))
            new = (fs["esn0_db"], fs["frames"], None if "probe" in tag else fs["bit_errors"])
            diff = 0.0 if logged[0] is None and new[0] is None else (
                np.inf if (logged[0] is None) != (new[0] is None) else abs(logged[0] - new[0]))
            out["max_esn0_diff_db"] = max(out["max_esn0_diff_db"], float(diff))
            if diff > tol_db or logged[1] != new[1] or logged[2] != new[2]:
                out["decode_mismatches"].append({"tag": tag, "logged": logged, "redecoded": new})
    out["ok"] = not (out["decode_mismatches"] or out["readback_problems"] or out["replay_mismatches"])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessions", default=str(ROOT / "results" / "hardware" / "closed_loop"))
    ap.add_argument("--out", default=str(ROOT / "results" / "analysis" / "closed_loop_verification.json"))
    a = ap.parse_args(argv)
    waveforms = load_waveforms()
    results = []
    for folder in sorted(Path(a.sessions).glob("session_*")):
        if not (folder / "rounds.csv").exists():
            continue
        rec = json.loads((folder / "session.json").read_text())
        if rec.get("mode") != "real_radios" or rec.get("error"):
            continue
        r = verify_session(folder, waveforms)
        results.append(r)
        print(f"  {r['session']}: {r['rounds']} rounds; re-decoded {r['captures_checked']} captures "
              f"(max Es/N0 difference {r['max_esn0_diff_db']:.3f} dB), {len(r['decode_mismatches'])} decode "
              f"mismatches, {len(r['readback_problems'])} readback problems, "
              f"{len(r['replay_mismatches'])} decision replay mismatches -> {'OK' if r['ok'] else 'CHECK'}")
    if not results:
        print("  No complete real-radio sessions found.")
        return 1
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"sessions": results, "all_ok": all(r["ok"] for r in results)}, indent=2,
                                      default=str))
    print(f"  {'ALL OK' if all(r['ok'] for r in results) else 'PROBLEMS FOUND'}; wrote {a.out}")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
