from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelMeasurement:
    channel_index: int
    snr_db: float
    timestamp_step: int
    source: str
    received_power_dbm: float | None = None
    noise_floor_dbm: float | None = None


@dataclass(frozen=True)
class PacketResult:
    success: bool
    channel_index: int
    modulation: str
    snr_db: float
    success_probability: float
    packet_bytes: int
    delivered_bytes: int
    timestamp_step: int


class RadioInterface(ABC):
    """Common interface for simulated and physical radio backends."""

    MODULATIONS = ("BPSK", "QPSK", "16-QAM")

    @abstractmethod
    def measure_channels(self) -> list[ChannelMeasurement]:
        """Measure channel conditions and return one record per channel."""

    @abstractmethod
    def set_channel(self, channel_index: int) -> None:
        """Select the transmission channel."""

    @abstractmethod
    def set_modulation(self, modulation: str) -> None:
        """Select the transmission modulation."""

    @abstractmethod
    def transmit_packet(self, payload: bytes) -> PacketResult:
        """Transmit one packet and return its measured outcome."""

    @abstractmethod
    def close(self) -> None:
        """Release radio resources."""
