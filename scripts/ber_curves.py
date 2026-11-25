#!/usr/bin/env python3
"""
BER-vs-Es/N0 curves for the multimod receiver, and controller thresholds.

Evidence level: SYNTHETIC AWGN. The channel is simulated (cyclic frames,
2.083333 -> 2.048 MS/s, CFO, random phase, AWGN). These curves calibrate the
controller against this receiver's own SNR estimate; they are not hardware
measurements. Re-run the same procedure on conducted captures to calibrate
against the real link.

    python scripts/ber_curves.py                       # default grid, target BER 1e-3
    python scripts/ber_curves.py --target-ber 1e-4 --captures 5

Writes:
    results/analysis/ber_vs_snr_multimod_synthetic.csv
    results/analysis/controller_thresholds_synthetic.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly
from scipy.special import erfc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.radio.cognitive_controller import CognitiveRadioController  # noqa: E402
from src.radio.multimod_frame import build_framed_waveform  # noqa: E402
from src.radio.multimod_receiver import MultimodFrameSpec, receive_multimod  # noqa: E402

TX, RX = 2_083_333.0, 2_048_000.0
GRID = {"BPSK": np.arange(0, 11, 1.0), "QPSK": np.arange(3, 14, 1.0), "16QAM": np.arange(9, 20, 1.0)}


def q(x):
    return 0.5 * erfc(x / np.sqrt(2))


THEORY = {"BPSK": lambda e: q(np.sqrt(2 * e)), "QPSK": lambda e: q(np.sqrt(e)),
          "16QAM": lambda e: 0.75 * q(np.sqrt(e / 5))}


def complete_frames(spec, reps, offset, margin_symbols=8):
    """Bursts that lie entirely inside the simulated capture (TX-rate samples)."""
    F, sps = spec.frame_samples, spec.sps
    total = reps * F
    count = 0
    for k in range(reps + 1):
        start = k * F - offset
        if start - margin_symbols * sps >= 0 and start + (spec.burst_symbols + margin_symbols) * sps <= total:
            count += 1
    return count


def simulate(iq, esn0, seed, reps=8, cfo=17_000.0):
    """Returns (rx samples at RX rate, roll offset in TX samples)."""
    rng = np.random.default_rng(seed)
    offset = int(rng.integers(0, len(iq)))
    x = np.roll(np.tile(iq.astype(np.complex128), reps), -offset)
    r = Fraction(RX / TX).limit_denominator(5000)
    x = resample_poly(x, r.numerator, r.denominator)
    n = np.arange(len(x))
    x = x * np.exp(1j * (2 * np.pi * cfo * n / RX + rng.uniform(-np.pi, np.pi)))
    sigma2 = (4 * RX / TX) / 10 ** (esn0 / 10)
    noise = np.sqrt(sigma2 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    return x + noise, offset


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--target-ber", type=float, default=1e-3)
    p.add_argument("--captures", type=int, default=3, help="captures per SNR point (8 frames each)")
    p.add_argument("--payload-bytes", type=int, default=256)
    p.add_argument("--out-dir", default=str(PROJECT_ROOT / "results/analysis"))
    p.add_argument("--quick", action="store_true", help="coarse grid for a smoke run")
    a = p.parse_args(argv)

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for mod, grid in GRID.items():
        iq, meta, _ = build_framed_waveform(mod, total_symbols=4096, payload_bytes=a.payload_bytes)
        spec = MultimodFrameSpec.from_metadata(meta)
        for esn0 in (grid[::3] if a.quick else grid):
            errors = bits = frames = possible = 0
            snr_est = []
            for c in range(a.captures):
                seed = int(1000 * esn0) + 7919 * c + {"BPSK": 1, "QPSK": 2, "16QAM": 3}[mod]
                y, offset = simulate(iq, esn0, seed=seed)
                res = receive_multimod(y, spec, TX, RX, max_frames=16)
                possible += complete_frames(spec, 8, offset)
                frames += res.frames_detected
                if res.detected:
                    errors += res.total_payload_bit_errors
                    bits += res.total_payload_bits_compared
                    snr_est += [f.snr_db for f in res.frames]
            ber = errors / bits if bits else float("nan")
            row = {"modulation": mod, "snr_db": float(esn0), "ber": ber, "bit_errors": errors,
                   "bits": bits, "frames_detected": frames, "frames_possible": possible,
                   "detection_rate": frames / possible if possible else float("nan"),
                   "mean_estimated_snr_db": float(np.mean(snr_est)) if snr_est else float("nan"),
                   "theory_ber": float(THEORY[mod](10 ** (esn0 / 10)))}
            rows.append(row)
            print(f"{mod:5s} Es/N0 {esn0:5.1f} dB  BER {ber:.3e} ({errors}/{bits})  theory "
                  f"{row['theory_ber']:.3e}  detected {frames}/{possible}  SNR est "
                  f"{row['mean_estimated_snr_db']:.2f}")

    csv_path = out / "ber_vs_snr_multimod_synthetic.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # Points with too few bits to resolve the target are not trusted below it.
    usable = [r for r in rows if r["bits"] and (r["bit_errors"] >= 10 or r["bits"] >= 10 / a.target_ber)]
    thresholds = CognitiveRadioController.thresholds_from_ber_curve(usable, a.target_ber)
    meta = {"evidence": "synthetic AWGN, not hardware", "target_ber": a.target_ber,
            "snr_definition": "multimod_receiver data-aided post-MF Es/N0 (true Es/N0 in simulation)",
            "thresholds_db": thresholds,
            "csv": str(csv_path.relative_to(PROJECT_ROOT)) if csv_path.is_relative_to(PROJECT_ROOT) else str(csv_path),
            "generated": datetime.now().isoformat()}
    json_path = out / "controller_thresholds_synthetic.json"
    json_path.write_text(json.dumps(meta, indent=2))
    print(f"\nThresholds for BER <= {a.target_ber:g}: " +
          ", ".join(f"{m} {v:.2f} dB" for m, v in thresholds.items()))
    print(f"CSV : {csv_path}\nJSON: {json_path}")
    return meta


if __name__ == "__main__":
    main()
