#!/usr/bin/env python3
"""
ADALM-Pluto transmitter in pure Python (pyadi-iio), no GNU Radio.

Owner decision (2026-11-23): GNU Radio is used for synthetic data only;
Python controls the hardware. This class replaces the gr-iio sink in the
hardware runner. The GNU Radio adapter (pluto_tx_adapter.PlutoTXAdapter)
is kept unchanged for reference and its own tests.

Reference pattern: Analog Devices' pyadi-iio documentation (cyclic buffers:
`tx_cyclic_buffer = True`, `tx(iq)`; a cyclic buffer must be removed with
`tx_destroy_buffer()` before new data is pushed) and the PySDR PlutoSDR
chapter.

Interface: same as PlutoTXAdapter where the runner uses it:
    __init__(uri, sample_rate, bandwidth, amplitude_scale, cyclic)
    configure(frequency, attenuation)  -> offline, records settings
    prepare(iq, amplitude_scale)       -> offline, scales once, checks peak
    start()                            -> connects, configures, transmits
    stop() / close()                   -> destroys buffer, minimum gain

Hardware is touched only in start(), and only when the module-level RF flag
(pluto_tx_adapter.RF_ENABLED, set by the runner after all safety gates) is
True.

Sample scaling: waveforms are complex floats with full scale 1.0 (the same
convention as GNU Radio's fc32 sink). pyadi-iio writes int16 samples, so the
prepared waveform is multiplied by DAC_FULL_SCALE = 2**15. With the default
amplitude_scale 0.1 the RMS level is -20 dBFS. Peak values are checked against
peak_limit (0.25 of full scale by default) and against the int16 range.

Order of operations in start() (hardware safety):
    1. TX gain to the minimum (-89.75 dB) and any old TX buffer destroyed,
       before changing the sample rate (changing the rate has been reported
       to produce a brief TX output on the Pluto).
    2. sample_rate, tx_rf_bandwidth, tx_lo.
    3. tx_hardwaregain_chan0 = -attenuation (last).
    4. tx_cyclic_buffer = True, tx(samples).
Only cyclic mode is offered: one buffer that the Pluto repeats until
tx_destroy_buffer(), which is the documented pyadi-iio pattern.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np

from src.radio import pluto_tx_adapter
from src.radio.hardware_config import PLUTO_URI, validate_pluto_sample_rate

DAC_FULL_SCALE = 2 ** 15
INT16_MAX = 2 ** 15 - 1
MIN_TX_GAIN_DB = -89.75
MAX_ATTENUATION_DB = 89.75


class PlutoPyadiTX:
    backend = "pyadi-iio"

    def __init__(
        self,
        uri: str = PLUTO_URI,
        sample_rate: int = 2_083_333,
        bandwidth: int = 1_000_000,
        amplitude_scale: float = 0.1,
        peak_limit: float = 0.25,
        cyclic: bool = True,
        sdr_factory=None,
    ):
        if not cyclic:
            raise ValueError("pyadi-iio backend supports cyclic TX only (--tx-mode cyclic).")
        self.uri = uri
        self.sample_rate = validate_pluto_sample_rate(sample_rate)
        self.bandwidth = int(bandwidth)
        if self.bandwidth <= 0:
            raise ValueError("bandwidth must be positive")
        self.amplitude_scale = float(amplitude_scale)
        self.peak_limit = float(peak_limit)
        self.cyclic = True
        self._sdr_factory = sdr_factory
        self._sdr = None
        self._frequency: Optional[int] = None
        self._attenuation: Optional[float] = None
        self._samples: Optional[np.ndarray] = None
        self._closed = False
        self.transmitting = False

    # ------------------------------------------------------------ offline
    def configure(self, frequency: int, attenuation: float = 30):
        attenuation = float(attenuation)
        if not 0 <= attenuation <= MAX_ATTENUATION_DB:
            raise ValueError(f"Attenuation must be between 0 and {MAX_ATTENUATION_DB} dB")
        if int(frequency) <= 0:
            raise ValueError("frequency must be positive")
        self._frequency = int(frequency)
        self._attenuation = attenuation
        return self

    def prepare(self, iq, amplitude_scale: Optional[float] = None):
        iq = np.asarray(iq, dtype=np.complex128)
        if iq.ndim != 1 or len(iq) == 0:
            raise ValueError("iq must be a non-empty 1-D array")
        if not np.all(np.isfinite(iq)):
            raise ValueError("iq contains non-finite samples")
        scale = self.amplitude_scale if amplitude_scale is None else float(amplitude_scale)
        scaled = iq * scale                      # scaled exactly once, full scale 1.0
        peak = float(np.max(np.abs(scaled)))
        if peak > self.peak_limit:
            raise ValueError(f"Peak amplitude {peak:.4f} exceeds limit {self.peak_limit}")
        samples = scaled * DAC_FULL_SCALE
        if max(np.max(np.abs(samples.real)), np.max(np.abs(samples.imag))) > INT16_MAX:
            raise ValueError("Scaled samples exceed the int16 range")
        self._samples = samples
        return self

    # ----------------------------------------------------------- hardware
    def _connect(self):
        if self._sdr_factory is not None:
            return self._sdr_factory(self.uri)
        import adi  # pyadi-iio; imported only when transmitting

        return adi.Pluto(uri=self.uri)

    def start(self) -> dict:
        if not pluto_tx_adapter.RF_ENABLED:
            raise RuntimeError("RF transmission is DISABLED. Use --enable-rf flag to enable.")
        if self._frequency is None or self._attenuation is None:
            raise RuntimeError("Hardware not configured. Call configure() first.")
        if self._samples is None:
            raise RuntimeError("No IQ data prepared. Call prepare() first.")
        if self._closed:
            raise RuntimeError("Transmitter is closed.")

        sdr = self._connect()
        self._sdr = sdr
        # 1. quiet first
        sdr.tx_hardwaregain_chan0 = MIN_TX_GAIN_DB
        try:
            sdr.tx_destroy_buffer()
        except Exception:
            pass  # no buffer yet
        # 2. rates and tuning
        sdr.sample_rate = int(self.sample_rate)
        sdr.tx_rf_bandwidth = int(self.bandwidth)
        sdr.tx_lo = int(self._frequency)
        # 3. requested level last
        sdr.tx_hardwaregain_chan0 = -float(self._attenuation)
        # 4. cyclic transmission
        sdr.tx_cyclic_buffer = True
        sdr.tx(self._samples)
        self.transmitting = True
        return {
            "status": "transmitting",
            "backend": self.backend,
            "samples": int(len(self._samples)),
            "frequency_hz": self._frequency,
            "sample_rate_hz": self.sample_rate,
            "bandwidth_hz": self.bandwidth,
            "attenuation_db": self._attenuation,
            "uri": self.uri,
            "tx_mode": "cyclic",
            "buffer_samples": int(len(self._samples)),
            "dac_full_scale": DAC_FULL_SCALE,
            "timestamp": datetime.now().isoformat(),
        }

    def stop(self) -> dict:
        self.close()
        return {"status": "stopped", "timestamp": datetime.now().isoformat()}

    def close(self):
        sdr, self._sdr = self._sdr, None
        errors = []
        if sdr is not None:
            try:
                sdr.tx_destroy_buffer()
            except Exception as e:  # report after the gain is set to minimum
                errors.append(f"tx_destroy_buffer: {type(e).__name__}: {e}")
            try:
                sdr.tx_hardwaregain_chan0 = MIN_TX_GAIN_DB
            except Exception as e:
                errors.append(f"tx_hardwaregain_chan0: {type(e).__name__}: {e}")
        self.transmitting = False
        self._samples = None
        self._closed = True
        if errors:
            raise RuntimeError("; ".join(errors))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
