from unittest.mock import patch

import numpy as np
import pytest

from src.radio.rtl_capture import CaptureResult
from src.radio.rtl_sdr_sensor import RTLSDRSensor


def make_sensor(**kwargs):
    defaults = {
        "center_frequencies": [98_000_000, 100_000_000],
        "sample_rate": 256_000,
        "bandwidth": 20_000,
        "capture_samples": 1024,
    }
    defaults.update(kwargs)
    return RTLSDRSensor(**defaults)


def test_analyze_iq_returns_required_measurements():
    sensor = make_sensor()

    rng = np.random.default_rng(42)
    noise = (
        rng.normal(0, 0.1, 8192)
        + 1j * rng.normal(0, 0.1, 8192)
    )

    t = np.arange(8192) / sensor.sample_rate
    signal = 2.0 * np.exp(2j * np.pi * 2000 * t)

    result = sensor.analyze_iq(signal + noise)

    assert set(result) == {
        "signal_power_db_relative",
        "noise_floor_db_relative",
        "estimated_snr_db",
    }

    assert np.isfinite(result["estimated_snr_db"])
    assert result["estimated_snr_db"] > 10


def test_analyze_iq_rejects_insufficient_samples():
    sensor = make_sensor()

    with pytest.raises(ValueError, match="Insufficient IQ samples"):
        sensor.analyze_iq(np.zeros(100, dtype=np.complex64))


def test_capture_iq_decodes_unsigned_bytes():
    sensor = make_sensor(capture_samples=1024)

    raw = bytes([128, 128] * 1024)

    result = CaptureResult(data=raw, stderr="", returncode=0)

    with patch(
        "src.radio.rtl_sdr_sensor.capture_exact",
        return_value=result,
    ) as capture:
        iq = sensor._capture_iq(98_000_000)

    command = capture.call_args.args[0]
    assert command[-1] == "-"
    assert "-n" not in command
    assert capture.call_args.kwargs["expected_bytes"] == 2048
    assert len(iq) == 1024
    assert np.iscomplexobj(iq)
    assert np.all(np.isfinite(iq))


def test_capture_iq_rejects_incomplete_capture():
    sensor = make_sensor(capture_samples=1024)

    result = CaptureResult(data=bytes([128, 128] * 100), stderr="", returncode=0)

    with patch(
        "src.radio.rtl_sdr_sensor.capture_exact",
        return_value=result,
    ):
        with pytest.raises(RuntimeError, match="Incomplete IQ capture"):
            sensor._capture_iq(98_000_000)


def test_capture_iq_reports_rtl_sdr_failure():
    sensor = make_sensor()

    result = CaptureResult(data=b"", stderr="Device not found", returncode=1)

    with patch(
        "src.radio.rtl_sdr_sensor.capture_exact",
        return_value=result,
    ):
        with pytest.raises(RuntimeError, match="Device not found"):
            sensor._capture_iq(98_000_000)


def test_measure_channels_returns_measurements():
    sensor = make_sensor(center_frequencies=[98_000_000, 100_000_000])

    fake_iq = np.ones(2048, dtype=np.complex64)

    sensor._capture_iq = lambda frequency: fake_iq
    sensor.analyze_iq = lambda iq: {
        "signal_power_db_relative": 10.0,
        "noise_floor_db_relative": 2.0,
        "estimated_snr_db": 8.0,
    }

    measurements = sensor.measure_channels()

    assert len(measurements) == 2
    assert [m.channel_index for m in measurements] == [0, 1]
    assert all(m.source == "rtl_sdr" for m in measurements)
    assert all(m.snr_db == 8.0 for m in measurements)
    assert all(m.timestamp_step == 1 for m in measurements)
    assert all(m.received_power_dbm is None for m in measurements)


def test_measure_channels_increments_timestamp():
    sensor = make_sensor(center_frequencies=[98_000_000])

    sensor._capture_iq = lambda frequency: np.ones(
        2048, dtype=np.complex64
    )
    sensor.analyze_iq = lambda iq: {
        "signal_power_db_relative": 10.0,
        "noise_floor_db_relative": 2.0,
        "estimated_snr_db": 8.0,
    }

    first = sensor.measure_channels()
    second = sensor.measure_channels()

    assert first[0].timestamp_step == 1
    assert second[0].timestamp_step == 2


def test_closed_sensor_rejects_measurement():
    sensor = make_sensor()
    sensor.close()

    with pytest.raises(RuntimeError, match="sensor is closed"):
        sensor.measure_channels()
