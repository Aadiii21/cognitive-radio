#!/usr/bin/python3

import time

from gnuradio import gr, blocks
from src.gnuradio_adapter import GNUradioAdapter


class ControllerLiveTest(gr.top_block):
    def __init__(self):
        super().__init__("Controller Driven Live Channel Switching")

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
    adapter = GNUradioAdapter()
    tb = ControllerLiveTest()

    scenarios = [
        ("Channel 1 strongest", [3.0, 18.0, 8.0]),
        ("Channel 0 strongest", [23.0, 11.0, 3.0]),
        ("Channel 2 strongest", [2.0, 3.0, 22.0]),
        ("All channels poor", [-3.0, -2.0, -4.0]),
    ]

    results = []

    tb.start()

    try:
        for name, snrs in scenarios:
            command = adapter.process(snrs)

            before = tb.probe.nitems_read(0)

            # Apply the controller's channel decision.
            tb.selector.set_input_index(command.channel)

            if not wait_for_samples(tb.probe, before + 300):
                raise RuntimeError(f"{name}: sample timeout")

            output = tb.probe.level()
            expected = command.channel + 1

            assert abs(output.real - expected) < 0.01, (
                f"{name}: expected output {expected}, got {output}"
            )

            print(
                f"{name}: "
                f"SNRs={snrs}, "
                f"channel={command.channel}, "
                f"modulation={command.modulation}, "
                f"enabled={command.enabled}, "
                f"action={command.action}, "
                f"output={output}"
            )

            results.append((command.channel, output.real))

    finally:
        tb.stop()
        tb.wait()

    print("\nController-driven live switching verified:", results)


if __name__ == "__main__":
    main()
