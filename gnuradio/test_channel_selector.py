#!/usr/bin/python3

from gnuradio import gr, blocks
import numpy as np


class ChannelSelectorTest(gr.top_block):
    def __init__(self, selected_channel):
        super().__init__("Bounded Channel Selector Test")

        sample_count = 4096

        # Three distinguishable constant complex signals.
        signals = [
            np.full(sample_count, 1+0j, dtype=np.complex64),
            np.full(sample_count, 2+0j, dtype=np.complex64),
            np.full(sample_count, 3+0j, dtype=np.complex64),
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

        self.head = blocks.head(
            gr.sizeof_gr_complex,
            sample_count
        )

        self.sink = blocks.vector_sink_c()

        for index, source in enumerate(self.sources):
            self.connect(source, (self.selector, index))

        self.connect(self.selector, self.head, self.sink)


def main():
    for channel in range(3):
        tb = ChannelSelectorTest(channel)
        tb.run()

        samples = np.asarray(tb.sink.data())
        print(
            f"Channel {channel}: "
            f"samples={len(samples)}, "
            f"mean={np.mean(samples).real:.2f}"
        )

        assert len(samples) == 4096
        assert np.allclose(samples, channel + 1)

    print("\nAll three channel selections passed.")


if __name__ == "__main__":
    main()
