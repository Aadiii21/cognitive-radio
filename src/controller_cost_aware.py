from dataclasses import dataclass

from src.metrics import packet_success_probability


@dataclass
class Decision:
    channel: int
    modulation: str
    data_rate: float
    action: str
    estimated_snr: float
    expected_utility: float


class CognitiveController:
    """Select modulation and channel using expected delivered data."""

    MODULATIONS = [
        ("BPSK", 4.0, 1.0),
        ("QPSK", 8.0, 2.0),
        ("16-QAM", 16.0, 4.0),
    ]

    def __init__(
        self,
        initial_channel=0,
        switch_delay_steps=2,
        switch_penalty=0.15,
        min_utility_gain=0.10,
    ):
        self.current_channel = initial_channel
        self.switch_delay_steps = switch_delay_steps
        self.switch_penalty = switch_penalty
        self.min_utility_gain = min_utility_gain

    def choose_modulation(self, snr):
        # Choose the modulation with the highest expected delivered data.
        candidates = []

        for name, threshold, rate in self.MODULATIONS:
            success = packet_success_probability(snr, name)
            candidates.append((rate * success, name, rate))

        _, name, rate = max(candidates)
        return name, self._threshold(name), rate

    def _threshold(self, modulation):
        return next(
            threshold
            for name, threshold, _ in self.MODULATIONS
            if name == modulation
        )

    def channel_utility(self, snr):
        modulation, _, rate = self.choose_modulation(snr)
        success = packet_success_probability(snr, modulation)
        return rate * success, modulation, rate

    def decide(self, channel_snrs):
        channel_snrs = list(channel_snrs)

        if not channel_snrs:
            raise ValueError("At least one channel SNR is required.")

        if not 0 <= self.current_channel < len(channel_snrs):
            raise ValueError("Current channel index is out of range.")

        current = self.current_channel
        current_utility, _, _ = self.channel_utility(channel_snrs[current])

        alternatives = []
        for channel, snr in enumerate(channel_snrs):
            utility, modulation, rate = self.channel_utility(snr)

            if channel != current:
                # Approximate the throughput lost during a handoff.
                utility *= max(
                    0.0,
                    1.0 - self.switch_penalty * self.switch_delay_steps,
                )

            alternatives.append((utility, channel, modulation, rate))

        best_utility, best_channel, _, _ = max(
            alternatives, key=lambda item: item[0]
        )

        if (
            best_channel != current
            and best_utility > current_utility + self.min_utility_gain
        ):
            self.current_channel = best_channel
            action = "switch_channel"
        else:
            action = "stay"

        snr = channel_snrs[self.current_channel]
        utility, modulation, rate = self.channel_utility(snr)

        return Decision(
            channel=self.current_channel,
            modulation=modulation,
            data_rate=rate,
            action=action,
            estimated_snr=snr,
            expected_utility=utility,
        )
