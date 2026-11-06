
import pytest

from src.controller import CognitiveController
from src.metrics import packet_success_probability


def test_empty_channel_list_raises():
    controller = CognitiveController()

    with pytest.raises(ValueError):
        controller.decide([])


def test_invalid_channel_index_raises():
    controller = CognitiveController(initial_channel=5)

    with pytest.raises(ValueError):
        controller.decide([10.0, 12.0, 15.0])


def test_modulation_selection_returns_valid_values():
    controller = CognitiveController()

    modulation, threshold, rate = controller.choose_modulation(15.0)

    assert modulation in {"BPSK", "QPSK", "16-QAM"}
    assert threshold in {4.0, 8.0, 16.0}
    assert rate in {1.0, 2.0, 4.0}


def test_candidate_evaluation_does_not_mutate_modulation():
    controller = CognitiveController(target_pdr=0.95)
    controller.current_modulation = "BPSK"

    controller.channel_utility(18.0)

    assert controller.current_modulation == "BPSK"


def test_switch_updates_channel_and_resets_dwell_counter():
    controller = CognitiveController(
        initial_channel=0,
        min_utility_gain=0.0,
        switch_cost_fraction=0.0,
    )

    decision = controller.decide([5.0, 25.0])

    assert decision.channel == 1
    assert decision.action == "switch_channel"
    assert controller.steps_since_switch == 0


def test_reliable_modulation_meets_target_when_feasible():
    controller = CognitiveController(target_pdr=0.95)

    modulation, _, rate = controller.choose_reliable_modulation(18.0)
    probability = packet_success_probability(18.0, modulation)

    assert probability >= 0.95
    assert rate in {1.0, 2.0, 4.0}


def test_rolling_pdr_tracks_recent_outcomes():
    controller = CognitiveController(pdr_window=3)

    assert controller.rolling_pdr is None

    controller.observe(True)
    controller.observe(False)
    controller.observe(True)

    assert controller.rolling_pdr == pytest.approx(2 / 3)

    controller.observe(False)

    assert controller.rolling_pdr == pytest.approx(1 / 3)


def test_reliability_rescue_can_bypass_dwell_time():
    controller = CognitiveController(
        initial_channel=0,
        min_dwell_steps=20,
        target_pdr=0.95,
        switch_cost_fraction=0.0,
        min_utility_gain=100.0,
    )

    # Simulate a controller that has just switched channels.
    controller.steps_since_switch = 0

    # Make recent packet delivery reliability fall below the target.
    for _ in range(100):
        controller.observe(False)

    decision = controller.decide([5.0, 30.0])

    assert decision.channel == 1
    assert decision.action == "switch_channel"


def test_ordinary_switch_respects_dwell_time():
    controller = CognitiveController(
        initial_channel=0,
        min_dwell_steps=20,
        target_pdr=None,
        switch_cost_fraction=0.0,
        min_utility_gain=0.0,
    )

    # Simulate being inside the dwell period.
    controller.steps_since_switch = 0

    decision = controller.decide([5.0, 30.0])

    assert decision.channel == 0
    assert decision.action == "stay"
