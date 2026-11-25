"""
Tests for the pure-Python Pluto transmitter (src/radio/pluto_pyadi_tx.py) and
its use by the runner. A fake adi.Pluto records every hardware call; no RF.
"""

import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from src.radio import pluto_tx_adapter
from src.radio.pluto_pyadi_tx import DAC_FULL_SCALE, MIN_TX_GAIN_DB, PlutoPyadiTX

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("rhe_pyadi", ROOT / "scripts/run_hardware_experiment.py")
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


class FakePluto:
    instances = []

    def __init__(self, uri):
        self.uri = uri
        self.log = [("connect", uri)]
        self.tx_data = None
        FakePluto.instances.append(self)

    def __setattr__(self, name, value):
        if name in ("uri", "log", "tx_data"):
            object.__setattr__(self, name, value)
        else:
            self.log.append(("set", name, value))
            object.__setattr__(self, name, value)

    def tx(self, data):
        self.log.append(("tx", len(data)))
        object.__setattr__(self, "tx_data", np.asarray(data))

    def tx_destroy_buffer(self):
        self.log.append(("destroy",))


@pytest.fixture(autouse=True)
def rf_off():
    FakePluto.instances = []
    pluto_tx_adapter.set_rf_enabled(False)
    yield
    pluto_tx_adapter.set_rf_enabled(False)


def make_tx(**kw):
    tx = PlutoPyadiTX(sample_rate=2_083_333, sdr_factory=FakePluto, **kw)
    tx.configure(866_000_000, 30)
    return tx


def test_nothing_touches_hardware_before_start():
    tx = make_tx()
    tx.prepare(np.ones(1000) * 0.5)
    assert FakePluto.instances == []


def test_start_refused_without_rf_flag():
    tx = make_tx()
    tx.prepare(np.ones(1000) * 0.5)
    with pytest.raises(RuntimeError, match="DISABLED"):
        tx.start()
    assert FakePluto.instances == []


def test_safe_configuration_order_and_cyclic_tx():
    tx = make_tx()
    tx.prepare(np.exp(1j * np.linspace(0, 20, 4096)), 0.1)
    pluto_tx_adapter.set_rf_enabled(True)
    status = tx.start()
    log = FakePluto.instances[0].log
    names = [(e[1] if e[0] == "set" else e[0]) for e in log]
    # gain to minimum before the sample rate changes; requested gain last; then cyclic tx
    assert names.index("tx_hardwaregain_chan0") < names.index("sample_rate")
    assert log[1] == ("set", "tx_hardwaregain_chan0", MIN_TX_GAIN_DB)
    i_rate, i_bw, i_lo = names.index("sample_rate"), names.index("tx_rf_bandwidth"), names.index("tx_lo")
    gains = [k for k, e in enumerate(log) if e[:2] == ("set", "tx_hardwaregain_chan0")]
    assert gains[-1] > max(i_rate, i_bw, i_lo) and log[gains[-1]][2] == -30.0
    assert ("set", "sample_rate", 2_083_333) in log and ("set", "tx_lo", 866_000_000) in log
    assert names.index("tx_cyclic_buffer") < names.index("tx")
    assert status["backend"] == "pyadi-iio" and status["tx_mode"] == "cyclic"


def test_samples_scaled_once_to_int16_full_scale():
    iq = np.exp(1j * np.linspace(0, 20, 4096))      # unit amplitude
    tx = make_tx()
    tx.prepare(iq, 0.1)
    pluto_tx_adapter.set_rf_enabled(True)
    tx.start()
    sent = FakePluto.instances[0].tx_data
    assert np.max(np.abs(sent)) == pytest.approx(0.1 * DAC_FULL_SCALE, rel=1e-6)   # -20 dBFS


def test_peak_limit_and_int16_range_enforced():
    tx = make_tx()
    with pytest.raises(ValueError, match="exceeds limit"):
        tx.prepare(np.ones(10) * 3.0, 0.1)          # peak 0.3 > 0.25
    big = PlutoPyadiTX(sdr_factory=FakePluto, peak_limit=2.0)
    with pytest.raises(ValueError, match="int16"):
        big.prepare(np.ones(10), 1.5)


def test_stop_destroys_buffer_then_minimum_gain():
    tx = make_tx()
    tx.prepare(np.ones(100) * 0.5)
    pluto_tx_adapter.set_rf_enabled(True)
    tx.start()
    tx.stop()
    log = FakePluto.instances[0].log
    assert log[-2] == ("destroy",) and log[-1] == ("set", "tx_hardwaregain_chan0", MIN_TX_GAIN_DB)
    assert tx._closed and not tx.transmitting


