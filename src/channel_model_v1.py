import numpy as np


class ChannelModel:
    """Simulates changing channel quality and interference."""

    def __init__(self, n_channels=3, seed=42):
        self.n_channels = n_channels
        self.rng = np.random.default_rng(seed)
        self.time = 0

        self.base_snr = np.array([18.0, 13.0, 9.0])
        self.interference = np.zeros(n_channels)

    def step(self):
        """Advance the simulation by one time step."""
        self.time += 1

        # Interference varies gradually, with occasional sudden changes.
        self.interference = (
            0.85 * self.interference
            + self.rng.normal(0.0, 1.5, self.n_channels)
        )
        if self.rng.random() < 0.08:
            channel = self.rng.integers(0, self.n_channels)
            self.interference[channel] += self.rng.uniform(6.0, 14.0)

        snr = self.base_snr - np.maximum(self.interference, 0.0)
        snr += self.rng.normal(0.0, 1.0, self.n_channels)

        return np.clip(snr, -5.0, 30.0)

    def reset(self):
        self.time = 0
        self.interference = np.zeros(self.n_channels)
