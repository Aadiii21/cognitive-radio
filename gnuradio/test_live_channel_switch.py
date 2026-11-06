#!/usr/bin/python3

import time
from gnuradio import gr, blocks


class LiveChannelTest(gr.top_block):
    def __init__(self):
        super().__init__("Live Channel Switching Test")

        self.sources = []
        self.throttles = []

        for channel in range(3):
            source = blocks.vector_source_c(
                [complex(channel + 1, 0)] * 5000,
                False
            )

            throttle = blocks.throttle(
                gr.sizeof_gr_complex,
                1000,
                True,
                100
            )
            throttle.set_max_output_buffer(100)

            self.sources.append(source)
            self.throttles.append(throttle)

        self.selector = blocks.selector(
            gr.sizeof_gr_complex, 0, 0
        )
        self.selector.set_max_output_buffer(100)

        self.probe = blocks.probe_signal_c()

        for i in range(3):
            self.connect(self.sources[i], self.throttles[i])
            self.connect(self.throttles[i], (self.selector, i))

        self.connect(self.selector, self.probe)


def wait_for_samples(probe, target, timeout=3.0):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if probe.nitems_read(0) >= target:
            return True
        time.sleep(0.01)

    return False


def main():
    tb = LiveChannelTest()
    tb.start()

    try:
        results = []

        for channel in range(3):
            before = tb.probe.nitems_read(0)

            tb.selector.set_input_index(channel)

            # Allow enough new samples to pass the bounded buffers.
            if not wait_for_samples(tb.probe, before + 300):
                raise RuntimeError(
                    f"Channel {channel}: sample timeout"
                )

            value = tb.probe.level()
            consumed = tb.probe.nitems_read(0)

            print(
                f"Channel {channel}: "
                f"probe={value}, samples={consumed}"
            )

            expected = channel + 1
            assert abs(value.real - expected) < 0.01, (
                f"Expected {expected}, received {value}"
            )

            results.append(value.real)

    finally:
        tb.stop()
        tb.wait()

    print("\nLive channel switching verified:", results)


if __name__ == "__main__":
    main()
