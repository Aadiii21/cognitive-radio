"""
Verified hardware constants for the Pluto TX / RTL-SDR RX path.

Single source for values that were previously hardcoded (and inconsistent)
across the adapter, sensors, pipeline and experiment runner.
"""

# ADALM-Pluto (Rev.C, AD9363A, fw v0.32, libiio 0.26).
# Verified working URI (USB-network gadget); `iio_info -u ip:192.168.2.1` works.
PLUTO_URI = "ip:192.168.2.1"

# AD9363 baseband rate limits *without* the AD9361 FIR interpolator/decimator.
# sampling_frequency_available on the Pluto reports [2083333 1 61440000].
# Rates below 2083333 need FIR filters, which this project does not configure.
PLUTO_MIN_SAMPLE_RATE = 2_083_333
PLUTO_MAX_SAMPLE_RATE = 61_440_000

# GNU Radio 3.10 gr-iio fmcomms2_sink_fc32 ch_en: one flag per I/Q *rail*.
# The Pluto has a single TX channel (TX1 = I rail + Q rail). GRC's Pluto sink
# template generates [True, True]; FMComms2 (2 TX) uses [tx1, tx1, tx2, tx2].
PLUTO_TX1_CH_EN = [True, True]
# Pluto has one TX channel: set_attenuation() channel index 0 only.
PLUTO_TX_ATTENUATION_CHANNELS = (0,)

# RTL2832U sample rates accepted by librtlsdr (rtlsdr_set_sample_rate).
RTL_SAMPLE_RATE_RANGES = ((225_001, 300_000), (900_001, 3_200_000))
# 2.048 MS/s: verified by rtl_test/rtl_sdr on this RTL2838/R820T, and exactly
# representable by the RTL2832 resampler (no fractional rate error).
RTL_DEFAULT_SAMPLE_RATE = 2_048_000
RTL_XTAL_HZ = 28_800_000  # nominal; ppm correction is not applied (-p 0)


def is_supported_rtl_rate(rate) -> bool:
    r = int(rate)
    return any(lo <= r <= hi for lo, hi in RTL_SAMPLE_RATE_RANGES)


def rtl_exact_sample_rate(requested, xtal_hz=RTL_XTAL_HZ) -> float:
    """Rate the RTL2832 actually produces for a request (librtlsdr formula).

    librtlsdr: rsamp_ratio = (xtal * 2^22 / rate) & 0x0ffffffc;
               real_rate   = xtal * 2^22 / rsamp_ratio
    It prints "Exact sample rate is: ..." only when real_rate != requested.
    """
    if not is_supported_rtl_rate(requested):
        raise ValueError(f"RTL-SDR sample rate {requested} not in {RTL_SAMPLE_RATE_RANGES}")
    ratio = int((xtal_hz * (1 << 22)) / int(requested)) & 0x0FFFFFFC
    return xtal_hz * (1 << 22) / ratio


def validate_pluto_sample_rate(rate) -> int:
    r = int(rate)
    if r != rate and abs(r - rate) > 0.5:
        raise ValueError(f"Pluto sample rate must be an integer number of Hz, got {rate}")
    if not PLUTO_MIN_SAMPLE_RATE <= r <= PLUTO_MAX_SAMPLE_RATE:
        raise ValueError(
            f"Pluto TX sample rate {r} outside {PLUTO_MIN_SAMPLE_RATE}-{PLUTO_MAX_SAMPLE_RATE} S/s "
            f"(rates below {PLUTO_MIN_SAMPLE_RATE} need AD9361 FIR interpolation, not configured)."
        )
    return r
