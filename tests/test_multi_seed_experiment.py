from types import SimpleNamespace

import numpy as np

import src.multi_seed_experiment as experiment


class FakeChannelModel:
    def __init__(self, **kwargs):
        pass

    def step(self):
        return np.array([18.0, 18.0, 18.0])


class FakeController:
    def __init__(self, **kwargs):
        self.calls = 0

    def choose_modulation(self, snr):
        return "QPSK", 8.0, 2.0

    def decide(self, channel_snrs):
        self.calls += 1

        if self.calls == 1:
            return SimpleNamespace(
                channel=1,
                action="switch_channel",
                modulation="QPSK",
                data_rate=2.0,
            )

        return SimpleNamespace(
            channel=1,
            action="stay",
            modulation="QPSK",
            data_rate=2.0,
        )

    def observe(self, success):
        pass


def test_two_step_switch_causes_two_unavailable_steps(monkeypatch):
    monkeypatch.setattr(experiment, "STEPS", 6)
    monkeypatch.setattr(experiment, "SWITCH_DELAY_STEPS", 2)
    monkeypatch.setattr(experiment, "ChannelModel", FakeChannelModel)
    monkeypatch.setattr(experiment, "CognitiveController", FakeController)
    monkeypatch.setattr(
        experiment, "FixedQPSKChannelController", FakeController
    )

    results = experiment.run_once(seed=2026, environment="Low")

    for strategy in (
        "channel_switching",
        "hybrid",
        "reliability_constrained",
    ):
        metrics = results[strategy]

        assert metrics["switches"] == 1
        assert metrics["attempted_packets"] == 4
        assert metrics["service_availability"] == 4 / 6
