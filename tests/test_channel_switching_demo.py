"""Tests for scripts/run_channel_switching_demo.py (no hardware)."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_channel_switching_demo as demo  # noqa: E402
from src.radio import pluto_tx_adapter  # noqa: E402


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "OUT_SIM", tmp_path / "sim")
    monkeypatch.setattr(demo, "OUT_REAL", tmp_path / "real")
    pluto_tx_adapter.RF_ENABLED = False
    yield tmp_path
    pluto_tx_adapter.RF_ENABLED = False


def args(*extra):
    a = demo.build_parser().parse_args(list(extra))
    a.channels = [int(f) for f in a.channels]
    a.settle_s = 0.0
    return a


def test_controller_snr_mapping():
    assert demo.esn0_to_controller_snr(22.0) == pytest.approx(22.0 - 6.0206, abs=1e-3)
    assert demo.esn0_to_controller_snr(None) == -5.0
    assert demo.esn0_to_controller_snr(-20.0) == -5.0
    assert demo.esn0_to_controller_snr(99.0) == 30.0


def test_margin_shifts_controller_input():
    assert demo.esn0_to_controller_snr(22.0, 2.0) == pytest.approx(22.0 - 6.0206 - 2.0, abs=1e-3)
    assert demo.esn0_to_controller_snr(None, 2.0) == -5.0
    assert demo.esn0_to_controller_snr(0.0, 2.0) == -5.0


def test_margin_makes_controller_drop_16qam_near_cutoff(sandbox, tmp_path):
    # one phase at ~17.5 dB Es/N0 in the simulated air (attenuation 5 dB): 16-QAM without margin,
    # QPSK with a 2 dB margin (16-QAM cut-off moves from 16.2 to 18.2 dB)
    import json
    sch = tmp_path / "s.json"
    sch.write_text(json.dumps([{"name": "near cut-off", "attenuation_db": [5, 20, 20]}]))
    plain = demo.run_session(args("--simulate", "--rounds-per-phase", "2", "--schedule", str(sch)))
    safe = demo.run_session(args("--simulate", "--rounds-per-phase", "2", "--schedule", str(sch),
                                 "--margin-db", "2"))
    assert {r["modulation"] for r in plain["rows"]} == {"16-QAM"}
    assert {r["modulation"] for r in safe["rows"]} == {"QPSK"}
    rec = json.loads((safe["out"] / "session.json").read_text())
    assert rec["controller"]["margin_db"] == 2.0


def test_margin_out_of_range_refused(sandbox, capsys):
    assert demo.main(["--simulate", "--margin-db", "20"]) == 2
    assert "margin" in capsys.readouterr().out


def test_simulated_session_switches_to_best_channel(sandbox):
    res = demo.run_session(args("--simulate", "--rounds-per-phase", "1"))
    rows, s = res["rows"], res["summary"]
    assert [r["channel"] for r in rows] == [0, 1, 2, 0, 0]
    assert [r["modulation"] for r in rows] == ["16-QAM", "16-QAM", "16-QAM", "QPSK", "BPSK"]
    assert s["switches"] == 3 and s["best_channel_rounds"] == 5 and s["data_bit_errors"] <= 5
    out = res["out"]
    assert (out / "rounds.csv").exists() and (out / "session.png").exists() and (out / "session.json").exists()
    assert len(list((out / "captures").glob("*.json"))) == 5 * 4
    assert not list((out / "captures").glob("*.cu8"))          # simulated raw IQ not kept by default
    assert pluto_tx_adapter.RF_ENABLED is False


@pytest.mark.parametrize("extra, msg", [
    ([], "--enable-rf"),
    (["--enable-rf"], "--rf-path is required"),
    (["--enable-rf", "--rf-path", "ota"], "--antenna-separation-m"),
    (["--enable-rf", "--rf-path", "ota", "--antenna-separation-m", "1", "--channels", "865700000", "867800000"],
     "not inside"),
    (["--enable-rf", "--rf-path", "ota", "--antenna-separation-m", "1", "--channels", "866000000", "866500000"],
     "overlap"),
    (["--enable-rf", "--rf-path", "ota", "--antenna-separation-m", "1", "--amplitude-scale", "0.5"],
     "amplitude"),
])
def test_preflight_refuses(extra, msg):
    with pytest.raises(SystemExit, match=msg):
        demo.run_session(args(*extra), input_fn=lambda _: pytest.fail("must not ask"))


class FakeTX:
    """Records every start/stop; transmits through a SimulatedAir so the receiver sees frames."""
    starts = stops = 0
    air = None
    readback_gain_offset = 0.0

    def __init__(self, uri, sample_rate, bandwidth, amplitude_scale, cyclic=True):
        self.rate = sample_rate

    def configure(self, frequency, attenuation):
        self.freq, self.att = frequency, attenuation

    def prepare(self, iq, amplitude_scale=None):
        self.iq = iq

    def start(self):
        assert pluto_tx_adapter.RF_ENABLED
        FakeTX.starts += 1
        FakeTX.air.current = (self.freq, self.att, self.iq)
        FakeTX.last = self
        return {}

    def stop(self):
        FakeTX.stops += 1
        return {}


def readback_for_fake(uri):
    t = FakeTX.last
    return {"tx_lo_hz": float(t.freq), "tx_hardwaregain_db": -float(t.att) + FakeTX.readback_gain_offset,
            "tx_sample_rate_hz": float(t.rate)}


@pytest.fixture
def fake_hw(monkeypatch):
    FakeTX.starts = FakeTX.stops = 0
    FakeTX.readback_gain_offset = 0.0
    FakeTX.air = demo.SimulatedAir(seed=3)
    monkeypatch.setattr(demo.hx, "check_devices", lambda backend="pyadi": True)
    return FakeTX


REAL = ["--enable-rf", "--rf-path", "ota", "--antenna-separation-m", "1.5", "--rounds-per-phase", "1"]


def test_real_path_with_fake_radios(fake_hw, sandbox):
    res = demo.run_session(args(*REAL), input_fn=lambda _: "TRANSMIT", tx_cls=FakeTX,
                           capture_fn=FakeTX.air.capture, readback_fn=readback_for_fake, lo_check=lambda uri: False)
    assert res["error"] is None and res["summary"]["switches"] == 3
    assert FakeTX.starts == FakeTX.stops == 20
    assert (sandbox / "real").exists() and pluto_tx_adapter.RF_ENABLED is False
    import json
    sc = json.loads(next((res["out"] / "captures").glob("*.json")).read_text())
    assert sc["data_kind"] == "rtl_sdr_rx_capture" and sc["rf_path"]["antenna_separation_m"] == 1.5
    assert len(list((res["out"] / "captures").glob("*.cu8"))) == 20     # real runs keep every capture


def test_operator_must_type_transmit(fake_hw):
    res = demo.run_session(args(*REAL), input_fn=lambda _: "yes", tx_cls=FakeTX, capture_fn=FakeTX.air.capture,
                           readback_fn=readback_for_fake, lo_check=lambda uri: False)
    assert res is None and FakeTX.starts == 0


def test_lo_powered_down_refused_before_asking(fake_hw):
    with pytest.raises(SystemExit, match="powered down"):
        demo.run_session(args(*REAL), input_fn=lambda _: pytest.fail("must not ask"), tx_cls=FakeTX,
                         capture_fn=FakeTX.air.capture, readback_fn=readback_for_fake, lo_check=lambda uri: True)
    assert FakeTX.starts == 0


def test_readback_mismatch_stops_session_and_tx(fake_hw):
    FakeTX.readback_gain_offset = 3.0
    res = demo.run_session(args(*REAL), input_fn=lambda _: "TRANSMIT", tx_cls=FakeTX,
                           capture_fn=FakeTX.air.capture, readback_fn=readback_for_fake, lo_check=lambda uri: False)
    assert res["rows"] == [] and "readback" in res["error"]
    assert FakeTX.starts == FakeTX.stops == 1 and pluto_tx_adapter.RF_ENABLED is False


def test_dry_run_touches_nothing(fake_hw):
    res = demo.run_session(args("--dry-run", "--rf-path", "ota", "--antenna-separation-m", "1"),
                           input_fn=lambda _: pytest.fail("must not ask"), tx_cls=FakeTX,
                           lo_check=lambda uri: pytest.fail("must not touch hardware"))
    assert res["dry_run"] and FakeTX.starts == 0


def test_real_pyadi_transmitter_through_fake_pluto(sandbox, monkeypatch):
    """Uses the real PlutoPyadiTX class (only the adi.Pluto device is faked) so argument mismatches show up."""
    from src.radio.pluto_pyadi_tx import PlutoPyadiTX
    air = demo.SimulatedAir(seed=4)
    devices = []

    class FakePluto:
        def __init__(self, uri):
            self.__dict__["log"] = []
            devices.append(self)

        def __setattr__(self, k, v):
            self.__dict__[k] = v
            self.log.append((k, v))

        def tx(self, data):
            air.current = (int(self.tx_lo), -float(self.tx_hardwaregain_chan0), np.asarray(data) / 2 ** 15)

        def tx_destroy_buffer(self):
            air.current = None

    class TX(PlutoPyadiTX):
        def __init__(self, **kw):
            super().__init__(sdr_factory=FakePluto, **kw)

    def readback(uri):
        d = devices[-1]
        return {"tx_lo_hz": float(d.tx_lo), "tx_hardwaregain_db": float(d.tx_hardwaregain_chan0),
                "tx_sample_rate_hz": float(d.sample_rate)}

    monkeypatch.setattr(demo.hx, "check_devices", lambda backend="pyadi": True)
    res = demo.run_session(args(*REAL), input_fn=lambda _: "TRANSMIT", tx_cls=TX, capture_fn=air.capture,
                           readback_fn=readback, lo_check=lambda uri: False)
    assert res["error"] is None and res["summary"]["switches"] == 3
    assert all(dict((k, v) for k, v in d.log if not isinstance(v, np.ndarray)).get("tx_rf_bandwidth") == 1_000_000
               for d in devices)
    assert all(d.log[-1] == ("tx_hardwaregain_chan0", -89.75) for d in devices)   # left at minimum gain
    assert pluto_tx_adapter.RF_ENABLED is False


def test_unresponsive_pluto_gives_clear_message():
    import subprocess

    def hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="iio_attr", timeout=10)
    with pytest.raises(SystemExit, match="not responding"):
        demo.read_lo_powerdown("ip:192.168.2.1", run=hang)


def test_read_lo_powerdown_parses_iio_attr():
    class R:
        def __init__(self, out):
            self.stdout = out
    assert demo.read_lo_powerdown("ip:x", run=lambda *a, **k: R("1\n")) is True
    assert demo.read_lo_powerdown("ip:x", run=lambda *a, **k: R("0\n")) is False
