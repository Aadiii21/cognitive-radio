"""
Data-flow tests for scripts/run_hardware_experiment.py.

The Pluto adapter and the rtl_sdr capture are replaced by fakes; the "RX"
bytes come from a simulated channel. These tests check ordering (TX running
during capture, always stopped), that the saved RX file is the captured data
and not the TX waveform, and that BER comes from the receiver. They are NOT
evidence of physical RF operation.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from test_bpsk_receiver import RX_RATE, TX_RATE, simulate_capture

PROJECT_ROOT = Path(__file__).resolve().parents[1]
spec_ = importlib.util.spec_from_file_location(
    "run_hardware_experiment", PROJECT_ROOT / "scripts/run_hardware_experiment.py")
runner = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(runner)


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


def to_u8(rx):
    i = np.clip(np.round(rx.real + 127.5), 0, 255).astype(np.uint8)
    q = np.clip(np.round(rx.imag + 127.5), 0, 255).astype(np.uint8)
    out = np.empty(2 * len(rx), dtype=np.uint8)
    out[0::2], out[1::2] = i, q
    return out


def _write_result(rec, results_dir):
    results_dir.mkdir(parents=True, exist_ok=True)
    p = results_dir / f"r_{len(list(results_dir.glob('*.json')))}.json"
    p.write_text(json.dumps(rec, indent=2, default=float))
    return p


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CAPTURE_DIR", tmp_path / "captures")
    monkeypatch.setattr(runner, "write_result",
                        lambda rec, results_dir=None: _write_result(rec, tmp_path / "results"))
    FakeAdapter.calls = []
    yield tmp_path
    runner.pluto_tx_adapter.set_rf_enabled(False)


def fake_readback(rate=2_083_333.0, lo=866_000_000.0, gain=-30.0, fail=False):
    def _rb(uri):
        FakeAdapter.calls.append(("readback",))
        if fail:
            raise RuntimeError("iio_attr: no such attribute")
        return {"uri": uri, "tx_sample_rate_hz": rate, "tx_lo_hz": lo,
                "tx_hardwaregain_db": gain, "tx_rf_bandwidth_hz": 1_000_000.0}
    return _rb


def make_args(**kw):
    argv = ["--enable-rf", "--freq", "866000000", "--rf-path", "conducted", "--attenuator-db", "30"]
    args = runner.build_parser().parse_args(argv)
    for k, v in kw.items():
        setattr(args, k, v)
    return args


def test_dry_run_validates_default_waveform():
    assert runner.main([], input_fn=lambda _: "")["status"] == "dry_run_ok"
    out = runner.main(["--freq", "866000000"], input_fn=lambda _: "")
    d = out["derived_configuration"]
    assert d["tx_rate_requested_hz"] == 2_083_333 and d["rx_rate_requested_hz"] == 2_048_000
    assert d["frames_in_capture"] >= 2


def test_old_ambiguous_waveform_is_rejected():
    with pytest.raises(ValueError, match="bpsk_frame_v2"):
        runner.load_waveform(PROJECT_ROOT / "results/baseband/prepared/bpsk_joined_seed42.json")


def test_enable_rf_requires_explicit_frequency():
    with pytest.raises(SystemExit, match="--freq is required"):
        runner.main(["--enable-rf", "--rf-path", "conducted", "--attenuator-db", "30"],
                    input_fn=lambda _: "TRANSMIT")


def test_physical_flow_tx_overlaps_capture_and_saves_rx_not_tx(sandbox):
    iq, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    rx = simulate_capture(spec, repeats=5, cfo_hz=15_000, phase=0.4, esn0_db=14,
                          start_offset=12_345, amplitude=25.0, seed=11, n_capture=1_048_576)
    captured = to_u8(rx)

    def fake_capture(freq, rate, gain, n, discard, dev):
        FakeAdapter.calls.append(("capture",))
        info = {"actual_sample_rate_hz": RX_RATE, "returncode": 0,
                "actual_sample_rate_source": "test", "requested_sample_rate_hz": int(rate)}
        return captured.copy(), info

    args = make_args(settle_s=0.0, tx_rate=2_083_333.0, rx_rate=RX_RATE)
    rec = runner.run_physical(args, iq, meta, spec, input_fn=lambda _: "TRANSMIT",
                              adapter_cls=FakeAdapter, capture_fn=fake_capture,
                              readback_fn=fake_readback(rate=TX_RATE))
    order = [c[0] for c in FakeAdapter.calls]
    assert order.index("start") < order.index("readback") < order.index("capture") < order.index("stop")
    # Receiver and sidecar use the READ-BACK TX rate, not the requested one.
    assert rec["tx_sample_rate_hz_used"] == TX_RATE
    assert rec["tx"]["readback"]["tx_sample_rate_hz"] == TX_RATE
    assert not runner.pluto_tx_adapter.RF_ENABLED

    saved = np.fromfile(rec["rx_capture_file"], dtype=np.uint8)
    np.testing.assert_array_equal(saved, captured)
    tx_bytes = np.fromfile(meta["iq_file_resolved"], dtype=np.uint8)
    assert saved.nbytes != tx_bytes.nbytes or not np.array_equal(saved, tx_bytes)
    side = json.loads(Path(rec["rx_capture_file"]).with_suffix(".json").read_text())
    assert side["rx_sample_rate_hz"] == RX_RATE and "NOT transmit data" in side["content"]

    assert rec["status"] == "frames_detected"
    assert rec["receiver"]["ber"] == 0.0
    assert rec["receiver"]["total_payload_bits_compared"] >= 3 * 512

    # Offline re-processing of the saved capture gives the same answer.
    off_args = runner.build_parser().parse_args(["--rx-file", rec["rx_capture_file"], "--no-save"])
    off = runner.run_offline(off_args, spec, meta)
    assert off["receiver"]["ber"] == rec["receiver"]["ber"]
    assert off["receiver"]["frames_detected"] == rec["receiver"]["frames_detected"]


def test_no_confirmation_means_no_transmission(sandbox):
    iq, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    rec = runner.run_physical(make_args(), iq, meta, spec, input_fn=lambda _: "yes",
                              adapter_cls=FakeAdapter, capture_fn=None)
    assert rec is None and FakeAdapter.calls == []
    assert not runner.pluto_tx_adapter.RF_ENABLED


def test_capture_failure_still_stops_tx_and_reports_no_ber(sandbox):
    iq, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)

    def failing_capture(*a):
        raise TimeoutError("no data")

    rec = runner.run_physical(make_args(settle_s=0.0), iq, meta, spec,
                              input_fn=lambda _: "TRANSMIT",
                              adapter_cls=FakeAdapter, capture_fn=failing_capture,
                              readback_fn=fake_readback())
    assert [c[0] for c in FakeAdapter.calls][-1] == "stop"
    assert rec["status"] == "failed_at_capture" and "receiver" not in rec
    assert not runner.pluto_tx_adapter.RF_ENABLED


def test_parse_rtl_exact_rate_and_clipping():
    stderr = "Found 1 device(s)\nExact sample rate is: 2083333.135571 Hz\n"
    assert runner.parse_rtl_exact_rate(stderr) == pytest.approx(2083333.135571)
    assert runner.parse_rtl_exact_rate("nothing") is None
    assert runner.clipping_fraction(np.array([0, 10, 255, 128], np.uint8)) == 0.5


# ------------------------------------------------------------
# PlutoTXAdapter start()/stop() and cyclic buffer size (stub GNU Radio)
# ------------------------------------------------------------
@pytest.fixture
def stub_gnuradio(monkeypatch):
    import sys
    import types
    from unittest.mock import MagicMock

    sink_args = {}

    def sink(*args):
        sink_args["args"] = args
        return MagicMock()

    gr_mod = types.SimpleNamespace(top_block=lambda name: MagicMock())
    iio_mod = types.SimpleNamespace(fmcomms2_sink_fc32=sink)
    blocks_mod = types.SimpleNamespace(vector_source_c=lambda *a, **k: object())
    pkg = types.ModuleType("gnuradio")
    pkg.gr, pkg.iio, pkg.blocks = gr_mod, iio_mod, blocks_mod
    monkeypatch.setitem(sys.modules, "gnuradio", pkg)
    monkeypatch.setitem(sys.modules, "gnuradio.gr", gr_mod)
    monkeypatch.setitem(sys.modules, "gnuradio.iio", iio_mod)
    monkeypatch.setitem(sys.modules, "gnuradio.blocks", blocks_mod)
    yield sink_args
    runner.pluto_tx_adapter.set_rf_enabled(False)


def test_cyclic_buffer_holds_whole_waveform(stub_gnuradio):
    A = runner.pluto_tx_adapter.PlutoTXAdapter
    a = A()
    a.prepare(np.ones(262_144, dtype=np.complex64))
    a.build_flowgraph()
    assert stub_gnuradio["args"][2] == 262_144 and stub_gnuradio["args"][3] is True
    # One TX channel = I rail + Q rail (gr-iio 3.10 ch_en is per rail).
    assert stub_gnuradio["args"][1] == [True, True]
    assert stub_gnuradio["args"][0] == "ip:192.168.2.1"
    b = A(buffer_size=32_768)
    b.prepare(np.ones(262_144, dtype=np.complex64))
    with pytest.raises(ValueError, match="truncated"):
        b.build_flowgraph()


def test_start_is_gated_nonblocking_and_stop_releases(stub_gnuradio):
    A = runner.pluto_tx_adapter.PlutoTXAdapter
    a = A(uri="ip:192.168.2.1", sample_rate=2_083_333)
    a.configure(866_000_000, 30)
    a.prepare(np.ones(1000, dtype=np.complex64) * 0.5, 0.1)
    runner.pluto_tx_adapter.set_rf_enabled(False)
    with pytest.raises(RuntimeError, match="DISABLED"):
        a.start()
    runner.pluto_tx_adapter.set_rf_enabled(True)
    status = a.start()
    assert status["status"] == "transmitting" and status["sample_rate_hz"] == 2_083_333
    a._top_block.start.assert_called_once()
    a._sink.set_samplerate.assert_called_with(2_083_333)
    # Pluto has only TX channel 0.
    a._sink.set_attenuation.assert_called_once_with(0, 30)
    a.stop()
    assert a._closed and a._top_block is None


# ------------------------------------------------------------
# Stage 1 review fixes: RF cleanup, band enforcement, readback, provenance
# ------------------------------------------------------------
class ExplodingAdapter(FakeAdapter):
    fail_at = None

    def __init__(self, **kwargs):
        if self.fail_at == "construct":
            raise RuntimeError("boom construct")
        super().__init__(**kwargs)

    def configure(self, freq, att):
        if self.fail_at == "configure":
            raise ValueError("boom configure")
        super().configure(freq, att)

    def prepare(self, iq, scale):
        if self.fail_at == "prepare":
            raise ValueError("boom prepare")
        super().prepare(iq, scale)

    def start(self):
        if self.fail_at == "start":
            FakeAdapter.calls.append(("start_failed",))
            raise RuntimeError("boom start")
        return super().start()


@pytest.mark.parametrize("stage", ["construct", "configure", "prepare", "start"])
def test_rf_flag_cleared_and_tx_stopped_on_any_failure(sandbox, stage):
    iq, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    ExplodingAdapter.fail_at = stage

    def capture_must_not_run(*a):
        raise AssertionError("capture reached")

    rec = runner.run_physical(make_args(settle_s=0.0), iq, meta, spec,
                              input_fn=lambda _: "TRANSMIT", adapter_cls=ExplodingAdapter,
                              capture_fn=capture_must_not_run, readback_fn=fake_readback())
    assert not runner.pluto_tx_adapter.RF_ENABLED
    assert rec["status"] == f"failed_at_{stage}"
    names = [c[0] for c in FakeAdapter.calls]
    if stage != "construct":
        assert names[-1] == "stop"
    assert "capture" not in names


def test_rf_flag_cleared_even_if_stop_raises(sandbox):
    iq, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)

    class BadStop(FakeAdapter):
        def stop(self):
            raise RuntimeError("stop failed")

    rec = runner.run_physical(make_args(settle_s=0.0), iq, meta, spec,
                              input_fn=lambda _: "TRANSMIT", adapter_cls=BadStop,
                              capture_fn=lambda *a: (_ for _ in ()).throw(TimeoutError("x")),
                              readback_fn=fake_readback())
    assert not runner.pluto_tx_adapter.RF_ENABLED
    assert rec["stop_error"].startswith("RuntimeError")


def test_rf_flag_cleared_on_keyboard_interrupt(sandbox):
    iq, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)

    def interrupted(*a):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        runner.run_physical(make_args(settle_s=0.0), iq, meta, spec,
                            input_fn=lambda _: "TRANSMIT", adapter_cls=FakeAdapter,
                            capture_fn=interrupted, readback_fn=fake_readback())
    assert not runner.pluto_tx_adapter.RF_ENABLED
    assert [c[0] for c in FakeAdapter.calls][-1] == "stop"


@pytest.mark.parametrize("freq", [865_000_000, 864_000_000, 867_700_000, 900_000_000])
def test_out_of_band_frequency_refused_before_any_hardware(sandbox, freq):
    iq, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    with pytest.raises(SystemExit, match="not inside"):
        runner.run_physical(make_args(freq=freq), iq, meta, spec,
                            input_fn=lambda _: pytest.fail("operator asked"),
                            adapter_cls=FakeAdapter, capture_fn=None, readback_fn=fake_readback())
    assert FakeAdapter.calls == []
    with pytest.raises(SystemExit, match="not inside"):
        runner.main(["--enable-rf", "--freq", str(freq), "--rf-path", "conducted",
                     "--attenuator-db", "30"], input_fn=lambda _: "TRANSMIT")


def test_band_edges():
    _, _, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    half = 2_083_333.0 / 4 * 1.35 / 2
    runner.enforce_band(865_000_000 + half + 1, 2_083_333.0, spec)
    runner.enforce_band(868_000_000 - half - 1, 2_083_333.0, spec)
    with pytest.raises(SystemExit):
        runner.enforce_band(865_000_000 + half - 1, 2_083_333.0, spec)


@pytest.mark.parametrize("rb,msg", [
    (dict(fail=True), "readback"),
    (dict(lo=866_100_000.0), "TX LO readback"),
    (dict(gain=-10.0), "hardwaregain"),
    (dict(rate=30_720_000.0), "not running the waveform at its design rate"),
    (dict(rate=2_083_333.0 * 1.001), "design rate"),
])
def test_readback_failure_or_mismatch_aborts_before_capture(sandbox, rb, msg):
    iq, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    rec = runner.run_physical(make_args(settle_s=0.0), iq, meta, spec,
                              input_fn=lambda _: "TRANSMIT", adapter_cls=FakeAdapter,
                              capture_fn=lambda *a: pytest.fail("captured"),
                              readback_fn=fake_readback(**rb))
    assert rec["status"] == "failed_at_readback" and msg in rec["error"]
    assert [c[0] for c in FakeAdapter.calls][-1] == "stop"
    assert not runner.pluto_tx_adapter.RF_ENABLED


def test_read_pluto_tx_state_uses_output_channels_and_fails_closed():
    import types
    seen = []
    values = {("voltage0", "sampling_frequency"): "2083333",
              ("voltage0", "rf_bandwidth"): "1000000",
              ("voltage0", "hardwaregain"): "-30.000000 dB",
              ("altvoltage1", "frequency"): "866000000"}

    def run(cmd, **kw):
        seen.append(cmd)
        assert cmd[:6] == ["iio_attr", "-u", "ip:192.168.2.1", "-o", "-c", "ad9361-phy"]
        return types.SimpleNamespace(returncode=0, stdout=values[(cmd[6], cmd[7])] + "\n", stderr="")

    st = runner.pluto_tx_adapter.read_pluto_tx_state("ip:192.168.2.1", run=run)
    assert st["tx_sample_rate_hz"] == 2083333.0 and st["tx_lo_hz"] == 866e6
    assert st["tx_hardwaregain_db"] == -30.0 and len(seen) == 4

    def bad(cmd, **kw):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="No such channel")

    with pytest.raises(RuntimeError, match="No such channel"):
        runner.pluto_tx_adapter.read_pluto_tx_state("ip:192.168.2.1", run=bad)


def test_parse_iio_attr_verbose_form():
    out = "dev 'ad9361-phy', channel 'voltage0' (output), attr 'sampling_frequency', value '2083333'"
    assert runner.pluto_tx_adapter.parse_iio_attr_value(out) == 2083333.0
    with pytest.raises(ValueError):
        runner.pluto_tx_adapter.parse_iio_attr_value("ERROR")


def _write_capture(tmp_path, sidecar, n=4096, name="cap"):
    path = tmp_path / f"{name}.cu8"
    np.full(2 * n, 128, dtype=np.uint8).tofile(path)
    if sidecar is not None:
        path.with_suffix(".json").write_text(sidecar if isinstance(sidecar, str) else json.dumps(sidecar))
    return path


def _good_sidecar(meta, n=4096):
    return {"data_kind": "rtl_sdr_rx_capture", "waveform_payload_hex": meta["payload_hex"],
            "rx_sample_rate_hz": RX_RATE, "tx_sample_rate_hz": TX_RATE, "samples": n}


@pytest.mark.parametrize("mutate,msg", [
    (lambda s: None, "Missing sidecar"),
    (lambda s: "{not json", "not valid JSON"),
    (lambda s: {k: v for k, v in s.items() if k != "data_kind"}, "data_kind"),
    (lambda s: {**s, "data_kind": "pluto_tx_waveform"}, "data_kind"),
    (lambda s: {**s, "content": "NOT transmit data", "data_kind": None}, "data_kind"),
    (lambda s: {**s, "waveform_payload_hex": "00" * 64}, "payload_hex"),
    (lambda s: {k: v for k, v in s.items() if k != "rx_sample_rate_hz"}, "rx_sample_rate_hz"),
    (lambda s: {**s, "tx_sample_rate_hz": 0}, "tx_sample_rate_hz"),
    (lambda s: {**s, "samples": 1}, "samples"),
    (lambda s: [1, 2], "JSON object"),
])
def test_offline_provenance_fails_closed(tmp_path, mutate, msg):
    _, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    side = mutate(_good_sidecar(meta))
    path = _write_capture(tmp_path, side)
    args = runner.build_parser().parse_args(["--rx-file", str(path), "--no-save",
                                             "--rx-rate-override", "2048000"])
    with pytest.raises(SystemExit, match=msg):
        runner.run_offline(args, spec, meta)


def test_offline_accepts_valid_provenance_and_flags_simulated(tmp_path):
    _, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    side = {**_good_sidecar(meta), "data_kind": "simulated_rx_capture"}
    path = _write_capture(tmp_path, side)
    args = runner.build_parser().parse_args(["--rx-file", str(path), "--no-save"])
    rec = runner.run_offline(args, spec, meta)
    assert rec["simulated"] is True and rec["status"] == "no_frame_detected"
    assert rec["receiver"]["ber"] is None


# ------------------------------------------------------------
# Hardware-integration debugging pass: config validation, RTL capture path,
# Pluto channel/URI/rate, SRO correction, legacy CLI
# ------------------------------------------------------------
@pytest.mark.parametrize("override,msg", [
    (dict(tx_rate=2_400_000.0), "design rate"),
    (dict(tx_rate=1_000_000.0), "FIR"),
    (dict(rx_rate=500_000.0), "not supported by the RTL-SDR"),
    (dict(rx_rate=256_000.0), "does not fit"),
    (dict(capture_samples=200_000), "shorter than 2 frames"),
    (dict(freq=865_000_000), "not inside"),
])
def test_configuration_validation_fails_closed_before_hardware(sandbox, override, msg):
    iq, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    with pytest.raises(SystemExit, match=msg):
        runner.run_physical(make_args(**override), iq, meta, spec,
                            input_fn=lambda _: pytest.fail("operator asked"),
                            adapter_cls=FakeAdapter, capture_fn=None, readback_fn=fake_readback())
    assert FakeAdapter.calls == []
    argv = ["--freq", str(override.get("freq", 866_000_000))]
    for k in ("tx_rate", "rx_rate", "capture_samples"):
        if k in override:
            argv += [f"--{k.replace('_', '-')}", str(override[k])]
    with pytest.raises(SystemExit, match=msg):
        runner.main(argv)  # dry run applies the same checks


def test_defaults_are_verified_hardware_values():
    args = runner.build_parser().parse_args([])
    assert args.pluto_uri == "ip:192.168.2.1"
    assert args.rx_rate == 2_048_000 and args.tx_rate == 2_083_333


def test_rtl_exact_rate_formula():
    from src.radio.hardware_config import rtl_exact_sample_rate
    assert rtl_exact_sample_rate(2_048_000) == 2_048_000.0
    assert rtl_exact_sample_rate(2_083_333) == pytest.approx(2083333.135571, abs=1e-5)
    with pytest.raises(ValueError):
        rtl_exact_sample_rate(500_000)


def _fake_capture_exact(data, stderr="", returncode=0):
    from src.radio.rtl_capture import CaptureResult

    def f(command, expected_bytes, timeout_s):
        f.command = command
        return CaptureResult(data=data[:expected_bytes], stderr=stderr, returncode=returncode)
    return f


def test_sensor_capture_raw_returns_received_bytes_and_actual_rate(monkeypatch):
    from src.radio import rtl_sdr_sensor as mod
    n, discard = 4096, 1024
    data = np.arange(2 * (n + discard), dtype=np.uint32).astype(np.uint8).tobytes()
    fake = _fake_capture_exact(data, stderr="Exact sample rate is: 2083333.135571 Hz\n")
    monkeypatch.setattr(mod, "capture_exact", fake)
    sensor = mod.RTLSDRSensor([866_000_000], sample_rate=2_083_333, gain=20.7)
    raw, info = sensor.capture_raw(866_000_000, n, discard)
    assert raw.tobytes() == data[2 * discard:]
    assert info["actual_sample_rate_hz"] == pytest.approx(2083333.135571)
    assert info["captured_samples"] == n and info["center_frequency_hz"] == 866_000_000
    assert fake.command[:2] == ["rtl_sdr", "-d"] and "2083333" in fake.command
    # 2.048 MS/s: exact, librtlsdr prints nothing -> formula value.
    monkeypatch.setattr(mod, "capture_exact", _fake_capture_exact(data))
    raw, info = mod.RTLSDRSensor([866_000_000]).capture_raw(866_000_000, n, discard)
    assert info["actual_sample_rate_hz"] == 2_048_000.0


@pytest.mark.parametrize("stderr,rc,msg", [
    ("", 1, "exit code 1"),
    ("WARNING: Failed to set sample rate.\n", 0, "Failed to set sample rate"),
    ("Exact sample rate is: 2000000.000000 Hz\n", 0, "formula"),
])
def test_sensor_capture_raw_fails_closed(monkeypatch, stderr, rc, msg):
    from src.radio import rtl_sdr_sensor as mod
    data = bytes(2 * 5000)
    monkeypatch.setattr(mod, "capture_exact", _fake_capture_exact(data, stderr, rc))
    with pytest.raises(RuntimeError, match=msg):
        mod.RTLSDRSensor([866_000_000], sample_rate=2_083_333).capture_raw(866_000_000, 4096, 0)


def test_sensor_rejects_unsupported_rtl_rate():
    from src.radio.rtl_sdr_sensor import RTLSDRSensor
    with pytest.raises(ValueError, match="not supported"):
        RTLSDRSensor([866_000_000], sample_rate=500_000, bandwidth=100_000)


def test_runner_capture_uses_sensor_path(monkeypatch):
    from src.radio import rtl_sdr_sensor as mod
    data = bytes(range(256)) * 64
    monkeypatch.setattr(mod, "capture_exact", _fake_capture_exact(data))
    raw, info = runner.capture_rtl(866_000_000, 2_048_000, 28.0, 4096, 0)
    assert raw.tobytes() == data[:8192] and info["actual_sample_rate_hz"] == 2_048_000.0


def test_pluto_adapter_rejects_rates_needing_fir():
    A = runner.pluto_tx_adapter.PlutoTXAdapter
    with pytest.raises(ValueError, match="FIR"):
        A(sample_rate=2_048_000)
    with pytest.raises(ValueError):
        A(sample_rate=70_000_000)
    assert A(sample_rate=2_083_333).sample_rate == 2_083_333


def test_legacy_adapter_cli_refuses_rf(monkeypatch):
    monkeypatch.setattr("sys.argv", ["pluto_tx_adapter.py", "--enable-rf"])
    with pytest.raises(SystemExit, match="run_hardware_experiment"):
        runner.pluto_tx_adapter.main()
    assert not runner.pluto_tx_adapter.RF_ENABLED


def test_receiver_refuses_wildly_inconsistent_rates():
    from src.radio.bpsk_receiver import convert_rate
    with pytest.raises(ValueError, match="inconsistent"):
        convert_rate(np.zeros(10, complex), 2_083_333, 256_000)


@pytest.mark.parametrize("sro", [0.0, 20.0, -35.0])
def test_receiver_sync_sro_correction_uses_estimate(sro):
    import src.receiver_sync as rs
    from src.radio.waveform_generator import generate_waveform
    ref, _, _ = generate_waveform("BPSK", 32768, 4, 0.35, 1)
    ref = ref.astype(np.complex128)
    rx = rs.apply_channel(ref, 37, 1.0, 0.4, 0.0, sro, 25.0, np.random.default_rng(3))
    r = rs.synchronize_receiver(ref, rx, actual_sro_ppm=sro, actual_delay=37, target_snr_db=25.0)
    assert r.detected_delay == 37
    assert abs(r.estimated_sro_ppm - sro) < 3.0
    assert r.measured_snr_db > 20.0   # old fixed 2083333/2048000 ratio: about -40 dB


def test_sro_correction_is_noop_below_threshold_and_inverts_add_sro():
    import src.receiver_sync as rs
    x = np.exp(2j * np.pi * 0.01 * np.arange(20000))
    assert rs.apply_sro_correction(x, 1e-9) is x
    y = rs.apply_sro_correction(rs.add_sro(x, 40.0), 40.0)
    assert np.max(np.abs(y[100:-1000] - x[100:-1000])) < 1e-3


def test_rx_only_never_touches_pluto_and_saves_rx_with_provenance(sandbox, monkeypatch):
    _, meta, spec = runner.load_waveform(runner.DEFAULT_WAVEFORM)
    rng = np.random.default_rng(4)
    noise = (rng.normal(0, 8, 2 * 600_000) + 127.5).clip(0, 255).astype(np.uint8)

    def fake_capture(freq, rate, gain, n, discard, dev):
        return noise[: 2 * n].copy(), {"actual_sample_rate_hz": 2_048_000.0, "returncode": 0,
                                       "actual_sample_rate_source": "test",
                                       "requested_sample_rate_hz": int(rate)}

    def no_pluto(*a, **k):
        raise AssertionError("Pluto touched")

    monkeypatch.setattr(runner.pluto_tx_adapter, "PlutoTXAdapter", no_pluto)
    monkeypatch.setattr(runner.pluto_tx_adapter, "read_pluto_tx_state", no_pluto)
    args = runner.build_parser().parse_args(["--rx-only", "--freq", "866000000",
                                             "--capture-samples", "600000"])
    rec = runner.run_rx_only(args, meta, spec, capture_fn=fake_capture)
    assert rec["tx_active"] is False and rec["status"] == "no_frame_detected"
    assert rec["receiver"]["ber"] is None
    assert not runner.pluto_tx_adapter.RF_ENABLED
    saved = np.fromfile(rec["rx_capture_file"], dtype=np.uint8)
    np.testing.assert_array_equal(saved, noise[:1_200_000])
    # The saved capture passes offline provenance validation.
    off = runner.run_offline(runner.build_parser().parse_args(
        ["--rx-file", rec["rx_capture_file"], "--no-save"]), spec, meta)
    assert off["status"] == "no_frame_detected"


def test_modes_are_mutually_exclusive():
    with pytest.raises(SystemExit, match="mutually exclusive"):
        runner.main(["--rx-only", "--enable-rf", "--freq", "866000000"])
