"""
Tests for the transmission-day additions to the hardware path:
RF-path gate, stream/cyclic TX modes with a repeating source, multimod frames
through the runner, and the CW tone test.

Pluto and RTL-SDR are replaced by fakes and simulated channels. These tests
check data flow and decisions; they are NOT evidence of RF operation.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from test_multimod_receiver import channel as mm_channel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("rhe_day", PROJECT_ROOT / "scripts/run_hardware_experiment.py")
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

TX = 2_083_333.0
RX = 2_048_000.0
RF_ARGS = ["--enable-rf", "--freq", "866000000", "--rf-path", "conducted", "--attenuator-db", "30"]


class FakeAdapter:
    calls = []

    def __init__(self, **kwargs):
        FakeAdapter.calls.append(("init", kwargs))

    def configure(self, freq, att):
        FakeAdapter.calls.append(("configure", freq, att))

    def prepare(self, iq, scale):
        FakeAdapter.calls.append(("prepare", len(iq), scale))

    def start(self):
        assert runner.pluto_tx_adapter.RF_ENABLED
        FakeAdapter.calls.append(("start",))
        return {"status": "transmitting"}

    def stop(self):
        FakeAdapter.calls.append(("stop",))


def readback(rate=2_083_333.0, lo=866_000_000.0, gain=-30.0):
    def _rb(uri):
        FakeAdapter.calls.append(("readback",))
        return {"uri": uri, "tx_sample_rate_hz": rate, "tx_lo_hz": lo,
                "tx_hardwaregain_db": gain, "tx_rf_bandwidth_hz": 1e6}
    return _rb


def to_u8(x):
    i = np.clip(np.round(x.real + 127.5), 0, 255).astype(np.uint8)
    q = np.clip(np.round(x.imag + 127.5), 0, 255).astype(np.uint8)
    out = np.empty(2 * len(x), np.uint8)
    out[0::2], out[1::2] = i, q
    return out


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CAPTURE_DIR", tmp_path / "captures")

    def _write(rec, results_dir=None):
        d = tmp_path / "results"
        d.mkdir(exist_ok=True)
        p = d / f"r_{len(list(d.glob('*.json')))}.json"
        p.write_text(json.dumps(rec, default=float))
        return p
    monkeypatch.setattr(runner, "write_result", _write)
    FakeAdapter.calls = []
    yield tmp_path
    runner.pluto_tx_adapter.set_rf_enabled(False)


def args_for(*extra, **overrides):
    a = runner.build_parser().parse_args(RF_ARGS + list(extra))
    a.settle_s = 0.0
    for k, v in overrides.items():
        setattr(a, k, v)
    return a


# ------------------------------------------------------------------ RF gate
@pytest.mark.parametrize("override,msg", [
    (dict(rf_path=None), "--rf-path is required"),
    (dict(rf_path="ota"), "--antenna-separation-m"),
    (dict(rf_path="ota", antenna_separation_m=0.0), "--antenna-separation-m"),
    (dict(rf_path="ota", antenna_separation_m=1.0), "--attenuator-db is for"),
    (dict(attenuator_db=None), "PHYSICAL attenuation"),
    (dict(attenuator_db=20.0), "PHYSICAL attenuation"),
])
def test_rf_path_gate_blocks_before_any_hardware(sandbox, override, msg):
    iq, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    with pytest.raises(SystemExit, match=msg):
        runner.run_physical(args_for(**override), iq, meta, spec,
                            input_fn=lambda _: pytest.fail("operator asked"),
                            adapter_cls=FakeAdapter, capture_fn=None, readback_fn=readback())
    with pytest.raises(SystemExit, match=msg):
        runner.run_tone_test(args_for("--tone", **override), input_fn=lambda _: pytest.fail("asked"),
                             adapter_cls=FakeAdapter, capture_fn=None, readback_fn=readback())
    assert FakeAdapter.calls == []
    assert not runner.pluto_tx_adapter.RF_ENABLED


def test_rf_path_gate_in_main():
    with pytest.raises(SystemExit, match="--rf-path"):
        runner.main(["--enable-rf", "--freq", "866000000"])
    with pytest.raises(SystemExit, match="PHYSICAL"):
        runner.main(["--enable-rf", "--freq", "866000000", "--rf-path", "conducted", "--attenuator-db", "10"])


def test_ota_path_parses_and_records_separation():
    a = runner.build_parser().parse_args(
        ["--enable-rf", "--freq", "866000000", "--rf-path", "ota", "--antenna-separation-m", "1.5"])
    assert runner.enforce_rf_path(a) == {"type": "ota", "antenna_separation_m": 1.5}
    assert "OTA" in runner.describe_rf_path(runner.enforce_rf_path(a))


def test_ota_physical_record(sandbox):
    from src.radio.multimod_frame import save_framed_waveform
    _, meta_path, _, _ = save_framed_waveform(sandbox / "wf", "QPSK", payload_bytes=128,
                                              total_symbols=65536, sps=4, sample_rate=2083333, seed=42)
    iq, meta, spec = runner.load_waveform(meta_path)
    captured = to_u8(mm_channel(iq, reps=5, offset=77_000, cfo=-18_000, phase=0.9, esn0=20,
                                gain=20.0, seed=5)[:1_048_576])

    def fake_capture(freq, rate, gain, n, discard, dev):
        return captured.copy(), {"actual_sample_rate_hz": RX, "actual_sample_rate_source": "test",
                                 "requested_sample_rate_hz": int(rate), "returncode": 0}

    a = args_for(waveform=str(meta_path), rf_path="ota", attenuator_db=None, antenna_separation_m=2.0)
    rec = runner.run_physical(a, iq, meta, spec, input_fn=lambda _: "TRANSMIT",
                              adapter_cls=FakeAdapter, capture_fn=fake_capture, readback_fn=readback())
    assert rec["rf_path"] == {"type": "ota", "antenna_separation_m": 2.0}
    assert rec["mode"] == "physical_ota_loopback"
    assert rec["receiver"]["ber"] == 0.0


# --------------------------------------------------------- TX modes (stub GR)
@pytest.fixture
def stub_gnuradio(monkeypatch):
    seen = {}

    def sink(*args):
        seen["sink"] = args
        return MagicMock()

    def vsrc(data, repeat=False, vlen=1):
        seen["repeat"] = repeat
        return object()

    gr_mod = types.SimpleNamespace(top_block=lambda name: MagicMock())
    iio_mod = types.SimpleNamespace(fmcomms2_sink_fc32=sink)
    blocks_mod = types.SimpleNamespace(vector_source_c=vsrc)
    pkg = types.ModuleType("gnuradio")
    pkg.gr, pkg.iio, pkg.blocks = gr_mod, iio_mod, blocks_mod
    for name, mod in (("gnuradio", pkg), ("gnuradio.gr", gr_mod),
                      ("gnuradio.iio", iio_mod), ("gnuradio.blocks", blocks_mod)):
        monkeypatch.setitem(sys.modules, name, mod)
    yield seen


def test_source_repeats_so_flowgraph_keeps_running(stub_gnuradio):
    a = runner.pluto_tx_adapter.PlutoTXAdapter()
    a.prepare(np.ones(1000, np.complex64))
    a.build_flowgraph()
    assert stub_gnuradio["repeat"] is True


def test_stream_mode_uses_non_cyclic_sink(stub_gnuradio):
    a = runner.pluto_tx_adapter.PlutoTXAdapter(cyclic=False)
    a.prepare(np.ones(262_144, np.complex64))
    a.build_flowgraph()
    uri, ch_en, buf, cyclic = stub_gnuradio["sink"]
    assert cyclic is False and buf == runner.pluto_tx_adapter.STREAM_BUFFER_SAMPLES
    assert ch_en == [True, True]


def test_runner_passes_tx_mode_to_adapter(sandbox):
    iq, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    for mode, cyclic in (("stream", False), ("cyclic", True)):
        FakeAdapter.calls = []
        runner.run_physical(args_for("--tx-backend", "gnuradio", "--tx-mode", mode), iq, meta, spec,
                            input_fn=lambda _: "TRANSMIT",
                            adapter_cls=FakeAdapter,
                            capture_fn=lambda *a: (_ for _ in ()).throw(TimeoutError("x")),
                            readback_fn=readback())
        assert FakeAdapter.calls[0][1]["cyclic"] is cyclic
    # Default backend is pyadi (cyclic); gnuradio keeps stream as its default.
    assert runner.resolve_tx(runner.build_parser().parse_args([])) == ("pyadi", "cyclic")
    assert runner.resolve_tx(runner.build_parser().parse_args(["--tx-backend", "gnuradio"])) == ("gnuradio", "stream")


# ------------------------------------------------- multimod through the runner
@pytest.mark.parametrize("mod", ["BPSK", "QPSK", "16QAM"])
def test_multimod_frame_physical_flow(sandbox, mod):
    from src.radio.multimod_frame import save_framed_waveform
    _, meta_path, _, _ = save_framed_waveform(sandbox / "wf", mod, payload_bytes=128,
                                              total_symbols=65536, sps=4, sample_rate=2083333, seed=42)
    iq, meta, spec = runner.load_waveform(meta_path)
    rx = mm_channel(iq, reps=5, offset=77_000, cfo=-18_000, phase=0.9, esn0=20, gain=20.0, seed=5)[:1_048_576]
    captured = to_u8(rx)

    def fake_capture(freq, rate, gain, n, discard, dev):
        FakeAdapter.calls.append(("capture",))
        return captured.copy(), {"actual_sample_rate_hz": RX, "actual_sample_rate_source": "test",
                                 "requested_sample_rate_hz": int(rate), "returncode": 0}

    a = args_for(waveform=str(meta_path))
    rec = runner.run_physical(a, iq, meta, spec, input_fn=lambda _: "TRANSMIT",
                              adapter_cls=FakeAdapter, capture_fn=fake_capture, readback_fn=readback())
    assert rec["status"] == "frames_detected" and rec["receiver"]["ber"] == 0.0
    assert rec["rf_path"] == {"type": "conducted", "physical_attenuation_db": 30.0}
    assert rec["receiver"]["modulation"] == mod
    off = runner.run_offline(runner.build_parser().parse_args(
        ["--rx-file", rec["rx_capture_file"], "--waveform", str(meta_path), "--no-save"]), spec, meta)
    assert off["receiver"]["ber"] == 0.0


def test_dry_run_accepts_multimod_waveform(tmp_path):
    from src.radio.multimod_frame import save_framed_waveform
    _, meta_path, _, _ = save_framed_waveform(tmp_path, "16QAM", payload_bytes=128, total_symbols=65536,
                                              sps=4, sample_rate=2083333, seed=42)
    out = runner.main(["--waveform", str(meta_path), "--freq", "866000000"])
    assert out["status"] == "dry_run_ok" and out["derived_configuration"]["frames_in_capture"] >= 2


# ------------------------------------------------------------------ tone test
def test_make_tone_is_seamless_and_offset_exact():
    iq, f = runner.make_tone(TX, 100_000.0)
    assert abs(f - 100_000.0) < TX / len(iq)
    nxt = np.exp(2j * np.pi * f / TX * len(iq))
    assert abs(nxt - 1) < 1e-6          # integer cycles: wraps without a phase jump
    assert np.max(np.abs(iq)) == pytest.approx(1.0, abs=1e-6)


def _rx_tone(present, cfo=23_456.0, amp=3.0, seed=0, n=1_048_576):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / RX
    x = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * 0.7
    # an internal spur like the RTL's (present in both captures)
    x += 0.6 * np.exp(2j * np.pi * -190_800 * t)
    if present:
        x += amp * np.exp(2j * np.pi * (100_000 + cfo) * t)
    return x


def test_analyze_tone_detects_tone_and_ignores_spurs():
    a = runner.analyze_tone(_rx_tone(True), _rx_tone(False, seed=1), RX, 100_000.0)
    assert a["detected"] and a["implied_cfo_hz"] == pytest.approx(23_456, abs=200)
    b = runner.analyze_tone(_rx_tone(False, seed=2), _rx_tone(False, seed=3), RX, 100_000.0)
    assert not b["detected"]


@pytest.mark.parametrize("present,status", [(True, "tone_detected"), (False, "tone_not_detected")])
def test_tone_test_flow(sandbox, present, status):
    caps = [to_u8(_rx_tone(present, seed=10)), to_u8(_rx_tone(False, seed=11))]

    def fake_capture(freq, rate, gain, n, discard, dev):
        FakeAdapter.calls.append(("capture",))
        return caps.pop(0)[: 2 * n], {"actual_sample_rate_hz": RX, "actual_sample_rate_source": "test",
                                      "requested_sample_rate_hz": int(rate), "returncode": 0}

    rec = runner.run_tone_test(args_for("--tone", "--rx-gain", "0"), input_fn=lambda _: "TRANSMIT",
                               adapter_cls=FakeAdapter, capture_fn=fake_capture, readback_fn=readback())
    order = [c[0] for c in FakeAdapter.calls]
    assert order == ["init", "configure", "prepare", "start", "readback", "capture", "stop", "capture"]
    assert rec["status"] == status
    assert not runner.pluto_tx_adapter.RF_ENABLED
    side = json.loads(Path(rec["tx_on_capture"]).with_suffix(".json").read_text())
    assert side["tx_signal"] == "cw_tone" and side["rx_gain_mode"].startswith("auto")
    assert json.loads(Path(rec["tx_off_capture"]).with_suffix(".json").read_text())["tx_active"] is False


def test_tone_out_of_band_refused(sandbox):
    with pytest.raises(SystemExit, match="not inside"):
        runner.run_tone_test(args_for("--tone", freq=864_950_000), input_fn=lambda _: pytest.fail("asked"),
                             adapter_cls=FakeAdapter, capture_fn=None, readback_fn=readback())
    assert FakeAdapter.calls == []


def test_tone_readback_failure_stops_tx_without_capture(sandbox):
    rec = runner.run_tone_test(args_for("--tone"), input_fn=lambda _: "TRANSMIT", adapter_cls=FakeAdapter,
                               capture_fn=lambda *a: pytest.fail("captured"),
                               readback_fn=readback(gain=-10.0))
    assert rec["status"] == "failed_at_readback"
    assert [c[0] for c in FakeAdapter.calls][-1] == "stop"


def test_tone_dry_run():
    out = runner.main(["--tone", "--freq", "866000000"])
    assert out["status"] == "dry_run_ok"
    assert out["derived_configuration"]["tone_frequency_hz"] == pytest.approx(866_100_000, abs=10)
