#!/usr/bin/env python3
"""Train and evaluate the DL modulation classifier (src/dl/modulation_classifier.py).

    python scripts/train_modulation_classifier.py            # ~5-10 min on a laptop CPU
    python scripts/train_modulation_classifier.py --quick    # small run, for a smoke test

Train: synthetic windows through a simulated RTL-SDR chain (random payloads).
Test 1: fresh synthetic windows at fixed Es/N0 (0..24 dB) -> accuracy vs Es/N0.
Test 2: the real OTA captures from 23 Nov (never seen in training).
Baseline: random forest on higher-order cumulant features, same data.

Outputs in results/dl/:
  modulation_cnn.pt               trained weights
  training_history.csv            loss / accuracy per epoch
  metrics.json                    all headline numbers
  accuracy_vs_esn0.csv / .png     synthetic accuracy curve, CNN vs baseline, real points
  confusion_synthetic.png         CNN on synthetic test set
  confusion_real.png              CNN on real OTA windows
  real_predictions.csv            one row per real window (capture, frame, Es/N0, prediction)
  real_by_capture.csv             per-capture accuracy and majority vote
"""
import argparse
import csv
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.dl.modulation_classifier import (CLASSES, build_model, cumulant_features, predict,  # noqa: E402
                                          real_dataset, synthetic_dataset)

OUT = ROOT / "results" / "dl"
TEST_ESN0 = list(range(0, 25, 2))


def _chunk(args):
    n, seed, esn0 = args
    return synthetic_dataset(n, seed=seed, esn0_db=esn0)


