#!/usr/bin/python3

import sys
from pathlib import Path

import numpy as np
from gnuradio import gr, blocks

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.gnuradio_adapter import GNUradioAdapter


class ChannelIntegrationTest(gr.top_block):
    def __init__(self, selected_channel):
        super().__init__("Controller Channel Integration")

        count = 4096

        signals = [
            np.full(count, complex(i + 1, 0), dtype=np.complex64)
            for i in range(3)
        ]

        self.sources = [
            blocks.vector_source_c(signal.tolist(), False)
            for signal in signals
        ]

        self.selector = blocks.selector(
            gr.sizeof_gr_complex,
            selected_channel,
            0
        )

        self.head = blocks.head(gr.sizeof_gr_complex, count)
        self.sink = blocks.vector_sink_c()

        for index, source in enumerate(self.sources):
            self.connect(source, (self.selector, index))

        self.connect(self.selector, self.head, self.sink)


def main():
    scenarios = [
        ([3.0, 18.0, 8.0], 1),
        ([23.0, 11.0, 3.0], 0),
    ]

    for snrs, expected_channel in scenarios:
        adapter = GNUradioAdapter()
        command = adapter.process(snrs)

        print(
            f"\nInput SNRs: {snrs}"
            f"\nController: channel={command.channel}, "
            f"modulation={command.modulation}, "
            f"action={command.action}"
        )

        assert command.channel == expected_channel, (
            f"Controller selected {command.channel}, "
            f"expected {expected_channel}"
        )

        tb = ChannelIntegrationTest(command.channel)
        tb.run()

        samples = np.asarray(tb.sink.data())
        measured = np.mean(samples).real

        print(
            f"Selector output: {len(samples)} samples, "
            f"mean={measured:.2f}"
        )

        assert len(samples) == 4096
        assert np.allclose(samples, expected_channel + 1)

    print("\nController-to-channel-Selector integration passed.")


if __name__ == "__main__":
    main()
