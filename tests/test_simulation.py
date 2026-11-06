import pytest

from src.metrics import summarize_run
from src.switching import SwitchingDelay


def test_two_step_switching_delay_blocks_exactly_two_steps():
    delay = SwitchingDelay(delay_steps=2)

    delay.start()

    assert delay.is_active
    assert delay.consume_step() is True
    assert delay.is_active
    assert delay.consume_step() is True
    assert delay.is_active is False
    assert delay.consume_step() is False


def test_zero_switching_delay_blocks_no_steps():
    delay = SwitchingDelay(delay_steps=0)

    delay.start()

    assert delay.is_active is False
    assert delay.consume_step() is False


def test_negative_switching_delay_raises():
    with pytest.raises(ValueError):
        SwitchingDelay(delay_steps=-1)


def test_availability_matches_transmission_steps():
    metrics = summarize_run(
        successes=[True] * 8,
        delivered_bits=8.0,
        elapsed_steps=10,
        switches=1,
        attempted_packets=8,
        transmission_steps=8,
    )

    assert metrics["attempted_packets"] == 8
    assert metrics["service_availability"] == pytest.approx(0.8)


def test_no_switch_delay_preserves_all_transmission_steps():
    metrics = summarize_run(
        successes=[True] * 10,
        delivered_bits=10.0,
        elapsed_steps=10,
        switches=0,
        attempted_packets=10,
        transmission_steps=10,
    )

    assert metrics["attempted_packets"] == 10
    assert metrics["service_availability"] == pytest.approx(1.0)
