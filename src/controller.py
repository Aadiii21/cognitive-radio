
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
        ("BPSK", 1.0),
        ("QPSK", 2.0),
        ("16-QAM", 4.0),
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
        modulation_hysteresis=0.03,
    ):
        if min_dwell_steps < 0:
            raise ValueError("min_dwell_steps cannot be negative.")
        if target_pdr is not None and not 0 < target_pdr < 1:
            raise ValueError("target_pdr must be between 0 and 1.")
        if pdr_window < 1:
            raise ValueError("pdr_window must be at least 1.")
        if not 0 <= switch_cost_fraction < 1:
            raise ValueError("switch_cost_fraction must be in [0, 1).")
        if modulation_hysteresis < 0:
            raise ValueError("modulation_hysteresis cannot be negative.")

        self.current_channel = initial_channel
        self.switch_delay_steps = switch_delay_steps
        self.min_utility_gain = min_utility_gain
        self.min_dwell_steps = min_dwell_steps
        self.target_pdr = target_pdr
        self.switch_cost_fraction = switch_cost_fraction
        self.modulation_hysteresis = modulation_hysteresis

        self.steps_since_switch = min_dwell_steps
        self.recent_outcomes = deque(maxlen=pdr_window)
        self.current_modulation = None

    @property
    def rolling_pdr(self):
        if not self.recent_outcomes:
            return None

        return sum(self.recent_outcomes) / len(self.recent_outcomes)

    def observe(self, success):
        self.recent_outcomes.append(bool(success))

    def _threshold(self, modulation):
        return {
            "BPSK": 4.0,
            "QPSK": 8.0,
            "16-QAM": 16.0,
        }[modulation]

    def choose_modulation(self, snr):
        candidates = []

        for name, rate in self.MODULATIONS:
            probability = packet_success_probability(snr, name)
            candidates.append((rate * probability, name, rate))

        _, name, rate = max(candidates)

        return name, self._threshold(name), rate

    def _select_modulation(self, snr, current_modulation=None):
        candidates = [
            (
                name,
                rate,
                packet_success_probability(snr, name),
            )
            for name, rate in self.MODULATIONS
        ]

        if self.target_pdr is None:
            return max(candidates, key=lambda item: item[1] * item[2])

        eligible = [
            candidate
            for candidate in candidates
            if candidate[2] >= self.target_pdr
        ]

        if eligible:
            selected = max(eligible, key=lambda item: item[1])
        else:
            selected = max(candidates, key=lambda item: item[2])

        current = next(
            (
                candidate
                for candidate in candidates
                if candidate[0] == current_modulation
            ),
            None,
        )

        reliability_degraded = (
            self.rolling_pdr is not None
            and self.rolling_pdr < self.target_pdr
        )

        if current is not None and not reliability_degraded:
            _, current_rate, current_probability = current
            _, selected_rate, selected_probability = selected

            if (
                current_probability >= self.target_pdr
                and selected_rate <= current_rate
                and selected_probability - current_probability
                < self.modulation_hysteresis
            ):
                selected = current

        return selected

    def choose_reliable_modulation(self, snr):
        if self.target_pdr is None:
            return self.choose_modulation(snr)

        name, rate, _ = self._select_modulation(
            snr,
            current_modulation=self.current_modulation,
        )

        self.current_modulation = name

        return name, self._threshold(name), rate

    def channel_utility(self, snr):
        modulation, rate, probability = self._select_modulation(
            snr,
            current_modulation=self.current_modulation,
        )

        return rate * probability, modulation, rate, probability

    def decide(self, channel_snrs):
        channel_snrs = list(channel_snrs)

        if not channel_snrs:
            raise ValueError("At least one channel SNR is required.")

        if not 0 <= self.current_channel < len(channel_snrs):
            raise ValueError("Current channel index is out of range.")

        current = self.current_channel
        current_snr = channel_snrs[current]

        (
            current_utility,
            current_modulation,
            current_rate,
            current_pdr,
        ) = self.channel_utility(current_snr)

        # Evaluate every channel before applying the dwell-time restriction.
        candidates = []

        for channel, snr in enumerate(channel_snrs):
            utility, modulation, rate, probability = (
                self.channel_utility(snr)
            )

            if channel != current:
                utility *= 1.0 - self.switch_cost_fraction

            candidates.append(
                (utility, channel, modulation, rate, probability)
            )

        (
            best_utility,
            best_channel,
            _,
            _,
            best_pdr,
        ) = max(candidates, key=lambda item: item[0])

        # Permit emergency switching when recent reliability is poor
        # and the best-utility alternative is predicted to meet the target.
        reliability_rescue = (
            self.target_pdr is not None
            and self.rolling_pdr is not None
            and self.rolling_pdr < self.target_pdr
            and best_channel != current
            and best_pdr >= self.target_pdr
        )

        # Dwell time blocks normal switching, not reliability rescue.
        if (
            self.steps_since_switch < self.min_dwell_steps
            and not reliability_rescue
        ):
            self.steps_since_switch += 1
            self.current_modulation = current_modulation

            return Decision(
                current,
                current_modulation,
                current_rate,
                "stay",
                current_snr,
                current_utility,
                current_pdr,
                self.rolling_pdr,
            )

        if best_channel != current and (
            reliability_rescue
            or best_utility
            > current_utility + self.min_utility_gain
        ):
            self.current_channel = best_channel
            self.steps_since_switch = 0
            action = "switch_channel"
        else:
            self.steps_since_switch += 1
            action = "stay"

        snr = channel_snrs[self.current_channel]

        utility, modulation, rate, predicted_pdr = (
            self.channel_utility(snr)
        )

        self.current_modulation = modulation

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
