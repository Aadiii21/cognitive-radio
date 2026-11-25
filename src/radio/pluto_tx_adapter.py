#!/usr/bin/env python3
"""
Pluto TX Adapter - ADALM-Pluto Transmitter

Provides a controlled Pluto-to-RTL-SDR transmission pipeline using:
- GNU Radio 3.10.x
- GNU Radio IIO `fmcomms2_sink_fc32`

Features:
- GNU Radio flowgraph with proper block connections
- Waveform loading and preparation for transmission
- Pluto hardware configuration and TX control
- RX-side signal detection and BER/PDR measurement
- Explicit enable/disable RF transmission (default disabled)
- Mock-friendly interface for unit testing

Usage:
    python src/radio/pluto_tx_adapter.py --modulation BPSK --symbols 65536 --seed 42

Physical transmission is NOT done from this file's CLI any more; use
    python scripts/run_hardware_experiment.py --enable-rf --freq <Hz>

WARNING: RF transmission is disabled by default. Do not enable until
operator has confirmed a safe conducted RF path and applicable regulatory
authorization. Never transmit without explicit --enable-rf flag.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from src.radio.hardware_config import (
    PLUTO_TX1_CH_EN,
    PLUTO_TX_ATTENUATION_CHANNELS,
    PLUTO_URI,
    validate_pluto_sample_rate,
)

# Buffer size for stream mode (GRC's Pluto Sink default).
STREAM_BUFFER_SAMPLES = 32768

# Default to disabled RF transmission
RF_ENABLED = False


def set_rf_enabled(value: bool):
    """Enable or disable RF transmission. Default is disabled."""
    global RF_ENABLED
    RF_ENABLED = value
    status = "ENABLED" if RF_ENABLED else "DISABLED"
    print(f"\nRF TRANSMISSION STATUS: {status} (operator-controlled)")
    if not RF_ENABLED:
        print("Use --enable-rf flag to enable transmission. See docs/DEMO_GUIDE.md.")


# ============================================================
# Waveform Generation
# ============================================================
def rrc_filter(beta=0.35, sps=4, span=10):
    """Generate a root-raised-cosine pulse shaping filter."""
    n = np.arange(-span * sps // 2, span * sps // 2 + 1)
    t = n / sps
    h = np.zeros_like(t, dtype=np.float64)

    for i, x in enumerate(t):
        if np.isclose(x, 0.0):
            h[i] = 1 - beta + 4 * beta / np.pi
        elif beta > 0 and np.isclose(abs(x), 1 / (4 * beta)):
            h[i] = (
                beta / np.sqrt(2)
                * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * beta))
                   + (1 - 2 / np.pi) * np.cos(np.pi / (4 * beta)))
            )
        else:
            numerator = (
                np.sin(np.pi * x * (1 - beta))
                + 4 * beta * x * np.cos(np.pi * x * (1 + beta))
            )
            denominator = np.pi * x * (1 - (4 * beta * x) ** 2)
            h[i] = numerator / denominator

    h /= np.sqrt(np.sum(h ** 2))
    return h


def generate_symbols(modulation: str, count: int, rng: np.random.Generator):
    """Generate symbols for the specified modulation."""
    if modulation == "BPSK":
        bits = rng.integers(0, 2, count)
        return (1 - 2 * bits).astype(np.complex64)

    if modulation == "QPSK":
        bits = rng.integers(0, 2, (count, 2))
        i = 1 - 2 * bits[:, 0]
        q = 1 - 2 * bits[:, 1]
        return ((i + 1j * q) / np.sqrt(2)).astype(np.complex64)

    if modulation == "16QAM":
        bits = rng.integers(0, 2, (count, 4))
        levels = np.array([-3, -1, 3, 1])
        i_idx = 2 * bits[:, 0] + bits[:, 1]
        q_idx = 2 * bits[:, 2] + bits[:, 3]
        i = levels[i_idx]
        q = levels[q_idx]
        return ((i + 1j * q) / np.sqrt(10)).astype(np.complex64)

    raise ValueError(f"Unsupported modulation: {modulation}")


def generate_waveform(modulation: str, count: int, sps: int, beta: float, seed: int):
    """Generate a waveform with RRC pulse shaping."""
    rng = np.random.default_rng(seed)
    symbols = generate_symbols(modulation, count, rng)
    upsampled = np.zeros(count * sps, dtype=np.complex64)
    upsampled[::sps] = symbols
    taps = rrc_filter(beta=beta, sps=sps)
    iq = np.convolve(upsampled, taps, mode="same")
    iq /= np.sqrt(np.mean(np.abs(iq) ** 2))
    return iq.astype(np.complex64), symbols, taps


# ============================================================
# Pluto TX Adapter (GNU Radio IIO Flowgraph)
# ============================================================
class PlutoTXAdapter:
    """
    ADALM-Pluto transmitter adapter using GNU Radio flowgraph.

    Builds a proper GNU Radio flowgraph with:
    - blocks.vector_source_c (IQ samples)
    - iio.fmcomms2_sink_fc32 (Pluto TX sink)

    Usage requires GNU Radio 3.10.x with IIO support.
    This class is designed to be mock-friendly for unit testing.

    Attributes:
        uri: Pluto device URI (default hardware_config.PLUTO_URI = 'ip:192.168.2.1')
        sample_rate: Sample rate in Hz
        bandwidth: Bandwidth in Hz
        amplitude_scale: Amplitude scale factor for TX output
        peak_limit: Maximum peak amplitude (default 0.25)
        channel_en: Whether to enable both TX I/Q channels
    """

    def __init__(
        self,
        uri: str = PLUTO_URI,
        sample_rate: int = 2_400_000,
        bandwidth: int = 1_000_000,
        amplitude_scale: float = 0.1,
        peak_limit: float = 0.25,
        channel_en: bool = True,
        buffer_size: Optional[int] = None,
        cyclic: bool = True,
    ):
        self.uri = uri
        self.sample_rate = validate_pluto_sample_rate(sample_rate)
        self.bandwidth = int(bandwidth)
        self.amplitude_scale = float(amplitude_scale)
        self.peak_limit = float(peak_limit)
        self.channel_en = bool(channel_en)
        # None -> one cyclic buffer holding the whole prepared waveform
        # (cyclic mode) or STREAM_BUFFER_SAMPLES (stream mode).
        self.buffer_size = None if buffer_size is None else int(buffer_size)
        # cyclic=True : the device repeats one buffer holding the whole frame.
        # cyclic=False: "stream" mode, the standard GRC pattern: a repeating
        #               vector source feeds a non-cyclic sink until stop().
        self.cyclic = bool(cyclic)

        self._top_block = None
        self._source = None
        self._sink = None
        self._prepared_iq: Optional[np.ndarray] = None
        self._hardware_configured = False
        self._closed = False

        # Default hardware parameters (must be explicitly configured)
        self._frequency = 500_000_000
        self._attenuation = 30  # dB

        # Flag to track if we are in hardware mode
        self.hardware_mode = False

    def configure(self, frequency: int, attenuation: int = 30):
        """
        Configure the Pluto TX hardware.

        Args:
            frequency: Center frequency in Hz (e.g., 500_000_000)
            attenuation: Attenuation in dB (e.g., 30, between 0-60)

        Returns self for chaining.
        """
        self._frequency = int(frequency)
        if not 0 <= attenuation <= 60:
            raise ValueError("Attenuation must be between 0 and 60 dB")
        self._attenuation = int(attenuation)
        self.hardware_mode = True
        return self

    def prepare(self, iq: np.ndarray, amplitude_scale: Optional[float] = None) -> "PlutoTXAdapter":
        """
        Prepare IQ data for transmission.

        Args:
            iq: Complex64 IQ data (interleaved)
            amplitude_scale: Scale factor for TX output.
                           If None, uses self.amplitude_scale.
                           Scaling happens exactly once.

        Returns self for chaining.
        """
        iq = np.asarray(iq, dtype=np.complex64)

        if amplitude_scale is not None:
            amplitude_scale = float(amplitude_scale)
        else:
            amplitude_scale = self.amplitude_scale

        # Apply amplitude scale exactly once
        prepared = (iq * amplitude_scale).astype(np.complex64)

        # Check peak
        peak = float(np.max(np.abs(prepared)))
        if peak > self.peak_limit:
            raise ValueError(
                f"Peak amplitude {peak:.4f} exceeds limit {self.peak_limit}"
            )

        self._prepared_iq = prepared
        return self

    def build_flowgraph(self):
        """
        Build the GNU Radio flowgraph.

        Creates a flowgraph with:
        - blocks.vector_source_c (prepared IQ samples)
        - iio.fmcomms2_sink_fc32 (Pluto TX sink)

        Returns the top block. Must be called before transmit().
        """
        if self._prepared_iq is None:
            raise RuntimeError(
                "No IQ data prepared. Call prepare() first."
            )

        from gnuradio import blocks, gr, iio

        # Create the top-level flowgraph
        self._top_block = gr.top_block("Pluto TX Adapter")

        # Create source: complex vector source.
        # repeat=True keeps the flowgraph running until stop(). With
        # repeat=False the flowgraph finishes once the source is exhausted,
        # and stopping the sink can end the transmission before a receiver
        # starts capturing (likely cause of the empty 2026-11-23 captures).
        self._source = blocks.vector_source_c(
            self._prepared_iq,
            repeat=True,
            vlen=1,
        )

        # Create sink: FMComms2 IIO sink.
        # In cyclic mode the device repeats the FIRST buffer it receives, so
        # the buffer must hold the whole waveform (previously fixed at 32768,
        # which truncated a 262144-sample frame to its first 12.5 %).
        if self.cyclic:
            buffer_size = self.buffer_size or len(self._prepared_iq)
        else:
            buffer_size = self.buffer_size or STREAM_BUFFER_SAMPLES
        if self.cyclic and buffer_size < len(self._prepared_iq):
            raise ValueError(
                f"Cyclic buffer ({buffer_size}) shorter than waveform "
                f"({len(self._prepared_iq)}); the frame would be truncated."
            )
        # ch_en is one flag per I/Q rail (GNU Radio 3.10 gr-iio). The Pluto
        # has ONE TX channel, TX1 = I rail + Q rail -> [True, True]. This is
        # what GRC's Pluto Sink generates. The previous [True] enabled only
        # the I rail. I and Q are not two RF channels.
        ch_en = list(PLUTO_TX1_CH_EN) if self.channel_en else [False, False]
        if not any(ch_en):
            raise ValueError("TX1 disabled (channel_en=False): nothing to transmit.")
        self._sink = iio.fmcomms2_sink_fc32(
            self.uri,
            ch_en,
            buffer_size,
            self.cyclic,
        )

        # Connect: source -> sink
        self._top_block.connect(self._source, self._sink)

        return self._top_block

    def _init_hardware(self):
        """
        Initialize Pluto hardware configuration.

        Configures frequency, sample rate, bandwidth, and attenuation.
        This is called automatically before transmission.
        """
        if not self.hardware_mode:
            raise RuntimeError(
                "Hardware mode not configured. Call configure() first."
            )

        if self._top_block is None:
            self.build_flowgraph()

        tx_block = self._sink

        # Configure hardware via sink methods (IIO standard)
        tx_block.set_frequency(self._frequency)
        tx_block.set_samplerate(self.sample_rate)
        tx_block.set_bandwidth(self.bandwidth)
        # Pluto (AD9363, 1T1R): only TX channel 0 exists. The previous extra
        # set_attenuation(1, ...) addressed a TX2 that the Pluto does not have.
        for chan in PLUTO_TX_ATTENUATION_CHANNELS:
            tx_block.set_attenuation(chan, self._attenuation)

        # Note: No set_channel_en() calls. The confirmed API
        # does not support set_channel_en(). Channel configuration
        # is handled by the [channel_en] array in the constructor.

    def transmit(self) -> dict:
        """
        Transmit the prepared IQ data over the air.

        Returns a status dictionary.
        This method requires hardware. If called without RF enabled, raises an error.

        The flowgraph:
        1. Builds the flowgraph if not already built
        2. Initializes hardware configuration
        3. Starts the flowgraph
        4. Runs for a fixed duration (60 seconds by default)
        5. Stops and waits for the flowgraph to finish
        6. Cleans up resources
        """
        if not RF_ENABLED:
            raise RuntimeError(
                "RF transmission is DISABLED. Use --enable-rf flag to enable."
            )

        if not self.hardware_mode:
            raise RuntimeError(
                "Hardware mode not configured. Call configure() first."
            )

        if self._prepared_iq is None:
            raise RuntimeError("No IQ data prepared. Call prepare() first.")

        if self._closed:
            raise RuntimeError("Transmitter is closed.")

        # Build flowgraph if not already built
        if self._top_block is None:
            self.build_flowgraph()

        # Initialize hardware
        self._init_hardware()

        # Start the flowgraph
        self._top_block.start()

        # Run for a fixed duration (60 seconds)
        # NOTE (audit B2): GNU Radio 3.10 gr.top_block.wait() may not accept a
        # timeout argument. Unverified here; scripts/run_hardware_experiment.py
        # uses start()/stop() instead of this blocking method.
        import time
        run_duration = 60  # seconds
        self._top_block.wait(timeout=run_duration)  # wait for flowgraph to finish

        # Stop and cleanup
        self._top_block.stop()
        self._top_block.wait()

        # Save sample count before cleanup
        sample_count = len(self._prepared_iq)

        # Cleanup
        self.close()

        return {
            "status": "transmitted",
            "samples": sample_count,
            "frequency_hz": self._frequency,
            "attenuation_db": self._attenuation,
            "timestamp": datetime.now().isoformat(),
        }

    def start(self) -> dict:
        """
        Start cyclic transmission of the prepared IQ and return immediately.

        Use this when a receiver must capture while the Pluto is transmitting.
        Call stop() afterwards. Same RF safety gate as transmit().
        """
        if not RF_ENABLED:
            raise RuntimeError(
                "RF transmission is DISABLED. Use --enable-rf flag to enable."
            )
        if not self.hardware_mode:
            raise RuntimeError("Hardware mode not configured. Call configure() first.")
        if self._prepared_iq is None:
            raise RuntimeError("No IQ data prepared. Call prepare() first.")
        if self._closed:
            raise RuntimeError("Transmitter is closed.")

        if self._top_block is None:
            self.build_flowgraph()
        self._init_hardware()
        self._top_block.start()
        return {
            "status": "transmitting",
            "samples": len(self._prepared_iq),
            "frequency_hz": self._frequency,
            "sample_rate_hz": self.sample_rate,
            "bandwidth_hz": self.bandwidth,
            "attenuation_db": self._attenuation,
            "uri": self.uri,
            "tx_mode": "cyclic" if self.cyclic else "stream",
            "buffer_samples": (self.buffer_size or len(self._prepared_iq)) if self.cyclic
                              else (self.buffer_size or STREAM_BUFFER_SAMPLES),
            "timestamp": datetime.now().isoformat(),
        }

    def stop(self) -> dict:
        """Stop a transmission started with start() and release resources."""
        self.close()
        return {"status": "stopped", "timestamp": datetime.now().isoformat()}

    def close(self):
        """Close the transmitter and release resources."""
        if self._top_block is not None:
            try:
                self._top_block.stop()
                self._top_block.wait()
            except Exception:
                pass
            self._top_block = None
            self._source = None
            self._sink = None
        self._prepared_iq = None
        self._closed = True

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self.close()
        return False


# ============================================================
# Pluto TX state readback (libiio command-line tools)
# ============================================================
# AD9361 IIO layout on the ADALM-Pluto:
#   ad9361-phy, OUTPUT channel voltage0   : TX path
#       sampling_frequency  -> TX baseband rate (Hz)
#       rf_bandwidth        -> TX analog bandwidth (Hz)
#       hardwaregain        -> TX gain in dB (= -attenuation, e.g. "-30.000000 dB")
#   ad9361-phy, OUTPUT channel altvoltage1: TX_LO
#       frequency           -> TX LO (Hz)
# The INPUT channel voltage0 holds the RX equivalents, hence "-o" below.
PLUTO_TX_READBACK_ATTRS = {
    "tx_sample_rate_hz": ("voltage0", "sampling_frequency"),
    "tx_rf_bandwidth_hz": ("voltage0", "rf_bandwidth"),
    "tx_hardwaregain_db": ("voltage0", "hardwaregain"),
    "tx_lo_hz": ("altvoltage1", "frequency"),
}

_IIO_VALUE = None


def parse_iio_attr_value(output: str) -> float:
    """Parse a numeric value from iio_attr output.

    Accepts both the verbose form
        dev 'ad9361-phy', channel 'voltage0' (output), attr 'sampling_frequency', value '2083333'
    and a bare value line ("2083333", "-30.000000 dB").
    """
    import re

    global _IIO_VALUE
    if _IIO_VALUE is None:
        _IIO_VALUE = re.compile(r"value\s+'([^']*)'")
    text = (output or "").strip()
    m = _IIO_VALUE.search(text)
    candidate = m.group(1) if m else (text.splitlines()[-1] if text else "")
    num = re.match(r"\s*([-+]?\d+(?:\.\d+)?)", candidate)
    if not num:
        raise ValueError(f"Cannot parse iio_attr output: {output!r}")
    return float(num.group(1))


def read_pluto_tx_state(uri: str, run=None, timeout_s: float = 5.0) -> dict:
    """Read the configured TX state from the Pluto while it is transmitting.

    Uses `iio_attr -u <uri> -o -c ad9361-phy <channel> <attr>` (output
    channels). Raises RuntimeError if any attribute cannot be read: the
    caller must not assume a rate it could not verify.
    """
    import subprocess

    run = run or subprocess.run
    state = {"uri": uri, "method": "iio_attr -o -c ad9361-phy"}
    for key, (channel, attr) in PLUTO_TX_READBACK_ATTRS.items():
        cmd = ["iio_attr", "-u", uri, "-o", "-c", "ad9361-phy", channel, attr]
        try:
            proc = run(cmd, capture_output=True, text=True, timeout=timeout_s)
        except Exception as exc:
            raise RuntimeError(f"Readback {channel}/{attr} failed: {exc}") from exc
        if proc.returncode != 0:
            raise RuntimeError(
                f"Readback {channel}/{attr} failed (exit {proc.returncode}): "
                f"{(proc.stderr or proc.stdout or '').strip()}"
            )
        state[key] = parse_iio_attr_value(proc.stdout)
        state[f"{key}_raw"] = (proc.stdout or "").strip()
    return state


# ============================================================
# RTL-SDR IQ Capture and Signal Detection
# ============================================================
class RTLSDRReceiver:
    """
    RTL-SDR receiver for IQ capture and signal detection.

    Provides actual RTL-SDR device initialization, center-frequency
    configuration, sample-rate configuration, IQ capture, safe device
    cleanup, and signal detection with SNR estimation.

    Uses the installed RTL-SDR library (librtlsdr 0.26-5 on Arch) and
    the `rtl-sdr` command-line tool for synchronous capture.

    Attributes:
        center_frequencies: List of frequencies to monitor
        sample_rate: Sample rate in Hz
        bandwidth: Bandwidth in Hz
        capture_samples: Number of samples to capture
        device_index: RTL-SDR device index (0 = first device)
    """

    def __init__(
        self,
        center_frequencies: list[int],
        sample_rate: int = 256_000,
        bandwidth: int = 20_000,
        capture_samples: int = 1024,
        device_index: int = 0,
        gain: float = 28.0,
    ):
        self.center_frequencies = center_frequencies
        self.gain = float(gain)
        self.sample_rate = int(sample_rate)
        self.bandwidth = int(bandwidth)
        self.capture_samples = int(capture_samples)
        self.device_index = int(device_index)
        self._capture_called = False
        self._captured_iq: Optional[np.ndarray] = None
        self._device_initialized = False
        self._closed = False

    def init_device(self) -> dict:
        """
        Initialize the RTL-SDR device.

        Checks for available RTL-SDR devices and initializes the
        first one found.

        Returns:
            Dictionary with initialization status
        """
        import subprocess

        # Check if rtl-sdr command exists
        try:
            result = subprocess.run(
                ["which", "rtl_sdr"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return {
                    "initialized": False,
                    "error": "rtl_sdr command not found",
                    "require_install": "rtl-sdr package",
                }
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {
                "initialized": False,
                "error": "rtl_sdr command not found",
                "require_install": "rtl-sdr package",
            }

        # Try to find connected RTL-SDR devices
        # Note: this rtl-sdr version does NOT support 'rtl_test -l'.
        # Use a quick device scan instead.
        try:
            # Run rtl_test briefly - it auto-finds first available device
            result = subprocess.run(
                ["rtl_test", "-s", "2048000", "-t", "5"],  # 5 second timeout
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout + result.stderr

            # Check for device found in output
            if "Found 1 device(s)" in output or "Found 2 device(s)" in output or "Found 3 device(s)" in output:
                self._device_initialized = True
                self._closed = False
                self.center_frequencies = list(self.center_frequencies)

                return {
                    "initialized": True,
                    "device_count": 1,
                    "device_index": self.device_index,
                    "available": True,
                }
            else:
                # Check if there's any error about no devices
                if "No devices found" in output or "Failed to find" in output or "No device(s)" in output:
                    return {
                        "initialized": False,
                        "error": "No RTL-SDR devices detected",
                        "command": "rtl_test quick scan",
                    }
                else:
                    return {
                        "initialized": False,
                        "error": "No RTL-SDR devices detected",
                        "command": "rtl_test quick scan",
                        "details": output[-500:] if len(output) > 500 else output,
                    }

        except subprocess.TimeoutExpired:
            return {
                "initialized": False,
                "error": "rtl_test timed out",
            }

    def configure(self, frequency: int, sample_rate: Optional[int] = None):
        """
        Configure the RTL-SDR device.

        Args:
            frequency: Center frequency in Hz
            sample_rate: Sample rate in Hz (defaults to self.sample_rate)

        Returns self for chaining.
        """
        self._frequency = int(frequency)
        if sample_rate is not None:
            self.sample_rate = int(sample_rate)
        return self

    def capture_iq(self, frequency: int) -> np.ndarray:
        """
        Capture IQ samples from the RTL-SDR device.

        Uses the `rtl_sdr` command-line tool for synchronous capture.
        Expects raw unsigned 8-bit IQ interleaved (I0 Q0 I1 Q1 ...).

        Returns:
            Complex64 IQ samples
        """
        if not self._device_initialized:
            raise RuntimeError(
                "Device not initialized. Call init_device() first."
            )

        self._capture_called = True

        command = [
            "rtl_sdr",
            "-d", str(self.device_index),
            "-f", str(frequency),
            "-s", str(self.sample_rate),
            "-g", str(self.gain),
            "-",
        ]

        expected_bytes = self.capture_samples * 2

        from src.radio.rtl_capture import capture_exact

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

        # Unpack interleaved unsigned 8-bit IQ
        i = raw[0::2].astype(np.float32) - 127.5
        q = raw[1::2].astype(np.float32) - 127.5

        return i + 1j * q

    def detect_signal(
        self, iq: np.ndarray, expected_frequency: float
    ) -> dict:
        """
        Detect a BPSK signal in captured IQ data.

        Returns detection metrics including BER and PDR.
        """
        iq = np.asarray(iq, dtype=np.complex64)

        if len(iq) < 1024:
            raise ValueError("Insufficient IQ samples.")

        # Find frequency offset using FFT
        window = np.hanning(len(iq))
        spectrum = np.fft.fftshift(np.fft.fft(iq * window))
        psd = np.abs(spectrum) ** 2 / np.sum(window ** 2)

        offsets = np.fft.fftshift(np.fft.fftfreq(len(iq), d=1 / self.sample_rate))
        abs_offsets = np.abs(offsets)

        # Signal band
        signal_mask = abs_offsets <= self.bandwidth / 2

        if not np.any(signal_mask):
            return {
                "detected": False,
                "signal_power_db": -np.inf,
                "snr_db": -np.inf,
                "ber": 0.5,
                "pdr": 0.0,
                "frequency_offset_hz": 0.0,
            }

        # Estimate SNR (simple energy-based)
        signal_power = float(np.mean(psd[signal_mask]))
        noise_power = float(np.median(psd[signal_mask] * 0.1))  # heuristic
        snr = 10 * np.log10(max(signal_power, 1e-20) / max(noise_power, 1e-20))

        # Estimate frequency offset
        peak_idx = np.argmax(psd)
        frequency_offset = float(offsets[peak_idx])

        # BER estimation (simplified: use SNR-based approximation)
        # For BPSK, BER ~ Q(sqrt(2*SNR))
        from scipy.special import erfc
        if snr > 0:
            ber = 0.5 * erfc(np.sqrt(snr / 10))  # approximate
        else:
            ber = 0.5

        # PDR estimate (assuming packet is detected)
        pdr = 1.0 if snr > 0 else 0.0

        return {
            "detected": snr > 0,
            "signal_power_db": snr,
            "snr_db": snr,
            "ber": float(ber),
            "pdr": float(pdr),
            "frequency_offset_hz": frequency_offset,
        }

    def measure(self, frequency: int) -> dict:
        """
        Capture and detect signal on a single frequency.

        Returns:
            Dictionary with detection results
        """
        iq = self.capture_iq(frequency)
        return self.detect_signal(iq, frequency)

    def cleanup(self):
        """Release the RTL-SDR device."""
        self._device_initialized = False
        self._captured_iq = None
        self._closed = True

    def __enter__(self):
        """Context manager entry."""
        self.init_device()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - release device."""
        self.cleanup()
        return False


