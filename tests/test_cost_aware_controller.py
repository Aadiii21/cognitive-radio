import pytest

from src.controller_cost_aware import CognitiveController


def test_controller_stays_when_current_channel_is_best():
    controller = CognitiveController(initial_channel=0)

    decision = controller.decide([25.0, 10.0, 5.0])

    assert decision.channel == 0
    assert decision.action == "stay"


def test_controller_switches_to_much_better_channel():
    controller = CognitiveController(initial_channel=0)

    decision = controller.decide([3.0, 25.0, 5.0])

    assert decision.channel == 1
    assert decision.action == "switch_channel"


def test_switch_penalty_discourages_marginal_switch():
    low_penalty = CognitiveController(
        initial_channel=0,
        switch_penalty=0.0,
    )
    high_penalty = CognitiveController(
        initial_channel=0,
        switch_penalty=0.30,
    )

    snrs = [12.0, 18.0, 5.0]

    low_decision = low_penalty.decide(snrs)
    high_decision = high_penalty.decide(snrs)

    assert low_decision.action == "switch_channel"
    assert high_decision.action == "stay"

def test_empty_channel_list_raises():
    controller = CognitiveController()

    with pytest.raises(ValueError):
        controller.decide([])


def test_invalid_initial_channel_raises():
    controller = CognitiveController(initial_channel=5)

    with pytest.raises(ValueError):
        controller.decide([10.0, 12.0, 15.0])
