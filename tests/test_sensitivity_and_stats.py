"""Tests for the sensitivity study harness and the hardware BER statistics."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import sensitivity_analysis as sa  # noqa: E402
import summarize_hardware_sweep as hs  # noqa: E402


def test_clopper_pearson_known_values():
    lo, hi = hs.clopper_pearson(0, 4096)
    assert lo == 0.0 and abs(hi - 9.0e-4) < 2e-5
    lo, hi = hs.clopper_pearson(5, 4096)
    assert abs(lo - 3.965e-4) < 1e-6 and abs(hi - 2.846e-3) < 1e-5


def test_implied_loss_zero_on_theory():
    ber = float(hs.theory_ber("QPSK", 8.0))
    assert abs(hs.implied_loss_db("QPSK", 8.0, ber)) < 1e-6
    assert hs.implied_loss_db("QPSK", 8.0, ber * 2) > 0      # worse than theory -> positive loss
    assert hs.implied_loss_db("QPSK", 8.0, 0.0) is None


def test_outcome_probability_matches_benchmark_at_zero_loss():
    for snr in (-5.0, 3.0, 12.0, 25.0):
        for mod in ("BPSK", "QPSK", "16-QAM"):
            assert sa.outcome_probability(snr, mod, 0.0) == sa.mse.calibrated_probability(snr, mod)
            assert sa.outcome_probability(snr, mod, 1.0) <= sa.mse.calibrated_probability(snr, mod) + 1e-12


@pytest.mark.parametrize("strategy", ["fixed", "calibrated_hybrid"])
def test_run_strategy_reproduces_benchmark_row(strategy):
    ref = pd.read_csv(ROOT / "results" / "calibrated_multi_seed_results.csv")
    row = ref[(ref.environment == "High") & (ref.seed == 2026) & (ref.strategy == strategy)].iloc[0]
    snr, rnd = sa.traces(2026, "High")
    r = sa.run_strategy(snr, rnd, strategy)
    assert abs(r["throughput_bits_per_step"] - row.throughput_bits_per_step) < 1e-12
    assert r["switches"] == row.switches


def test_margin_makes_controller_more_conservative():
    snr, rnd = sa.traces(2027, "High")
    base = sa.run_strategy(snr[:1500], rnd[:1500], "calibrated_hybrid", loss_db=1.0)
    safe = sa.run_strategy(snr[:1500], rnd[:1500], "calibrated_hybrid", loss_db=1.0, margin_db=1.0)
    assert safe["packet_delivery_ratio"] >= base["packet_delivery_ratio"]
