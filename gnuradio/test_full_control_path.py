#!/usr/bin/python3

from gnuradio import gr, blocks
from src.gnuradio_joint_controller import JointCognitiveController


class FullControlPathTest(gr.top_block):

    def __init__(self):
        super().__init__("Full Cognitive Radio Control Test")

        self.controller = JointCognitiveController()

        self.sources = []
        self.modulation_selectors = []

        for channel in range(3):
            selector = blocks.selector(
                gr.sizeof_gr_complex, 0, 0
            )
            self.modulation_selectors.append(selector)

            for modulation in range(3):
                value = complex(channel * 100 + modulation + 1, 0)

                source = blocks.vector_source_c(
                    [value] * 15000, False
                )
                throttle = blocks.throttle(
                    gr.sizeof_gr_complex, 1000, True, 100
                )

                self.sources.append(source)
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

        self.output_sink = blocks.vector_sink_c()
        self.connect(self.channel_selector, self.output_sink)

        self.debug = {
            "channel": blocks.message_debug(),
            "modulation": blocks.message_debug(),
            "enable": blocks.message_debug(),
        }

        for port, block in self.debug.items():
            self.msg_connect(
                (self.controller, port),
                (block, "store")
            )

        scenarios = [
            [3.0, 18.0, 8.0],
            [23.0, 11.0, 3.0],
            [2.0, 3.0, 22.0],
            [-3.0, -2.0, -4.0],
            [23.0, 11.0, 3.0],
        ]

        channel_values = [[], [], []]

        for snrs in scenarios:
            for channel in range(3):
                channel_values[channel].extend(
                    [snrs[channel]] * 20
                )

        self.snr_sources = []

        for channel in range(3):
            source = blocks.vector_source_f(
                channel_values[channel], False
            )
            throttle = blocks.throttle(
                gr.sizeof_float, 20, True, 10
            )

            self.snr_sources.append(source)
            self.connect(source, throttle)
            self.connect(throttle, (self.controller, channel))


def main():
    tb = FullControlPathTest()

    print("Running finite full-control-path test...\n")
    tb.run()

    print("===== CONTROLLER STATE =====")
    print("Channel:", tb.controller.adapter.controller.current_channel)
    print("Modulation:", tb.controller.adapter.controller.current_modulation)
    print("Enabled:", tb.controller.current_enabled)

    print("\n===== MESSAGE COUNTS =====")
    for name, debug in tb.debug.items():
        print(f"{name}: {debug.num_messages()}")

    output = tb.output_sink.data()

    print("\n===== SIGNAL OUTPUT =====")
    print("Output samples:", len(output))

    unique = sorted(set(round(x.real, 2) for x in output))
    print("Observed signal values:", unique)

    assert tb.debug["channel"].num_messages() >= 3
    assert tb.debug["modulation"].num_messages() >= 2
    assert tb.debug["enable"].num_messages() >= 2

    assert 103.0 in unique
    assert 3.0 in unique
    assert 203.0 in unique

    final_channel = tb.controller.adapter.controller.current_channel
    final_modulation = tb.controller.adapter.controller.current_modulation
    final_enabled = tb.controller.current_enabled

    print("\n===== FINAL ASSERTION VALUES =====")
    print("Channel:", repr(final_channel))
    print("Modulation:", repr(final_modulation))
    print("Enabled:", repr(final_enabled))

    assert bool(final_enabled) is True
    assert final_channel == 0
    assert final_modulation == "16-QAM"

    print("\nFULL CONTROL-PATH TEST PASSED")


if __name__ == "__main__":
    main()