# ============================================================
# Hardware Test Script
# ============================================================
def main():
    """Command-line entry point for Pluto TX adapter."""
    parser = argparse.ArgumentParser(
        description="Pluto TX Adapter - BCH over-the-air transmission pipeline"
    )
    parser.add_argument("--modulation", choices=["BPSK", "QPSK", "16QAM"], default="BPSK")
    parser.add_argument("--symbols", type=int, default=65536)
    parser.add_argument("--sps", type=int, default=4)
    parser.add_argument("--beta", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="results/baseband/prepared")
    parser.add_argument("--frequency", type=int, default=500_000_000,
                        help="TX center frequency in Hz (must be explicitly configured)")
    parser.add_argument("--attenuation", type=int, default=30,
                        help="TX attenuation in dB (must be explicitly configured)")
    parser.add_argument("--amplitude-scale", type=float, default=0.1,
                        help="TX amplitude scale factor")
    parser.add_argument("--enable-rf", action="store_true",
                        help="Enable RF transmission (default: disabled for safety)")
    parser.add_argument("--test-mode", action="store_true",
                        help="Run in test mode (no actual hardware transmission)")

    args = parser.parse_args()

    # Physical transmission from this CLI is disabled (see below); refuse
    # before the RF flag is ever set.
    if args.enable_rf:
        raise SystemExit(
            "pluto_tx_adapter.py --enable-rf is disabled. Use "
            "scripts/run_hardware_experiment.py --enable-rf --freq <Hz> instead."
        )
    set_rf_enabled(False)

    if not RF_ENABLED:
        print("=" * 60)
        print("  PLUTO TX ADAPTER - SAFETY MODE")
        print("=" * 60)
        print("  RF TRANSMISSION: DISABLED")
        print("  Use --enable-rf to enable transmission.")
        print("  See docs/DEMO_GUIDE.md for safety requirements.")
        print("=" * 60)

        # Generate waveform but do not transmit
        iq, symbols, taps = generate_waveform(
            args.modulation, args.symbols, args.sps, args.beta, args.seed
        )

        # Save waveform
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = f"{args.modulation.lower()}_seed{args.seed}"
        iq_path = output_dir / f"{stem}.cf32"
        metadata_path = output_dir / f"{stem}.json"

        iq.tofile(iq_path)

        metadata = {
            "modulation": args.modulation,
            "symbols": args.symbols,
            "samples": len(iq),
            "samples_per_symbol": args.sps,
            "sample_rate_sps": PlutoTXAdapter().sample_rate,
            "symbol_rate_sps": PlutoTXAdapter().sample_rate / args.sps,
            "sample_rate_note": "PlutoTXAdapter default; not a measured hardware rate",
            "rolloff": args.beta,
            "filter": "root-raised-cosine",
            "filter_taps": len(taps),
            "seed": args.seed,
            "iq_format": "complex64 interleaved float32",
            "average_power": float(np.mean(np.abs(iq) ** 2)),
            "peak_amplitude": float(np.max(np.abs(iq))),
            "iq_file": str(iq_path),
            "rf_transmission_enabled": False,
        }

        metadata_path.write_text(json.dumps(metadata, indent=4))

        print(f"\nWaveform generated (no TX):")
        print(f"  IQ: {iq_path}")
        print(f"  Metadata: {metadata_path}")
        return

    # ---- Hardware mode (RF enabled) ----
    # Disabled: this legacy path transmitted random BPSK (no frame) at a
    # default of 500 MHz with no band check, stopped TX BEFORE the RTL-SDR
    # captured, and reported a heuristic "BER". Physical tests go through
    # scripts/run_hardware_experiment.py (band check, readback, concurrent
    # capture, real receiver). The code below is kept for reference only.
    raise SystemExit(
        "pluto_tx_adapter.py --enable-rf is disabled. Use "
        "scripts/run_hardware_experiment.py --enable-rf --freq <Hz> instead."
    )
    print("=" * 60)  # noqa: unreachable (kept for reference)
    print("  PLUTO TX ADAPTER - RADIO MODE")
    print("=" * 60)
    print(f"  Modulation    : {args.modulation}")
    print(f"  Symbols       : {args.symbols}")
    print(f"  Sample rate   : 2400000 SPS")
    print(f"  Center freq   : {args.frequency / 1e6:.3f} MHz")
    print(f"  Attenuation   : {args.attenuation} dB")
    print(f"  RF enabled    : YES (operator-confirmed)")
    print("=" * 60)

    # Generate waveform
    iq, symbols, taps = generate_waveform(
        args.modulation, args.symbols, args.sps, args.beta, args.seed
    )

    # Prepare for TX (exactly one amplitude scale)
    prepared = (iq * args.amplitude_scale).astype(np.complex64)
    peak = float(np.max(np.abs(prepared)))
    if peak > 0.25:
        raise ValueError(f"Peak {peak:.4f} exceeds limit 0.25")

    # Configure Pluto adapter
    adapter = PlutoTXAdapter()
    adapter.configure(args.frequency, args.attenuation)
    adapter.prepare(prepared)

    # Transmit
    print("\nTransmitting...")
    result = adapter.transmit()

    print(f"\n===== TX COMPLETE =====")
    print(f"  Samples       : {result['samples']}")
    print(f"  Frequency     : {result['frequency_hz'] / 1e6:.3f} MHz")
    print(f"  Attenuation   : {result['attenuation_db']} dB")
    print(f"  Timestamp     : {result['timestamp']}")

    # Verify with RTL-SDR receiver
    print("\nVerifying with RTL-SDR...")
    receiver = RTLSDRReceiver(
        center_frequencies=[args.frequency],
        sample_rate=256_000,
        capture_samples=2048,
    )
    measurement = receiver.measure(args.frequency)

    print(f"\n===== RTL-SDR VERIFICATION =====")
    print(f"  Detected      : {measurement['detected']}")
    print(f"  SNR           : {measurement['snr_db']:.2f} dB")
    print(f"  BER (est.)    : {measurement['ber']:.4f}")
    print(f"  PDR           : {measurement['pdr']:.2f}")

    # Save measurement
    results_dir = Path("results/hardware/pluto_tx")
    results_dir.mkdir(parents=True, exist_ok=True)
    result_file = results_dir / f"pluto_tx_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result_file.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "modulation": args.modulation,
        "samples": args.symbols,
        "frequency_hz": args.frequency,
        "attenuation_db": args.attenuation,
        "rf_enabled": True,
        "detection": measurement,
    }, indent=4))

    print(f"  Results saved : {result_file}")

    if not measurement["detected"]:
        print("  WARNING: Signal not detected on RTL-SDR. This may be due to:")
        print("  - Insufficient attenuation (signal is too weak)")
        print("  - Frequency mismatch")
        print("  - RF path not connected")
        print("  - Regulatory/operational restrictions")


if __name__ == "__main__":
    main()
