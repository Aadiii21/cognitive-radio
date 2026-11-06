#!/usr/bin/python3

import numpy as np
from collections import Counter

from gnuradio import gr, blocks
from src.gnuradio_joint_controller import JointCognitiveController


class MeasuredSNRControlTest(gr.top_block):

    def __init__(self):
        super().__init__("Measured SNR Cognitive Radio Integration")

        self.stage_samples = 40000
        self.alpha = 0.001
        self.rng = np.random.default_rng(2026)

        self.stages = [
            [0.25, 0.10, 0.35],
            [0.10, 0.35, 0.25],
            [1.20, 1.30, 1.10],
            [0.25, 0.10, 0.35],
        ]

        self.total_samples = self.stage_samples * len(self.stages)

        self.controller = JointCognitiveController()

        self.estimator_sinks = []
        self.modulation_selectors = []

        # Four finite stages of independently generated channel noise.
        pilot = np.cos(
            2 * np.pi * 1000 *
            np.arange(self.total_samples) / 100000
        ).astype(np.float32)

        for channel in range(3):

            noise_parts = []

            for stage in self.stages:
                sigma = stage[channel]

                noise = self.rng.normal(
                    0.0, sigma, self.stage_samples
                ).astype(np.float32)

                noise_parts.append(noise)

            noise = np.concatenate(noise_parts)

            received = (pilot + noise).astype(np.float32)
            inverted_pilot = (-pilot).astype(np.float32)

            received_source = blocks.vector_source_f(
                received.tolist(), False
            )

            inverted_source = blocks.vector_source_f(
                inverted_pilot.tolist(), False
            )

            pilot_source = blocks.vector_source_f(
                pilot.tolist(), False
            )

            # Pilot cancellation: (pilot + noise) - pilot = noise
            subtract_pilot = blocks.add_ff(1)

            pilot_rms = blocks.rms_ff(self.alpha)
            noise_rms = blocks.rms_ff(self.alpha)

            ratio = blocks.divide_ff(1)
            snr_db = blocks.nlog10_ff(20, 1, 0)

            snr_sink = blocks.vector_sink_f()

            self.connect(received_source, (subtract_pilot, 0))
            self.connect(inverted_source, (subtract_pilot, 1))

            self.connect(pilot_source, pilot_rms)
            self.connect(subtract_pilot, noise_rms)

            self.connect(pilot_rms, (ratio, 0))
            self.connect(noise_rms, (ratio, 1))
            self.connect(ratio, snr_db)

            # Critical: estimated SNR goes directly to controller.
            self.connect(snr_db, (self.controller, channel))
            self.connect(snr_db, snr_sink)

            self.estimator_sinks.append(snr_sink)

        # Three channels, each with three modulation branches.
        self.signal_sources = []

        for channel in range(3):

            modulation_selector = blocks.selector(
                gr.sizeof_gr_complex, 0, 0
            )

            self.modulation_selectors.append(modulation_selector)

            for modulation in range(3):

                marker = complex(channel * 100 + modulation + 1, 0)

                source = blocks.vector_source_c(
                    [marker] * self.total_samples, False
                )

                self.signal_sources.append(source)

                self.connect(
                    source,
                    (modulation_selector, modulation)
                )

            self.msg_connect(
                (self.controller, "modulation"),
                (modulation_selector, "iindex")
            )

        # Final channel selector.
        self.channel_selector = blocks.selector(
            gr.sizeof_gr_complex, 0, 0
        )

        for channel, selector in enumerate(self.modulation_selectors):
            self.connect(
                selector,
                (self.channel_selector, channel)
            )

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


def main():

    tb = MeasuredSNRControlTest()

    print("Running measured-SNR controller integration...\n")

    tb.run()

    print("===== ESTIMATED SNR BY STAGE =====")

    for channel, sink in enumerate(tb.estimator_sinks):

        values = np.asarray(sink.data())

        for stage_index, noise_levels in enumerate(tb.stages):

            start = stage_index * tb.stage_samples
            end = start + tb.stage_samples

            # Ignore the first half of each stage for RMS settling.
            segment = values[
                start + tb.stage_samples // 2:end
            ]

            measured = float(np.mean(segment))

            sigma = noise_levels[channel]
            expected = 20 * np.log10(
                (1 / np.sqrt(2)) / sigma
            )

            print(
                f"Channel {channel}, Stage {stage_index + 1}: "
                f"expected={expected:.2f} dB, "
                f"measured={measured:.2f} dB"
            )

            assert abs(measured - expected) < 1.0, (
                f"SNR validation failed: channel {channel}, "
                f"stage {stage_index + 1}"
            )

    print("\n===== FINAL CONTROLLER STATE =====")

    controller = tb.controller

    print(
        "Channel:",
        controller.adapter.controller.current_channel
    )
    print(
        "Modulation:",
        controller.adapter.controller.current_modulation
    )
    print("Enabled:", controller.current_enabled)

    print("\n===== MESSAGE COUNTS =====")

    for name, debug in tb.debug.items():
        print(f"{name}: {debug.num_messages()}")

    output = np.asarray(tb.output_sink.data())

    print("\n===== OUTPUT =====")
    print("Output samples:", len(output))

    counts = Counter(round(value.real, 2) for value in output)

    print("Observed markers:", sorted(counts))
    print("Marker counts:")

    for marker, count in sorted(counts.items()):
        print(f"  {marker}: {count}")

    assert controller.adapter.controller.current_channel == 1
    assert controller.adapter.controller.current_modulation == "16-QAM"
    assert bool(controller.current_enabled) is True

    assert tb.debug["channel"].num_messages() >= 2
    assert tb.debug["modulation"].num_messages() >= 2
    assert tb.debug["enable"].num_messages() >= 2

    print("\nMEASURED-SNR CONTROL INTEGRATION PASSED")


if __name__ == "__main__":
    main()
