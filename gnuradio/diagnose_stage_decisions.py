#!/usr/bin/python3

from src.gnuradio_adapter import GNUradioAdapter

stages = {
    "A": [9.03, 16.99, 6.11],
    "B": [16.99, 6.11, 9.03],
    "C": [-4.59, -5.29, -3.84],
    "D": [9.03, 16.99, 6.11],
}

for name, snrs in stages.items():
    adapter = GNUradioAdapter()
    command = adapter.process(snrs)

    marker = command.channel * 100 + command.modulation_index + 1

    print(
        f"Stage {name}: "
        f"SNR={snrs}, "
        f"channel={command.channel}, "
        f"modulation={command.modulation}, "
        f"enabled={command.enabled}, "
        f"expected marker={marker}"
    )
