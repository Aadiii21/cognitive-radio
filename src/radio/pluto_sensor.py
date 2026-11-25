import subprocess

import numpy as np

from src.radio.hardware_config import PLUTO_URI

from src.radio.base import ChannelMeasurement


class PlutoSensor:
    """
    Receive-only ADALM-Pluto spectrum sensor.

    Captures IQ samples through GNU Radio IIO and estimates
    relative in-band signal power and adjacent-band noise.

    This is not calibrated absolute RF SNR.
    """

    def __init__(
        self,
        center_frequencies,
        uri=PLUTO_URI,
        sample_rate=2_400_000,
        gain=30.0,
        bandwidth=180_000,
        capture_samples=262_144,
    ):
        try:
            frequencies = [int(f) for f in center_frequencies]
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Center frequencies must be integers.")

        if not frequencies or any(f <= 0 for f in frequencies):
            raise ValueError("Valid center frequencies are required.")

        if int(sample_rate) < 2_083_333:
            raise ValueError("Pluto sample rate must be at least 2083333.")

        if int(bandwidth) <= 0 or int(bandwidth) >= int(sample_rate) / 2:
            raise ValueError("Invalid measurement bandwidth.")

        if int(capture_samples) < 1024:
            raise ValueError("At least 1024 samples are required.")

        if not np.isfinite(float(gain)) or not -3 <= float(gain) <= 71:
            raise ValueError("Pluto gain must be between -3 and 71 dB.")

        self.center_frequencies = frequencies
        self.uri = uri
        self.sample_rate = int(sample_rate)
        self.gain = float(gain)
        self.bandwidth = int(bandwidth)
        self.capture_samples = int(capture_samples)

        # AD9363 RX hardware bandwidth is separate from estimator bandwidth.
        # Minimum supported RX bandwidth is 200 kHz.
        self.rf_bandwidth = max(200_000, self.bandwidth)
        self._hardware_configured = False

        self.timestamp_step = 0
        self.closed = False

    def _configure_hardware(self):
        if self._hardware_configured:
            return

        command = [
            "iio_attr",
            "-u", self.uri,
            "-c", "ad9361-phy",
            "voltage0",
            "rf_bandwidth",
            str(self.rf_bandwidth),
        ]

        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        verify_command = [
            "iio_attr",
            "-u", self.uri,
            "-c", "ad9361-phy",
            "voltage0",
            "rf_bandwidth",
        ]

        result = subprocess.run(
            verify_command,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        values = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
        ]

        try:
            verified = values and all(
                int(value) == self.rf_bandwidth for value in values
            )
        except ValueError:
            verified = False

        if not verified:
            raise RuntimeError(
                f"Pluto RX bandwidth verification failed: {values}"
            )

        self._hardware_configured = True

    def _capture_iq(self, frequency):
        if self.closed:
            raise RuntimeError("Pluto sensor is closed.")

        self._configure_hardware()

        from gnuradio import gr, blocks, iio

        class Capture(gr.top_block):
            def __init__(inner):
                super().__init__("Pluto IQ Capture")

                inner.source = iio.fmcomms2_source_fc32(
                    self.uri, [True, True], 32768
                )

                inner.source.set_frequency(frequency)
                inner.source.set_samplerate(self.sample_rate)
                inner.source.set_gain_mode(0, "manual")
                inner.source.set_gain(0, self.gain)
                inner.source.set_quadrature(True)
                inner.source.set_rfdc(True)
                inner.source.set_bbdc(True)

                inner.head = blocks.head(
                    gr.sizeof_gr_complex,
                    self.capture_samples,
                )

                inner.sink = blocks.vector_sink_c()

                inner.connect(inner.source, inner.head, inner.sink)

        tb = Capture()
        tb.run()

        iq = np.asarray(tb.sink.data(), dtype=np.complex64)

        if len(iq) != self.capture_samples:
            raise RuntimeError(
                f"Incomplete Pluto capture: expected "
                f"{self.capture_samples}, received {len(iq)} samples."
            )

        return iq

    def analyze_iq(self, iq):
        iq = np.asarray(iq, dtype=np.complex64)

        if len(iq) < 1024:
            raise ValueError("Insufficient IQ samples.")

        if not np.isfinite(iq).all():
            raise ValueError("IQ data contains invalid values.")

        window = np.hanning(len(iq))

        spectrum = np.fft.fftshift(
            np.fft.fft(iq * window)
        )

        psd = np.abs(spectrum) ** 2 / np.sum(window ** 2)

        offsets = np.fft.fftshift(
            np.fft.fftfreq(
                len(iq),
                d=1 / self.sample_rate,
            )
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

        cutoff = np.percentile(guard_power, 80)
        clean_guard = guard_power[guard_power <= cutoff]

        signal_power = float(np.mean(psd[signal_mask]))
        noise_power = float(np.median(clean_guard))

        snr = 10 * np.log10(
            max(signal_power, 1e-20)
            / max(noise_power, 1e-20)
        )

        return {
            "signal_power_db_relative": float(
                10 * np.log10(max(signal_power, 1e-20))
            ),
            "noise_floor_db_relative": float(
                10 * np.log10(max(noise_power, 1e-20))
            ),
            "estimated_snr_db": float(snr),
        }

    def measure_channels(self):
        if self.closed:
            raise RuntimeError("Pluto sensor is closed.")

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
                    source="pluto",
                    received_power_dbm=None,
                    noise_floor_dbm=None,
                )
            )

            print(
                f"Channel {index} | "
                f"{frequency / 1e6:.3f} MHz | "
                f"Estimated SNR: {result['estimated_snr_db']:.2f} dB"
            )

            print(
                f"    Signal power: "
                f"{result['signal_power_db_relative']:.2f} dB | "
                f"Noise floor: "
                f"{result['noise_floor_db_relative']:.2f} dB"
            )

        return measurements

    def close(self):
        self.closed = True
