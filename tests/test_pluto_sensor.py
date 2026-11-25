import numpy as np
import pytest

from src.radio.pluto_sensor import PlutoSensor
from src.radio.base import ChannelMeasurement


@pytest.fixture
def sensor():
    return PlutoSensor(
        center_frequencies=[500_000_000, 501_000_000, 502_000_000]
    )


def test_synthetic_iq_analysis(sensor):
    rng = np.random.default_rng(42)
    n = 262144
    t = np.arange(n) / sensor.sample_rate

    iq = (
        0.5 * np.exp(2j * np.pi * 50_000 * t)
        + 0.01 * (
            rng.normal(size=n) + 1j * rng.normal(size=n)
        )
    )

    result = sensor.analyze_iq(iq)

    assert np.isfinite(result["estimated_snr_db"])
    assert result["estimated_snr_db"] > 20


def test_measurement_structure(sensor):
    measurement = ChannelMeasurement(
        channel_index=0,
        snr_db=10.0,
        timestamp_step=1,
        source="pluto",
    )

    assert measurement.source == "pluto"
    assert measurement.channel_index == 0


def test_insufficient_iq_samples(sensor):
    with pytest.raises(ValueError):
        sensor.analyze_iq(np.ones(100, dtype=np.complex64))


def test_non_finite_iq(sensor):
    iq = np.ones(2048, dtype=np.complex64)
    iq[0] = np.nan

    with pytest.raises(ValueError):
        sensor.analyze_iq(iq)


def test_invalid_frequency():
    with pytest.raises(ValueError):
        PlutoSensor(center_frequencies=[])


def test_invalid_bandwidth():
    with pytest.raises(ValueError):
        PlutoSensor(
            center_frequencies=[500_000_000],
            bandwidth=2_000_000,
        )


def test_closed_sensor(sensor):
    sensor.close()

    with pytest.raises(RuntimeError):
        sensor.measure_channels()
