import numpy as np

from src.channel_model import ChannelModel
from src.calibrated_controller import calibrated_packet_success
from src.noise_calibration import noise_for_snr

from src.radio.base import (
    RadioInterface,
    ChannelMeasurement,
    PacketResult,
)


class SimulatedRadio(RadioInterface):
    """Radio backend driven by the existing channel and calibration models."""

    def __init__(
        self,
        seed=42,
        volatility=1.5,
        burst_probability=0.08,
        n_channels=3,
    ):
        self.model = ChannelModel(
            n_channels=n_channels,
            seed=seed,
            volatility=volatility,
            burst_probability=burst_probability,
        )

        self.rng = np.random.default_rng(seed + 50000)

        self.n_channels = n_channels
        self.current_channel = 0
        self.current_modulation = "QPSK"

        self.timestamp_step = 0
        self.latest_measurements = None
        self.closed = False

    def _ensure_open(self):
        if self.closed:
            raise RuntimeError("Radio is closed.")

    def measure_channels(self):
        self._ensure_open()

        snrs = self.model.step()
        self.timestamp_step += 1

        measurements = []

        for index, snr in enumerate(snrs):
            measurements.append(
                ChannelMeasurement(
                    channel_index=index,
                    snr_db=float(snr),
                    timestamp_step=self.timestamp_step,
                    source="simulation",
                )
            )

        self.latest_measurements = measurements

        return measurements

    def set_channel(self, channel_index):
        self._ensure_open()

        if not isinstance(channel_index, int):
            raise TypeError("Channel index must be an integer.")

        if not 0 <= channel_index < self.n_channels:
            raise ValueError("Channel index out of range.")

        self.current_channel = channel_index

    def set_modulation(self, modulation):
        self._ensure_open()

        if modulation not in self.MODULATIONS:
            raise ValueError(f"Unsupported modulation: {modulation}")

        self.current_modulation = modulation

    def transmit_packet(self, payload):
        self._ensure_open()

        if not isinstance(payload, bytes):
            raise TypeError("Payload must be bytes.")

        if self.latest_measurements is None:
            raise RuntimeError(
                "Measure channels before transmitting a packet."
            )

        measurement = self.latest_measurements[self.current_channel]

        noise = noise_for_snr(
            measurement.snr_db,
            self.current_modulation,
            clip=True,
        )
        probability = calibrated_packet_success(
            noise,
            self.current_modulation,
        )

        success = bool(self.rng.random() < probability)

        delivered_bytes = len(payload) if success else 0

        return PacketResult(
            success=success,
            channel_index=self.current_channel,
            modulation=self.current_modulation,
            snr_db=measurement.snr_db,
            success_probability=probability,
            packet_bytes=len(payload),
            delivered_bytes=delivered_bytes,
            timestamp_step=self.timestamp_step,
        )

    def close(self):
        self.closed = True

    def reset(self):
        self._ensure_open()

        self.model.reset()
        self.rng = np.random.default_rng(self.model.seed + 50000)

        self.current_channel = 0
        self.current_modulation = "QPSK"
        self.timestamp_step = 0
        self.latest_measurements = None
