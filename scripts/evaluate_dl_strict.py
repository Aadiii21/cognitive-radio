#!/usr/bin/env python3
"""Stricter evaluation of the trained CNN (results/dl/modulation_cnn.pt). No training.

    python scripts/evaluate_dl_strict.py

1. Capture-level bootstrap: the 536 real windows come from 19 captures and are
   not independent, so the 95 % interval resamples whole captures.
2. Confidence: how sure the network is when it is right and when it is wrong.
3. A second unseen frame format: the payloads of the BPSK frame v2 captures
   (64-chip preamble + 512 BPSK symbols, gain 28 dB and 40 dB). The CNN never saw
   this format, and the 40 dB capture includes one damaged frame.

Outputs: results/dl/strict_evaluation.json, results/dl/bpsk_v2_predictions.csv
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.dl.modulation_classifier import (CLASSES, SPS, build_model, load_cu8, predict,  # noqa: E402
                                          real_dataset, to_tensor_array, windows_from)
from src.radio.bpsk_receiver import convert_rate  # noqa: E402
from src.radio.multimod_receiver import estimate_dc  # noqa: E402

OUT = ROOT / "results" / "dl"
PREAMBLE_SYMBOLS = 64
BOOT = 10_000


def load_model():
    import torch
    ck = torch.load(OUT / "modulation_cnn.pt", map_location="cpu", weights_only=True)
    m = build_model()
    m.load_state_dict(ck["state_dict"])
    m.eval()
    return m


def bootstrap(rows, correct, seed=0):
    rng = np.random.default_rng(seed)
    caps = sorted({r["capture"] for r in rows})
    by = {c: np.array([ok for r, ok in zip(rows, correct) if r["capture"] == c]) for c in caps}
    stats = []
    for _ in range(BOOT):
        pick = rng.choice(len(caps), len(caps), replace=True)
        allv = np.concatenate([by[caps[i]] for i in pick])
        stats.append(allv.mean())
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(lo), float(hi)


def bpsk_v2_windows():
    X, rows = [], []
    for rp in sorted((ROOT / "results/hardware/experiment_results").glob("*.json")):
        rec = json.loads(rp.read_text())
        if rec.get("waveform_format") != "bpsk_frame_v2" or not rec.get("receiver"):
            continue
        cap = ROOT / "results/hardware/captures" / Path(rec["rx_capture_file"]).name
        wm = Path(rec["waveform_metadata"])
        wm = ROOT / wm if not wm.is_absolute() else ROOT / "results/baseband/prepared" / wm.name
        meta = json.loads(wm.read_text())
        n_payload = (meta["burst_symbols"] - PREAMBLE_SYMBOLS) * SPS
        x = load_cu8(cap)
        x = x - estimate_dc(x)
        x, *_ = convert_rate(x, float(rec["tx_sample_rate_hz_used"]), float(rec["rx_sample_rate_hz_used"]))
        for k, fr in enumerate(rec["receiver"]["frames"]):
            start = int(fr["start_sample"]) + PREAMBLE_SYMBOLS * SPS
            for w in windows_from(x, start, n_payload):
                X.append(w)
                rows.append({"capture": cap.name, "rx_gain_db": rec["rx"]["gain_db"], "frame": k,
                             "esn0_db": round(float(fr["snr_db"]), 2), "frame_ber": float(fr["ber"])})
    return (to_tensor_array(X) if X else np.zeros((0, 2, 512), np.float32)), rows


def main():
    model = load_model()
    X, y, rows = real_dataset(ROOT)
    p = predict(model, X)
    pred, conf = p.argmax(1), p.max(1)
    ok = pred == y
    lo, hi = bootstrap(rows, ok)
    frames = {}
    for r, pr in zip(rows, pred):
        frames.setdefault((r["capture"], r["frame"]), [r["modulation"], np.zeros(3, int)])[1][pr] += 1
    wrong = conf[~ok]
    real = {
        "windows": int(len(y)), "captures": len({r["capture"] for r in rows}), "frames": len(frames),
        "window_accuracy": round(float(ok.mean()), 4),
        "window_accuracy_capture_bootstrap_ci95": [round(lo, 4), round(hi, 4)],
        "frame_vote_accuracy": round(float(np.mean([CLASSES[int(v.argmax())] == m for m, v in frames.values()])), 4),
        "errors": int((~ok).sum()),
        "errors_esn0_db_max": round(float(max(r["esn0_db"] for r, o in zip(rows, ok) if not o)), 2) if (~ok).any() else None,
        "confidence_when_correct_median": round(float(np.median(conf[ok])), 4),
        "confidence_when_wrong_median": round(float(np.median(wrong)), 4) if len(wrong) else None,
        "wrong_with_confidence_over_0.9": int((wrong > 0.9).sum()),
        "windows_with_confidence_over_0.9": int((conf > 0.9).sum()),
        "accuracy_when_confidence_over_0.9": round(float(ok[conf > 0.9].mean()), 4),
    }

    Xb, rb = bpsk_v2_windows()
    v2 = {"windows": 0}
    if len(Xb):
        pb = predict(model, Xb)
        predb, confb = pb.argmax(1), pb.max(1)
        with open(OUT / "bpsk_v2_predictions.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rb[0]) + ["cnn_pred", "cnn_conf"])
            w.writeheader()
            for r, a, c in zip(rb, predb, confb):
                w.writerow({**r, "cnn_pred": CLASSES[a], "cnn_conf": round(float(c), 4)})
        okb = predb == 0
        clean = np.array([r["frame_ber"] < 0.01 for r in rb])
        v2 = {"windows": int(len(rb)), "frames": len({(r["capture"], r["frame"]) for r in rb}),
              "accuracy_all": round(float(okb.mean()), 4),
              "accuracy_decodable_frames": round(float(okb[clean].mean()), 4) if clean.any() else None,
              "accuracy_damaged_frames": round(float(okb[~clean].mean()), 4) if (~clean).any() else None,
              "per_frame": [{"capture": r["capture"], "rx_gain_db": r["rx_gain_db"], "frame": r["frame"],
                             "esn0_db": r["esn0_db"], "frame_ber": r["frame_ber"]}
                            for r in {(r["capture"], r["frame"]): r for r in rb}.values()]}
        for fr in v2["per_frame"]:
            sel = [i for i, r in enumerate(rb) if r["capture"] == fr["capture"] and r["frame"] == fr["frame"]]
            fr["windows"] = len(sel)
            fr["bpsk_windows"] = int(okb[sel].sum())
    res = {"multimod_real_ota": real, "bpsk_frame_v2_unseen_format": v2}
    (OUT / "strict_evaluation.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
