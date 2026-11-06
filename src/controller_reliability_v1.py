
from collections import deque
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
    predicted_pdr: float
    rolling_pdr: float | None


class CognitiveController:
    MODULATIONS = [
        ("BPSK", 4.0, 1.0),
        ("QPSK", 8.0, 2.0),
        ("16-QAM", 16.0, 4.0),
    ]

    def __init__(
        self,
        initial_channel=0,
        switch_delay_steps=2,
        min_utility_gain=0.10,
        min_dwell_steps=0,
        target_pdr=None,
        pdr_window=100,
        switch_cost_fraction=0.15,
    ):
        if min_dwell_steps < 0:
            raise ValueError("min_dwell_steps cannot be negative")
        if target_pdr is not None and not 0 < target_pdr < 1:
            raise ValueError("target_pdr must be None or between 0 and 1")
        if pdr_window < 1:
            raise ValueError("pdr_window must be at least 1")
        if switch_delay_steps < 0:
            raise ValueError("switch_delay_steps cannot be negative")
        if not 0 <= switch_cost_fraction < 1:
            raise ValueError("switch_cost_fraction must be in [0, 1)")

        self.current_channel = initial_channel
        self.switch_delay_steps = switch_delay_steps
        self.min_utility_gain = min_utility_gain
        self.min_dwell_steps = min_dwell_steps
        self.target_pdr = target_pdr
        self.switch_cost_fraction = switch_cost_fraction
        self.steps_since_switch = min_dwell_steps
        self.recent_outcomes = deque(maxlen=pdr_window)

    @property
    def rolling_pdr(self):
        if not self.recent_outcomes:
            return None
        return sum(self.recent_outcomes) / len(self.recent_outcomes)

    def observe(self, success):
        """Record the outcome of a transmitted packet."""
        self.recent_outcomes.append(bool(success))

    def choose_modulation(self, snr):
        """Throughput-oriented choice, retained for baseline policies."""
        candidates = []
        for name, _, rate in self.MODULATIONS:
            p_success = packet_success_probability(snr, name)
            candidates.append((rate * p_success, name, rate))

        _, name, rate = max(candidates)
        threshold = next(t for n, t, _ in self.MODULATIONS if n == name)
        return name, threshold, rate

    def choose_reliable_modulation(self, snr):
        """Choose the fastest modulation predicted to meet the PDR target."""
        if self.target_pdr is None:
            return self.choose_modulation(snr)

        candidates = []
        for name, _, rate in self.MODULATIONS:
            p_success = packet_success_probability(snr, name)
            candidates.append((name, rate, p_success))

        eligible = [c for c in candidates if c[2] >= self.target_pdr]
        if eligible:
            name, rate, _ = max(eligible, key=lambda c: c[1])
        else:
            # If no mode meets the target, select the most reliable mode.
            name, rate, _ = max(candidates, key=lambda c: c[2])

        threshold = next(t for n, t, _ in self.MODULATIONS if n == name)
        return name, threshold, rate

    def channel_utility(self, snr):
        modulation, _, rate = self.choose_reliable_modulation(snr)
        p_success = packet_success_probability(snr, modulation)
        return rate * p_success, modulation, rate, p_success

    def decide(self, channel_snrs):
        channel_snrs = list(channel_snrs)

        if not channel_snrs:
            raise ValueError("At least one channel SNR is required.")
        if not 0 <= self.current_channel < len(channel_snrs):
            raise ValueError("Current channel index is out of range.")

        current = self.current_channel
        current_snr = channel_snrs[current]
        current_utility, current_mod, current_rate, current_pdr = (
            self.channel_utility(current_snr)
        )

        # Stay on this channel during the minimum dwell interval.
        if self.steps_since_switch < self.min_dwell_steps:
            self.steps_since_switch += 1
            return Decision(
                current, current_mod, current_rate, "stay",
                current_snr, current_utility, current_pdr,
                self.rolling_pdr,
            )

        candidates = []
        for channel, snr in enumerate(channel_snrs):
            utility, modulation, rate, p_success = self.channel_utility(snr)

            if channel != current:
                utility *= 1.0 - self.switch_cost_fraction

            candidates.append(
                (utility, channel, modulation, rate, p_success)
            )

        best_utility, best_channel, _, _, best_pdr = max(
            candidates, key=lambda item: item[0]
        )

        # Reliability rescue: switch if observed or predicted reliability
        # is below target and another channel is predicted to meet it.
        reliability_rescue = (
            self.target_pdr is not None
            and (
                current_pdr < self.target_pdr
                or (
                    self.rolling_pdr is not None
                    and self.rolling_pdr < self.target_pdr
                )
            )
            and best_channel != current
            and best_pdr >= self.target_pdr
        )

        if best_channel != current and (
            reliability_rescue
            or best_utility > current_utility + self.min_utility_gain
        ):
            self.current_channel = best_channel
            self.steps_since_switch = 0
            action = "switch_channel"
        else:
            self.steps_since_switch += 1
            action = "stay"

        snr = channel_snrs[self.current_channel]
        utility, modulation, rate, predicted_pdr = self.channel_utility(snr)

        return Decision(
            self.current_channel,
            modulation,
            rate,
            action,
            snr,
            utility,
            predicted_pdr,
            self.rolling_pdr,
        )