def make_synthetic(n_per_class, seed, workers, esn0=None):
    per = max(1, n_per_class // workers)
    jobs = [(per, seed * 1000 + i, esn0) for i in range(workers)]
    with Pool(workers) as p:
        parts = p.map(_chunk, jobs)
    return tuple(np.concatenate([part[i] for part in parts]) for i in range(3))


def train(model, X, y, epochs, seed):
    import torch
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(X))
    n_val = len(X) // 10
    val, tr = idx[:n_val], idx[n_val:]
    Xt, yt = torch.from_numpy(X), torch.from_numpy(y)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=epochs * ((len(tr) + 255) // 256))
    loss_fn = torch.nn.CrossEntropyLoss()
    hist = []
    for ep in range(epochs):
        model.train()
        perm = rng.permutation(tr)
        tot = correct = 0.0
        for i in range(0, len(perm), 256):
            b = perm[i:i + 256]
            xb = Xt[b]
            # augmentation: random phase rotation and I/Q-order-preserving conjugation
            th = torch.rand(len(b), 1) * 2 * np.pi
            c, s = torch.cos(th), torch.sin(th)
            xb = torch.stack([xb[:, 0] * c - xb[:, 1] * s, xb[:, 0] * s + xb[:, 1] * c], 1)
            if rng.random() < 0.5:
                xb = torch.stack([xb[:, 0], -xb[:, 1]], 1)
            opt.zero_grad()
            out = model(xb)
            loss = loss_fn(out, yt[b])
            loss.backward()
            opt.step()
            sched.step()
            tot += loss.item() * len(b)
            correct += (out.argmax(1) == yt[b]).sum().item()
        p = predict(model, X[val])
        va = float((p.argmax(1) == y[val]).mean())
        hist.append({"epoch": ep + 1, "train_loss": tot / len(tr), "train_acc": correct / len(tr), "val_acc": va})
        print(f"  epoch {ep + 1:2d}: loss {tot / len(tr):.4f}  train {correct / len(tr):.3f}  val {va:.3f}")
    return hist


def confusion(y_true, y_pred):
    m = np.zeros((len(CLASSES), len(CLASSES)), int)
    for t, p in zip(y_true, y_pred):
        m[t, p] += 1
    return m


def plot_confusion(m, title, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(4.2, 3.6))
    norm = m / np.maximum(m.sum(1, keepdims=True), 1)
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    for i in range(len(CLASSES)):
        for j in range(len(CLASSES)):
            ax.text(j, i, f"{m[i, j]}\n{100 * norm[i, j]:.0f}%", ha="center", va="center",
                    color="white" if norm[i, j] > 0.6 else "black", fontsize=9)
    ax.set_xticks(range(3), CLASSES)
    ax.set_yticks(range(3), CLASSES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--per-class", type=int, default=8000, help="synthetic training windows per class")
    ap.add_argument("--test-per-class", type=int, default=300, help="synthetic test windows per class per Es/N0")
    ap.add_argument("--epochs", type=int, default=14)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv)
    if a.quick:
        a.per_class, a.test_per_class, a.epochs = 600, 40, 3
    import torch
    torch.set_num_threads(max(1, a.workers))
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print(f"Synthetic training set: {a.per_class} windows/class ...")
    X, y, e = make_synthetic(a.per_class, a.seed, a.workers)
    print(f"  {len(X)} windows, Es/N0 {e.min():.1f}-{e.max():.1f} dB ({time.time() - t0:.0f} s)")

    model = build_model()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"CNN: {n_params} parameters. Training {a.epochs} epochs ...")
    hist = train(model, X, y, a.epochs, a.seed)
    torch.save({"state_dict": model.state_dict(), "classes": CLASSES}, OUT / "modulation_cnn.pt")
    with open(OUT / "training_history.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(hist[0]))
        w.writeheader()
        w.writerows(hist)

    print("Baseline: random forest on cumulant features ...")
    from sklearn.ensemble import RandomForestClassifier
    rf = RandomForestClassifier(n_estimators=300, random_state=a.seed, n_jobs=a.workers)
    rf.fit(cumulant_features(X), y)

    print("Synthetic test at fixed Es/N0 ...")
    curve, all_t, all_p = [], [], []
    for k, snr in enumerate(TEST_ESN0):
        Xs, ys, _ = make_synthetic(a.test_per_class, 10_000 + k, a.workers, esn0=snr)
        pc = predict(model, Xs).argmax(1)
        pb = rf.predict(cumulant_features(Xs))
        all_t.append(ys), all_p.append(pc)
        row = {"esn0_db": snr, "cnn_acc": float((pc == ys).mean()), "baseline_acc": float((pb == ys).mean())}
        for ci, cname in enumerate(CLASSES):
            row[f"cnn_acc_{cname}"] = float((pc[ys == ci] == ci).mean())
        curve.append(row)
        print(f"  {snr:2d} dB: CNN {row['cnn_acc']:.3f}  baseline {row['baseline_acc']:.3f}")
    with open(OUT / "accuracy_vs_esn0.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(curve[0]))
        w.writeheader()
        w.writerows(curve)
    syn_t, syn_p = np.concatenate(all_t), np.concatenate(all_p)
    plot_confusion(confusion(syn_t, syn_p), "CNN, synthetic test (0-24 dB)", OUT / "confusion_synthetic.png")

    print("Real OTA captures ...")
    Xr, yr, rows = real_dataset(ROOT)
    real = {}
    if len(Xr):
        pr = predict(model, Xr)
        pred = pr.argmax(1)
        pb = rf.predict(cumulant_features(Xr))
        plot_confusion(confusion(yr, pred), f"CNN, real OTA windows (n={len(yr)})", OUT / "confusion_real.png")
        with open(OUT / "real_predictions.csv", "w", newline="") as f:
            fields = list(rows[0]) + ["true", "cnn_pred", "cnn_conf", "baseline_pred"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r, t, p, pp, b in zip(rows, yr, pred, pr, pb):
                w.writerow({**r, "true": CLASSES[t], "cnn_pred": CLASSES[p], "cnn_conf": round(float(pp.max()), 4),
                            "baseline_pred": CLASSES[b]})
        caps = {}
        for r, t, p in zip(rows, yr, pred):
            c = caps.setdefault(r["capture"], {"capture": r["capture"], "modulation": r["modulation"],
                                               "pluto_attenuation_db": r["pluto_attenuation_db"],
                                               "esn0": [], "n": 0, "correct": 0, "votes": np.zeros(3, int)})
            c["esn0"].append(r["esn0_db"]); c["n"] += 1; c["correct"] += int(p == t); c["votes"][p] += 1
        cap_rows = []
        for c in sorted(caps.values(), key=lambda c: (CLASSES.index(c["modulation"]), -np.mean(c["esn0"]))):
            cap_rows.append({"capture": c["capture"], "modulation": c["modulation"],
                             "pluto_attenuation_db": c["pluto_attenuation_db"],
                             "mean_esn0_db": round(float(np.mean(c["esn0"])), 2), "windows": c["n"],
                             "window_acc": round(c["correct"] / c["n"], 4),
                             "majority_vote": CLASSES[int(c["votes"].argmax())],
                             "vote_correct": CLASSES[int(c["votes"].argmax())] == c["modulation"]})
        with open(OUT / "real_by_capture.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(cap_rows[0]))
            w.writeheader()
            w.writerows(cap_rows)
        frame_ok = {}
        for r, p in zip(rows, pred):
            frame_ok.setdefault((r["capture"], r["frame"]), [r["modulation"], np.zeros(3, int)])[1][p] += 1
        real = {
            "windows": int(len(yr)), "captures": len(cap_rows),
            "frames": len(frame_ok),
            "cnn_window_acc": float((pred == yr).mean()),
            "cnn_window_acc_per_class": {c: float((pred[yr == i] == i).mean()) for i, c in enumerate(CLASSES)
                                         if (yr == i).any()},
            "cnn_frame_vote_acc": float(np.mean([CLASSES[int(v.argmax())] == m for m, v in frame_ok.values()])),
            "cnn_capture_vote_acc": float(np.mean([r["vote_correct"] for r in cap_rows])),
            "baseline_window_acc": float((pb == yr).mean()),
            "esn0_range_db": [float(min(r["esn0_db"] for r in rows)), float(max(r["esn0_db"] for r in rows))],
        }
        print(f"  CNN window acc {real['cnn_window_acc']:.3f} | frame vote {real['cnn_frame_vote_acc']:.3f} | "
              f"capture vote {real['cnn_capture_vote_acc']:.3f} | baseline {real['baseline_window_acc']:.3f}")
    else:
        print("  no real captures found; skipped")

    _plot_curve(curve, OUT / "accuracy_vs_esn0.png", OUT / "real_by_capture.csv")
    metrics = {
        "model": "1-D CNN (6 conv layers, global average pooling)", "parameters": int(n_params),
        "input": "512 IQ samples (128 symbols) on the 2.083 MS/s TX grid, unit RMS, no CFO/phase correction",
        "train_windows": int(len(X)), "epochs": a.epochs, "final_val_acc": hist[-1]["val_acc"],
        "synthetic_test": {"windows_per_class_per_snr": a.test_per_class,
                           "overall_cnn_acc": float((syn_t == syn_p).mean()), "curve": curve},
        "real_ota": real, "runtime_s": round(time.time() - t0, 1), "quick": a.quick,
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"Done in {time.time() - t0:.0f} s. Outputs in {OUT.relative_to(ROOT)}/")


def _plot_curve(curve, path, cap_csv):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    s = [r["esn0_db"] for r in curve]
    ax.plot(s, [r["cnn_acc"] for r in curve], "o-", color="#2E7D57", label="CNN, synthetic")
    ax.plot(s, [r["baseline_acc"] for r in curve], "s--", color="#888888", label="Cumulant + random forest, synthetic")
    if cap_csv.exists():
        with open(cap_csv) as f:
            caps = list(csv.DictReader(f))
        marks = {"BPSK": "^", "QPSK": "D", "16QAM": "v"}
        for m in CLASSES:
            pts = [(float(c["mean_esn0_db"]), float(c["window_acc"])) for c in caps if c["modulation"] == m]
            if pts:
                ax.scatter(*zip(*pts), marker=marks[m], s=46, color="#B8621B", edgecolor="black", linewidth=0.5,
                           zorder=3, label=f"CNN, real OTA capture ({m})")
    ax.axhline(1 / 3, color="#bbbbbb", lw=0.8, ls=":")
    ax.set_xlabel("Es/N0 (dB)")
    ax.set_ylabel("Classification accuracy")
    ax.set_ylim(0.25, 1.02)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")
    ax.set_title("Modulation classification accuracy vs Es/N0", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    main()
