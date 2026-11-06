import numpy as np


class ChannelModel:
    """Simulate channels with configurable interference dynamics."""

    def __init__(
        self,
        n_channels=3,
        seed=42,
        volatility=1.5,
        burst_probability=0.08,
    ):
        if n_channels < 1:
            raise ValueError("n_channels must be positive")
        if volatility < 0:
            raise ValueError("volatility cannot be negative")
        if not 0 <= burst_probability <= 1:
            raise ValueError("burst_probability must be between 0 and 1")

        self.n_channels = n_channels
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.volatility = volatility
        self.burst_probability = burst_probability
        self.time = 0
        self.burst_count = 0

        if n_channels <= 3:
            self.base_snr = np.array([18.0, 13.0, 9.0])[:n_channels]
        else:
            self.base_snr = np.linspace(18.0, 9.0, n_channels)

        self.interference = np.zeros(n_channels)

    def step(self):
        """Advance one time step and return each channel's SNR in dB."""
        self.time += 1

        self.interference = (
            0.85 * self.interference
            + self.rng.normal(
                0.0, self.volatility, self.n_channels
            )
        )

        if self.rng.random() < self.burst_probability:
            channel = self.rng.integers(0, self.n_channels)
            scale = self.volatility / 1.5
            self.interference[channel] += self.rng.uniform(
                6.0, 14.0
            ) * scale
            self.burst_count += 1

        snr = self.base_snr - np.maximum(self.interference, 0.0)
        snr += self.rng.normal(0.0, 1.0, self.n_channels)

        return np.clip(snr, -5.0, 30.0)

    def reset(self):
        """Restore the initial state, including the random sequence."""
        self.rng = np.random.default_rng(self.seed)
        self.time = 0
        self.burst_count = 0
        self.interference = np.zeros(self.n_channels)
