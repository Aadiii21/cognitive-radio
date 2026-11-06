import pytest

from src.metrics import packet_success_probability, summarize_run


THRESHOLDS = {
    "BPSK": 4.0,
    "QPSK": 8.0,
    "16-QAM": 16.0,
}


@pytest.mark.parametrize("modulation", list(THRESHOLDS))
def test_probability_is_half_at_modulation_threshold(modulation):
    probability = packet_success_probability(
        THRESHOLDS[modulation],
        modulation,
    )

    assert probability == pytest.approx(0.5)


@pytest.mark.parametrize("modulation", list(THRESHOLDS))
def test_probability_increases_with_snr(modulation):
    snr_values = [-5, 0, 5, 10, 15, 20, 25, 30]
    probabilities = [
        packet_success_probability(snr, modulation)
        for snr in snr_values
    ]

    assert all(
        lower < higher
        for lower, higher in zip(
            probabilities,
            probabilities[1:],
        )
    )


@pytest.mark.parametrize("modulation", list(THRESHOLDS))
@pytest.mark.parametrize("snr", [-5, 0, 10, 20, 30])
def test_probability_stays_between_zero_and_one(snr, modulation):
    probability = packet_success_probability(snr, modulation)

    assert 0.0 <= probability <= 1.0


def test_invalid_modulation_is_rejected():
    with pytest.raises(KeyError):
        packet_success_probability(10.0, "INVALID")


def test_empty_success_list_has_zero_pdr():
    metrics = summarize_run(
        successes=[],
        delivered_bits=0.0,
        elapsed_steps=10,
        switches=0,
        attempted_packets=0,
        transmission_steps=0,
    )

    assert metrics["packet_delivery_ratio"] == 0.0
    assert metrics["throughput_bits_per_step"] == 0.0
    assert metrics["service_availability"] == 0.0


def test_failed_packets_do_not_increase_delivered_bits():
    metrics = summarize_run(
        successes=[True, False, True, False],
        delivered_bits=4.0,
        elapsed_steps=4,
        switches=0,
        attempted_packets=4,
        transmission_steps=4,
    )

    assert metrics["packet_delivery_ratio"] == pytest.approx(0.5)
    assert metrics["throughput_bits_per_step"] == pytest.approx(1.0)


def test_availability_uses_transmission_steps():
    metrics = summarize_run(
        successes=[True] * 8,
        delivered_bits=16.0,
        elapsed_steps=10,
        switches=1,
        attempted_packets=8,
        transmission_steps=8,
    )

    assert metrics["service_availability"] == pytest.approx(0.8)
