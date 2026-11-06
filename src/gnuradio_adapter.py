from dataclasses import dataclass

from src.controller_cost_aware import CognitiveController


MODULATION_INDEX = {
    "BPSK": 0,
    "QPSK": 1,
    "16-QAM": 2,
}


@dataclass
class RadioCommand:
    channel: int
    modulation: str
    modulation_index: int
    enabled: bool
    action: str
    estimated_snr: float
    expected_utility: float


class GNUradioAdapter:

    def __init__(self, controller=None, disable_threshold=0.0):
        self.controller = controller or CognitiveController()
        self.disable_threshold = disable_threshold

    def process(self, channel_snrs):
        decision = self.controller.decide(channel_snrs)

        enabled = decision.estimated_snr >= self.disable_threshold

        return RadioCommand(
            channel=decision.channel,
            modulation=decision.modulation,
            modulation_index=MODULATION_INDEX[decision.modulation],
            enabled=enabled,
            action=decision.action,
            estimated_snr=decision.estimated_snr,
            expected_utility=decision.expected_utility,
        )
