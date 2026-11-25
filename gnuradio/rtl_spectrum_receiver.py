#!/usr/bin/env python3

import argparse
import signal
import time
from pathlib import Path

from gnuradio import gr, blocks
import osmosdr


class RTLPowerCapture(gr.top_block):
    def __init__(self, frequency, sample_rate, gain, ppm, window, output):
        super().__init__("RTL-SDR Power Measurement")

        self.source = osmosdr.source(args="numchan=1")
        self.source.set_sample_rate(sample_rate)
        self.source.set_center_freq(frequency, 0)
        self.source.set_freq_corr(ppm, 0)
        self.source.set_gain_mode(False, 0)
        self.source.set_gain(gain, 0)
        self.source.set_bandwidth(0, 0)

        self.power = blocks.complex_to_mag_squared(1)
        self.average = blocks.moving_average_ff(
            window, 1.0 / window, 4000
        )
        self.decimator = blocks.keep_one_in_n(
            gr.sizeof_float, window
        )
        self.to_dbfs = blocks.nlog10_ff(10.0, 1, 0.0)
        self.sink = blocks.file_sink(
            gr.sizeof_float, str(output), False
        )

        self.connect(
            self.source,
            self.power,
            self.average,
            self.decimator,
            self.to_dbfs,
            self.sink
        )


def main():
    parser = argparse.ArgumentParser(
        description="RTL-SDR smoothed power measurement"
    )

    parser.add_argument("--frequency", type=float, required=True,
                        help="Center frequency in Hz")
    parser.add_argument("--sample-rate", type=float, default=2.4e6)
    parser.add_argument("--gain", type=float, default=20.0)
    parser.add_argument("--ppm", type=float, default=0.0)
    parser.add_argument("--window", type=int, default=24000)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument(
        "--output", type=Path,
        default=Path("results/rtl_power_dbfs.f32")
    )

    args = parser.parse_args()

    if min(args.sample_rate, args.window, args.duration) <= 0:
        parser.error("Sample rate, window and duration must be positive")

    if args.window > args.sample_rate:
        parser.error("Window cannot exceed sample rate")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.output.exists():
        args.output.unlink()

    print("RTL-SDR Power Capture")
    print(f"Frequency:      {args.frequency / 1e6:.6f} MHz")
    print(f"Sample rate:    {args.sample_rate / 1e6:.3f} MS/s")
    print(f"Manual gain:    {args.gain:.1f} dB")
    print(f"Measurement rate: {args.sample_rate / args.window:.1f} Hz")
    print(f"Duration:       {args.duration:.1f} seconds")
    print(f"Output:         {args.output}")

    tb = RTLPowerCapture(
        args.frequency,
        args.sample_rate,
        args.gain,
        args.ppm,
        args.window,
        args.output
    )

    stopping = False

    def stop_handler(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    try:
        tb.start()
        start = time.monotonic()

        while not stopping and time.monotonic() - start < args.duration:
            time.sleep(0.1)

    finally:
        tb.stop()
        tb.wait()

    count = args.output.stat().st_size // 4

    print(f"Measurements written: {count}")
    print(f"Output size: {args.output.stat().st_size} bytes")

    if count == 0:
        print("WARNING: No measurements written.")


if __name__ == "__main__":
    main()
