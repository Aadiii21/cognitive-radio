import re

import numpy as np

from src.radio.base import ChannelMeasurement
from src.radio.hardware_config import (
    RTL_DEFAULT_SAMPLE_RATE,
    RTL_SAMPLE_RATE_RANGES,
    is_supported_rtl_rate,
    rtl_exact_sample_rate,
)
from src.radio.rtl_capture import capture_exact

_EXACT_RATE = re.compile(r"Exact sample rate is:\s*([0-9.]+)\s*Hz")
_RATE_FAILURE = "Failed to set sample rate"


def parse_rtl_exact_rate(stderr):
    """librtlsdr prints this line only when the real rate differs from the request."""
    m = _EXACT_RATE.search(stderr or "")
    return float(m.group(1)) if m else None


class RTLSDRSensor:
    """
    Receive-only RTL-SDR spectrum sensing adapter.

    Returns ChannelMeasurement objects compatible with the
    existing cognitive-radio controller.

    SNR is an estimate based on the in-band signal power
    and adjacent guard-band noise estimate. It is not
    calibrated absolute RF SNR.
    """

    def __init__(
        self,
        center_frequencies,
        sample_rate=RTL_DEFAULT_SAMPLE_RATE,
        gain=28.0,
        bandwidth=180_000,
        capture_samples=262_144,
        device_index=0,
    ):
        try:
            frequencies = [int(f) for f in center_frequencies]
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Center frequencies must be a sequence of integers.")

        if not frequencies:
            raise ValueError("At least one center frequency is required.")

        if any(f <= 0 for f in frequencies):
            raise ValueError("Center frequencies must be positive.")

        if int(sample_rate) <= 0 or int(bandwidth) <= 0:
            raise ValueError("Sample rate and bandwidth must be positive.")

        if not is_supported_rtl_rate(sample_rate):
            raise ValueError(
                f"RTL-SDR sample rate {int(sample_rate)} not supported by librtlsdr "
                f"(ranges {RTL_SAMPLE_RATE_RANGES})."
            )

        if int(bandwidth) >= int(sample_rate) / 2:
            raise ValueError("Bandwidth is too large for this configuration.")

        if int(capture_samples) < 1024:
            raise ValueError("Capture must contain at least 1024 samples.")

        if int(device_index) < 0:
            raise ValueError("Device index cannot be negative.")

        if not np.isfinite(float(gain)):
            raise ValueError("Gain must be finite.")

        self.center_frequencies = frequencies
        self.sample_rate = int(sample_rate)
        self.gain = float(gain)
        self.bandwidth = int(bandwidth)
        self.capture_samples = int(capture_samples)
        self.device_index = int(device_index)

        self.timestamp_step = 0
        self.closed = False

    def _command(self, frequency):
        return [
            "rtl_sdr",
            "-d", str(self.device_index),
            "-f", str(int(frequency)),
            "-s", str(self.sample_rate),
            "-g", str(self.gain),
            "-"
        ]

    def capture_raw(self, frequency, n_samples, discard_samples=0, timeout_s=30.0):
        """
        Capture raw RTL-SDR bytes (uint8 interleaved I/Q) for physical experiments.

        Returns (raw_uint8, info). `raw_uint8` is exactly 2*n_samples bytes of
        RECEIVED data after dropping `discard_samples` (tuner settling).
        `info["actual_sample_rate_hz"]` is the rate the RTL2832 really runs at:
        the value librtlsdr prints, cross-checked against the librtlsdr formula.
        Fails (RuntimeError) on timeout, short read, non-zero exit status,
        a sample-rate failure message, or a printed/computed rate mismatch.
        """
        if n_samples <= 0 or discard_samples < 0:
            raise ValueError("n_samples must be > 0 and discard_samples >= 0.")
        command = self._command(frequency)
        expected = 2 * (int(n_samples) + int(discard_samples))
        try:
            result = capture_exact(command, expected_bytes=expected, timeout_s=timeout_s)
        except TimeoutError as exc:
            raise RuntimeError(f"RTL-SDR capture timed out at {frequency} Hz: {exc}") from exc
        except RuntimeError as exc:
            raise RuntimeError(f"RTL-SDR capture failed at {frequency} Hz: {exc}") from exc

        stderr = result.stderr or ""
        if result.returncode != 0:
            raise RuntimeError(
                f"RTL-SDR capture failed at {frequency} Hz (exit code {result.returncode}): "
                f"{stderr.strip() or 'Unknown error'}"
            )
        if _RATE_FAILURE in stderr:
            raise RuntimeError(f"rtl_sdr reported: {_RATE_FAILURE} ({self.sample_rate} S/s).")

        raw = np.frombuffer(result.data, dtype=np.uint8)
        if len(raw) != expected:
            raise RuntimeError(f"Incomplete IQ capture: expected {expected} bytes, received {len(raw)}.")

        computed = rtl_exact_sample_rate(self.sample_rate)
        printed = parse_rtl_exact_rate(stderr)
        if printed is not None and abs(printed - computed) > 1.0:
            raise RuntimeError(
                f"rtl_sdr reports {printed} S/s but librtlsdr formula gives {computed} S/s "
                f"for a {self.sample_rate} S/s request."
            )
        info = {
            "command": command,
            "returncode": result.returncode,
            "stderr_tail": stderr[-2000:],
            "center_frequency_hz": int(frequency),
            "requested_sample_rate_hz": self.sample_rate,
            "actual_sample_rate_hz": printed if printed is not None else computed,
            "actual_sample_rate_source": ("rtl_sdr 'Exact sample rate' (matches librtlsdr formula)"
                                          if printed is not None else
                                          "librtlsdr formula; rate is exact so rtl_sdr prints none"),
            "gain_db": self.gain,
            "device_index": self.device_index,
            "discarded_samples": int(discard_samples),
            "captured_samples": int(n_samples),
        }
        return raw[2 * int(discard_samples):].copy(), info

    def _capture_iq(self, frequency):
        command = [
            "rtl_sdr",
            "-d", str(self.device_index),
            "-f", str(frequency),
            "-s", str(self.sample_rate),
            "-g", str(self.gain),
            "-",
        ]

        expected_bytes = self.capture_samples * 2

        try:
            result = capture_exact(
                command,
                expected_bytes=expected_bytes,
                timeout_s=15,
            )
        except TimeoutError as exc:
            raise RuntimeError(
                f"RTL-SDR capture timed out at {frequency} Hz."
            ) from exc
        except RuntimeError as exc:
            raise RuntimeError(
                f"RTL-SDR capture failed at {frequency} Hz: {exc}"
            ) from exc

        # Check if the process reported an error (e.g., PLL not locked, device not found)
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            raise RuntimeError(
                f"RTL-SDR capture failed at {frequency} Hz (exit code {result.returncode}): {error_msg}"
            )

        raw = np.frombuffer(result.data, dtype=np.uint8)

        if len(raw) != expected_bytes:
            raise RuntimeError(
                f"Incomplete IQ capture: expected {expected_bytes} bytes, "
                f"received {len(raw)} bytes."
            )

        i = raw[0::2].astype(np.float32) - 127.5
        q = raw[1::2].astype(np.float32) - 127.5

        return i + 1j * q

    def analyze_iq(self, iq):
        """
        Estimate in-band power and robust spectral noise floor.

        The noise estimate excludes the signal band and rejects
        unusually strong spectral bins in the guard region.

        This remains a relative estimate, not calibrated RF SNR.
        """

        iq = np.asarray(iq, dtype=np.complex64)

        if len(iq) < 1024:
            raise ValueError("Insufficient IQ samples.")

        n = len(iq)
        window = np.hanning(n)

        spectrum = np.fft.fftshift(
            np.fft.fft(iq * window)
        )

        psd = np.abs(spectrum) ** 2 / np.sum(window ** 2)

        offsets = np.fft.fftshift(
            np.fft.fftfreq(n, d=1 / self.sample_rate)
        )

        abs_offsets = np.abs(offsets)

        signal_mask = abs_offsets <= self.bandwidth / 2

        guard_mask = (
            (abs_offsets >= self.bandwidth)
            & (abs_offsets <= self.bandwidth * 2)
        )

        if not np.any(signal_mask) or not np.any(guard_mask):
            raise RuntimeError("Unable to construct signal/noise bands.")

        guard_power = psd[guard_mask]

        # Reject the strongest 20% of guard-band bins to reduce
        # contamination from narrowband interference.
        cutoff = np.percentile(guard_power, 80)
        clean_guard = guard_power[guard_power <= cutoff]

        signal_power = float(np.mean(psd[signal_mask]))
        noise_power = float(np.median(clean_guard))

        estimated_snr = 10 * np.log10(
            max(signal_power, 1e-20) / max(noise_power, 1e-20)
        )

        return {
            "signal_power_db_relative": float(
                10 * np.log10(max(signal_power, 1e-20))
            ),
            "noise_floor_db_relative": float(
                10 * np.log10(max(noise_power, 1e-20))
            ),
            "estimated_snr_db": float(estimated_snr),
        }

    def measure_channels(self):
        if self.closed:
            raise RuntimeError("RTL-SDR sensor is closed.")

        self.timestamp_step += 1
        measurements = []

        for index, frequency in enumerate(self.center_frequencies):
            iq = self._capture_iq(frequency)
            result = self.analyze_iq(iq)

            measurements.append(
                ChannelMeasurement(
                    channel_index=index,
                    snr_db=result["estimated_snr_db"],
                    timestamp_step=self.timestamp_step,
                    source="rtl_sdr",
                    received_power_dbm=None,
                    noise_floor_dbm=None,
                )
            )

            print(
                f"Channel {index} | "
                f"{frequency / 1e6:.3f} MHz | "
                f"Estimated SNR: "
                f"{result['estimated_snr_db']:.2f} dB"
            )

        return measurements

    def close(self):
        self.closed = True
