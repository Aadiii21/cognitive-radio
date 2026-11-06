import numpy as np
import pytest

from src.channel_model import ChannelModel


def test_same_seed_produces_identical_traces():
    first = ChannelModel(seed=2026)
    second = ChannelModel(seed=2026)

    trace_first = np.array([first.step() for _ in range(100)])
    trace_second = np.array([second.step() for _ in range(100)])

    assert np.array_equal(trace_first, trace_second)
    assert first.burst_count == second.burst_count


def test_different_seeds_produce_different_traces():
    first = ChannelModel(seed=2026)
    second = ChannelModel(seed=2027)

    trace_first = np.array([first.step() for _ in range(100)])
    trace_second = np.array([second.step() for _ in range(100)])

    assert not np.array_equal(trace_first, trace_second)


def test_reset_reproduces_original_trace_and_burst_count():
    model = ChannelModel(seed=2026)

    original = np.array([model.step() for _ in range(100)])
    original_bursts = model.burst_count

    model.reset()
    assert model.burst_count == 0
    assert model.time == 0

    replayed = np.array([model.step() for _ in range(100)])

    assert np.array_equal(original, replayed)
    assert model.burst_count == original_bursts
    assert model.time == 100


def test_snr_is_finite_and_within_configured_bounds():
    model = ChannelModel(seed=2026)

    trace = np.array([model.step() for _ in range(1000)])

    assert np.isfinite(trace).all()
    assert (trace >= -5.0).all()
    assert (trace <= 30.0).all()


def test_step_returns_one_snr_per_channel():
    model = ChannelModel(n_channels=4, seed=2026)

    assert model.step().shape == (4,)


@pytest.mark.parametrize("n_channels", [0, -1])
def test_invalid_channel_count_raises(n_channels):
    with pytest.raises(ValueError):
        ChannelModel(n_channels=n_channels)


def test_negative_volatility_raises():
    with pytest.raises(ValueError):
        ChannelModel(volatility=-1.0)


@pytest.mark.parametrize("probability", [-0.1, 1.1])
def test_invalid_burst_probability_raises(probability):
    with pytest.raises(ValueError):
        ChannelModel(burst_probability=probability)


def test_zero_burst_probability_never_generates_bursts():
    model = ChannelModel(
        seed=2026,
        burst_probability=0.0,
    )

    for _ in range(1000):
        model.step()

    assert model.burst_count == 0


def test_burst_probability_one_generates_a_burst_every_step():
    model = ChannelModel(
        seed=2026,
        burst_probability=1.0,
    )

    for _ in range(100):
        model.step()

    assert model.burst_count == 100
