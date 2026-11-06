import numpy as np

from src.controller_cost_aware import CognitiveController
from src.noise_calibration import noise_for_snr


# Fitted from refined_equal_power_calibration.csv.
# These models use GNU Radio noise voltage, not SNR in dB.
LOGISTIC_MODELS = {
    "BPSK": (42.074806, -154.056157),
    "QPSK": (56.481401, -303.631691),
    "16-QAM": (36.539672, -484.154524),
}


def calibrated_packet_success(noise_voltage, modulation):
    intercept, slope = LOGISTIC_MODELS[modulation]
    z = np.clip(intercept + slope * noise_voltage, -40, 40)
    return float(1.0 / (1.0 + np.exp(-z)))


class CalibratedCognitiveController(CognitiveController):
    """
    Cost-aware controller using empirically fitted GNU Radio
    packet-success models.
    """

    def noise_from_snr(self, snr):
        # The BPSK mapping represents the common channel SNR.
        # Modulation-specific power differences are negligible.
        return noise_for_snr(float(snr), "BPSK")

    def choose_modulation(self, snr):
        noise = self.noise_from_snr(snr)

        candidates = []

        for name, threshold, rate in self.MODULATIONS:
            success = calibrated_packet_success(noise, name)
            candidates.append((rate * success, name, rate))

        _, name, rate = max(candidates)
        return name, self._threshold(name), rate

    def channel_utility(self, snr):
        noise = self.noise_from_snr(snr)
        modulation, _, rate = self.choose_modulation(snr)

        success = calibrated_packet_success(noise, modulation)

        return rate * success, modulation, rate
