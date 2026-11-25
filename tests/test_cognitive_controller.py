"""Tests for src/radio/cognitive_controller.py (policy only; no RF)."""

import csv

import pytest

from src.radio.cognitive_controller import CognitiveRadioController as C


def test_first_decision_is_initial_and_picks_best_channel():
    d = C().decide([7.5, 14.2, 19.8])
    assert (d.channel_index, d.modulation, d.action) == (2, "16QAM", "initial")


def test_hold_when_nothing_changes():
    c = C()
    c.decide([12.0, 5.0])
    d = c.decide([12.2, 5.0])
    assert (d.channel_index, d.modulation, d.action) == (0, "QPSK", "hold")


def test_channel_list_shrinking_during_dwell_does_not_crash():
    c = C(min_dwell_steps=3)
    c.decide([5.0, 6.0, 20.0])          # initial: channel 2
    c.decide([5.0, 25.0, 9.0])          # switch to channel 1, starts dwell
    d = c.decide([30.0])                # channel 1 no longer exists
    assert d.channel_index == 0 and d.action in ("switch_channel", "switch_channel_and_modulation")


def test_below_bpsk_threshold_is_flagged():
    c = C()
    d = c.decide([-10.0, -12.0])
    assert d.action == "insufficient_snr" and d.modulation == "BPSK" and d.channel_index == 0
    d = c.decide([2.0, 1.0])
    assert d.action == "insufficient_snr"


def test_upgrade_needs_hysteresis_but_holding_does_not():
    c = C(hysteresis_db=1.0, min_dwell_steps=0)
    assert c.decide([12.0]).modulation == "QPSK"
    assert c.decide([18.5]).modulation == "QPSK"      # 18.5 < 18 + 1: no upgrade
    assert c.decide([19.2]).modulation == "16QAM"     # upgrade
    assert c.decide([18.2]).modulation == "16QAM"     # >= 18: stays
    assert c.decide([17.5]).modulation == "QPSK"      # below threshold: downgrade


def test_channel_switch_needs_hysteresis():
    c = C(hysteresis_db=1.0, min_dwell_steps=0)
    c.decide([12.0, 11.0])
    assert c.decide([12.0, 12.5]).channel_index == 0      # +0.5 dB: stay
    assert c.decide([12.0, 13.5]).channel_index == 1      # +1.5 dB: switch


def test_dwell_holds_channel_but_applies_downgrade_at_once():
    c = C(min_dwell_steps=2, hysteresis_db=0.0)
    c.decide([20.0, 5.0])                                  # initial: ch0 16QAM
    c.decide([12.0, 25.0])                                 # switch to ch1, dwell 2
    d = c.decide([30.0, 12.0])                             # wants ch0, but dwell holds ch1
    assert d.channel_index == 1 and d.modulation == "QPSK" and d.action == "change_modulation"
    d = c.decide([30.0, 12.0])
    assert d.channel_index == 1 and d.action == "hold_dwell"
    d = c.decide([30.0, 12.0])                             # dwell over
    assert d.channel_index == 0 and d.action == "switch_channel_and_modulation"


def test_dwell_broken_when_current_channel_becomes_unusable():
    c = C(min_dwell_steps=5, hysteresis_db=0.0)
    c.decide([12.0, 5.0])
    c.decide([5.0, 13.0])                                  # switch to ch1, dwell 5
    d = c.decide([12.0, -3.0])                             # ch1 now below BPSK minimum
    assert d.channel_index == 0


def test_invalid_parameters():
    with pytest.raises(ValueError):
        C(bpsk_min_db=10, qpsk_min_db=5, qam16_min_db=18)
    with pytest.raises(ValueError):
        C(hysteresis_db=-1)
    with pytest.raises(ValueError):
        C().decide([])


def test_thresholds_from_ber_curve_interpolates_log_ber():
    rows = []
    for mod, pts in {"BPSK": [(6, 2e-3), (7, 5e-4)], "QPSK": [(9, 3e-3), (10, 1e-3), (11, 2e-4)],
                     "16QAM": [(16, 2e-3), (17, 6e-4)]}.items():
        rows += [{"modulation": mod, "snr_db": s, "ber": b} for s, b in pts]
    t = C.thresholds_from_ber_curve(rows, 1e-3)
    assert 6 < t["BPSK"] < 7 and t["QPSK"] == pytest.approx(10.0) and 16 < t["16QAM"] < 17
    with pytest.raises(ValueError, match="never reaches"):
        C.thresholds_from_ber_curve(rows, 1e-6)


def test_from_ber_curve_csv(tmp_path):
    p = tmp_path / "c.csv"
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["modulation", "snr_db", "ber"])
        w.writeheader()
        for mod, base in (("BPSK", 6), ("QPSK", 9), ("16QAM", 16)):
            w.writerow({"modulation": mod, "snr_db": base, "ber": 1e-2})
            w.writerow({"modulation": mod, "snr_db": base + 2, "ber": 1e-4})
    c = C.from_ber_curve(p, 1e-3)
    assert c.thresholds == pytest.approx((7.0, 10.0, 17.0))


def test_ber_curve_script_quick(tmp_path):
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("ber_curves", root / "scripts/ber_curves.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    meta = mod.main(["--captures", "1", "--out-dir", str(tmp_path), "--target-ber", "1e-2"])
    assert set(meta["thresholds_db"]) == {"BPSK", "QPSK", "16QAM"}
    assert meta["evidence"].startswith("synthetic")
    # Theory for BER 1e-2: BPSK ~4.3, QPSK ~7.3, 16-QAM ~13.4 dB Es/N0.
    t = meta["thresholds_db"]
    assert 3.5 < t["BPSK"] < 5.5 and 6.5 < t["QPSK"] < 8.5 and 12.5 < t["16QAM"] < 14.5
