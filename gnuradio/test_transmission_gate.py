#!/usr/bin/python3

import time

from gnuradio import gr, blocks
from src.gnuradio_joint_controller import JointCognitiveController


class TransmissionGateTest(gr.top_block):

    def __init__(self):
        super().__init__("Transmission Gate Validation")

        self.controller = JointCognitiveController()

        self.modulation_selectors = []
        self.sources = []
        self.throttles = []

        for channel in range(3):
            selector = blocks.selector(
                gr.sizeof_gr_complex, 0, 0
            )
            self.modulation_selectors.append(selector)

            for modulation in range(3):
                value = complex(channel * 100 + modulation + 1, 0)

                source = blocks.vector_source_c(
                    [value] * 30000, False
                )

                throttle = blocks.throttle(
                    gr.sizeof_gr_complex, 1000, True, 100
                )

                self.sources.append(source)
                self.throttles.append(throttle)

                self.connect(source, throttle)
                self.connect(throttle, (selector, modulation))

            self.msg_connect(
                (self.controller, "modulation"),
                (selector, "iindex")
            )

        self.channel_selector = blocks.selector(
            gr.sizeof_gr_complex, 0, 0
        )

        for channel, selector in enumerate(self.modulation_selectors):
            self.connect(selector, (self.channel_selector, channel))

        self.msg_connect(
            (self.controller, "channel"),
            (self.channel_selector, "iindex")
        )

        self.msg_connect(
            (self.controller, "enable"),
            (self.channel_selector, "en")
        )

        self.output_throttle = blocks.throttle(
            gr.sizeof_gr_complex, 1000, True, 100
        )

        self.probe = blocks.probe_signal_c()

        self.connect(self.channel_selector, self.output_throttle)
        self.connect(self.output_throttle, self.probe)

        # Three 5-second stages: good, poor, recovery.
        stages = [
            [23.0, 11.0, 3.0],
            [-3.0, -2.0, -4.0],
            [23.0, 11.0, 3.0],
        ]

        self.snr_sources = []
        self.snr_throttles = []

        for channel in range(3):
            values = []

            for stage in stages:
                values.extend([stage[channel]] * 100)

            source = blocks.vector_source_f(values, False)

            throttle = blocks.throttle(
                gr.sizeof_float, 20, True, 10
            )

            self.snr_sources.append(source)
            self.snr_throttles.append(throttle)

            self.connect(source, throttle)
            self.connect(throttle, (self.controller, channel))


def wait_for_state(controller, enabled, timeout=8.0):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if controller.current_enabled is not None:
            if bool(controller.current_enabled) == enabled:
                return True

        time.sleep(0.02)

    return False


def wait_for_samples(probe, target, timeout=3.0):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if probe.nitems_read(0) >= target:
            return True
        time.sleep(0.01)

    return False


def main():
    tb = TransmissionGateTest()

    print("Starting transmission-gating validation...\n")

    tb.start()

    try:
        # Stage 1: good conditions.
        if not wait_for_state(tb.controller, True):
            raise RuntimeError("Initial transmission did not enable.")

        if not wait_for_samples(tb.probe, 300):
            raise RuntimeError("No initial output samples received.")

        initial_count = tb.probe.nitems_read(0)
        print(f"GOOD LINK: enabled, samples={initial_count}")

        # Stage 2: poor conditions.
        if not wait_for_state(tb.controller, False):
            raise RuntimeError("Controller did not disable transmission.")

        disabled_count = tb.probe.nitems_read(0)
        time.sleep(0.5)
        disabled_count_after = tb.probe.nitems_read(0)

        print(
            f"POOR LINK: disabled, "
            f"samples before={disabled_count}, "
            f"after={disabled_count_after}"
        )

        if disabled_count_after != disabled_count:
            raise RuntimeError(
                "Transmission continued while disabled."
            )

        # Stage 3: recovery.
        if not wait_for_state(tb.controller, True):
            raise RuntimeError("Transmission did not recover.")

        if not wait_for_samples(
            tb.probe, disabled_count_after + 300
        ):
            raise RuntimeError("Output did not resume after recovery.")

        recovered_count = tb.probe.nitems_read(0)

        print(f"RECOVERY: enabled, samples={recovered_count}")

    finally:
        tb.stop()
        tb.wait()

    print("\nTRANSMISSION GATING TEST PASSED")


if __name__ == "__main__":
    main()