def test_failure_during_start_is_cleaned_up_by_stop():
    class Broken(FakePluto):
        def tx(self, data):
            raise OSError("buffer push failed")

    tx = PlutoPyadiTX(sdr_factory=Broken)
    tx.configure(866_000_000, 30)
    tx.prepare(np.ones(100) * 0.5)
    pluto_tx_adapter.set_rf_enabled(True)
    with pytest.raises(OSError):
        tx.start()
    tx.stop()
    assert FakePluto.instances[0].log[-1] == ("set", "tx_hardwaregain_chan0", MIN_TX_GAIN_DB)


def test_stream_mode_rejected_and_rate_validated():
    with pytest.raises(ValueError, match="cyclic"):
        PlutoPyadiTX(cyclic=False)
    with pytest.raises(ValueError, match="FIR"):
        PlutoPyadiTX(sample_rate=2_048_000)


def test_runner_defaults_to_pyadi_cyclic():
    a = runner.build_parser().parse_args([])
    assert a.tx_backend == "pyadi"
    assert runner.resolve_tx(a) == ("pyadi", "cyclic")
    assert runner.adapter_class_for("pyadi") is PlutoPyadiTX
    g = runner.build_parser().parse_args(["--tx-backend", "gnuradio"])
    assert runner.resolve_tx(g) == ("gnuradio", "stream")
    bad = runner.build_parser().parse_args(["--tx-mode", "stream"])
    with pytest.raises(SystemExit, match="cyclic only"):
        runner.resolve_tx(bad)


def test_runner_tone_test_end_to_end_with_fake_pluto(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(runner, "CAPTURE_DIR", tmp_path / "cap")
    monkeypatch.setattr(runner, "write_result",
                        lambda rec, results_dir=None: (tmp_path / "r.json").write_text(json.dumps(rec, default=float))
                        or tmp_path / "r.json")
    n = 1_048_576
    t = np.arange(n) / 2_048_000.0

    def u8(x):
        out = np.empty(2 * len(x), np.uint8)
        out[0::2] = np.clip(np.round(x.real + 127.5), 0, 255)
        out[1::2] = np.clip(np.round(x.imag + 127.5), 0, 255)
        return out

    noise = lambda s: (np.random.default_rng(s).standard_normal(n) + 1j * np.random.default_rng(s + 1).standard_normal(n)) * 0.7
    caps = [u8(noise(1) + 3 * np.exp(2j * np.pi * 112_000 * t)), u8(noise(3))]

    def fake_capture(*a):
        return caps.pop(0), {"actual_sample_rate_hz": 2_048_000.0, "actual_sample_rate_source": "test",
                             "requested_sample_rate_hz": 2_048_000, "returncode": 0}

    def readback(uri):
        return {"tx_sample_rate_hz": 2_083_333.0, "tx_lo_hz": 866_000_000.0,
                "tx_hardwaregain_db": -30.0, "tx_rf_bandwidth_hz": 1e6}

    args = runner.build_parser().parse_args(["--enable-rf", "--tone", "--freq", "866000000",
                                             "--rf-path", "conducted", "--attenuator-db", "30"])
    args.settle_s = 0.0

    class Factory(PlutoPyadiTX):
        def __init__(self, **kw):
            super().__init__(sdr_factory=FakePluto, **kw)

    rec = runner.run_tone_test(args, input_fn=lambda _: "TRANSMIT", adapter_cls=Factory,
                               capture_fn=fake_capture, readback_fn=readback)
    assert rec["status"] == "tone_detected" and rec["tx_backend"] == "pyadi"
    assert rec["tone_analysis"]["implied_cfo_hz"] == pytest.approx(12_000, abs=300)
    log = FakePluto.instances[0].log
    assert log[-1] == ("set", "tx_hardwaregain_chan0", MIN_TX_GAIN_DB)   # stopped before baseline
    assert not pluto_tx_adapter.RF_ENABLED


def test_check_devices_requires_adi_for_pyadi(monkeypatch):
    monkeypatch.setitem(sys.modules, "adi", None)     # import fails
    assert runner.check_devices("pyadi") is False
    fake_adi = types.ModuleType("adi")
    fake_adi.Pluto = FakePluto
    monkeypatch.setitem(sys.modules, "adi", fake_adi)
    monkeypatch.setitem(sys.modules, "iio", types.ModuleType("iio"))
    monkeypatch.setattr(runner.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr=""))
    assert runner.check_devices("pyadi") is True
