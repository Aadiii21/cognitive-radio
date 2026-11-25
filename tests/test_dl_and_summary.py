"""Tests for the DL classifier data path and the hardware BER summary (no hardware, no training)."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.dl import modulation_classifier as mc  # noqa: E402


def test_synthetic_dataset_shapes_and_balance():
    X, y, e = mc.synthetic_dataset(6, seed=3)
    assert X.shape == (18, 2, mc.WINDOW) and X.dtype == np.float32
    assert np.bincount(y).tolist() == [6, 6, 6]
    rms = np.sqrt(np.mean(X[:, 0] ** 2 + X[:, 1] ** 2, axis=1))
    assert np.allclose(rms, 1.0, atol=1e-4)
    assert (e >= 0).all() and (e <= 26).all()


def test_fixed_esn0_and_reproducible():
    a = mc.synthetic_dataset(3, seed=5, esn0_db=12)
    b = mc.synthetic_dataset(3, seed=5, esn0_db=12)
    assert np.array_equal(a[0], b[0]) and set(a[2]) == {12.0}


def test_cumulant_features_separate_clean_constellations():
    X, y, _ = mc.synthetic_dataset(20, seed=1, esn0_db=25,
                                   ranges=mc.ImpairmentRanges(cfo_hz=(0.0, 0.0)))
    f = mc.cumulant_features(X)
    c42 = f[:, 2]   # normalised C42: BPSK ~ -2, QPSK ~ -1, 16QAM ~ -0.68
    assert c42[y == 0].mean() < c42[y == 1].mean() < c42[y == 2].mean()


def test_real_dataset_empty_project(tmp_path):
    X, y, rows = mc.real_dataset(tmp_path)
    assert X.shape == (0, 2, mc.WINDOW) and rows == []


def test_model_forward_shape():
    torch = pytest.importorskip("torch")
    m = mc.build_model()
    out = m(torch.zeros(4, 2, mc.WINDOW))
    assert tuple(out.shape) == (4, 3)
    p = mc.predict(m, np.zeros((5, 2, mc.WINDOW), np.float32))
    assert p.shape == (5, 3) and np.allclose(p.sum(1), 1, atol=1e-5)


def test_hardware_summary_theory_and_collect(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import summarize_hardware_sweep as s
    assert abs(s.theory_ber("BPSK", 4.32) - 0.01) < 0.002
    assert s.theory_ber("16QAM", 10) > s.theory_ber("QPSK", 10) > s.theory_ber("BPSK", 10)
    rec = {"waveform_format": "multimod_frame_v1", "tx": {"requested_attenuation_db": 5}, "rx": {"gain_db": 28.0},
           "rf_path": {"type": "conducted"}, "rf_path_correction": {"actual_type": "ota"},
           "receiver": {"modulation": "QPSK", "frames": [{"snr_db": 10.0}, {"snr_db": 10.0}],
                        "total_payload_bit_errors": 0, "total_payload_bits_compared": 2048}}
    (tmp_path / "experiment_result_x.json").write_text(json.dumps(rec))
    rows = s.collect(tmp_path)
    assert len(rows) == 1 and rows[0]["rf_path"] == "ota" and rows[0]["mean_esn0_db"] == 10.0
    assert rows[0]["ber_95_upper_if_zero"] == round(3 / 2048, 6)
