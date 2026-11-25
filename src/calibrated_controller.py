import numpy as np

from src.controller_cost_aware import CognitiveController
from src.noise_calibration import noise_for_snr


LOGISTIC_MODELS = {
    "BPSK": (42.198029, -153.934945),
    "QPSK": (180.955965, -994.912015),
    "16-QAM": (79.256161, -1032.793196),
}

NOISE_RANGE = (0.02, 0.45)


def calibrated_packet_success(noise_voltage, modulation):
    if modulation not in LOGISTIC_MODELS:
        raise ValueError(f"Unknown modulation: {modulation}")

    noise = float(noise_voltage)

    if not np.isfinite(noise):
        raise ValueError("Noise voltage must be finite.")

    if not NOISE_RANGE[0] <= noise <= NOISE_RANGE[1]:
        raise ValueError(
            f"Noise voltage {noise:.5f} outside "
            f"calibration range {NOISE_RANGE}"
        )

    intercept, slope = LOGISTIC_MODELS[modulation]
    z = np.clip(intercept + slope * noise, -40, 40)

    return float(1.0 / (1.0 + np.exp(-z)))


class CalibratedCognitiveController(CognitiveController):

    def noise_from_snr(self, snr, modulation):
        # Boundary saturation is an explicit approximation.
        return noise_for_snr(
            float(snr),
            modulation,
            clip=True
        )

    def choose_modulation(self, snr):
        candidates = []

        for name, threshold, rate in self.MODULATIONS:
            noise = self.noise_from_snr(snr, name)
            success = calibrated_packet_success(noise, name)

            candidates.append(
                (rate * success, name, threshold, rate)
            )

        _, name, threshold, rate = max(candidates)

        return name, threshold, rate

    def channel_utility(self, snr):
        modulation, _, rate = self.choose_modulation(snr)

        noise = self.noise_from_snr(snr, modulation)
        success = calibrated_packet_success(noise, modulation)

        return rate * success, modulation, rate
