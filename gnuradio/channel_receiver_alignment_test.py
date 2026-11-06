#!/usr/bin/python3

from gnuradio import gr, blocks, digital, filter, channels
from gnuradio.filter import firdes
import numpy as np


def run_test(name, use_channel, restore_delay, phase_offset, frequency_offset):
    rng = np.random.default_rng(42)

    payload = rng.integers(0, 256, 1000, dtype=np.uint8)

    sps = 4
    nfilts = 32
    rolloff = 0.35

    constellation = digital.constellation_16qam().base()
    points = np.asarray(
        constellation.points(), dtype=np.complex64
    )

    bits = np.unpackbits(payload, bitorder="big")

    tx_indices = (
        bits.reshape(-1, 4)
        @ np.array([8, 4, 2, 1])
    ).astype(np.uint8)

    tx_taps = firdes.root_raised_cosine(
        1.0, sps, 1.0, rolloff, 44
    )

    pfb_taps = firdes.root_raised_cosine(
        float(nfilts),
        float(nfilts * sps),
        1.0,
        rolloff,
        44 * nfilts
    )

    tb = gr.top_block(name)

    source = blocks.vector_source_b(
        tx_indices.tolist(), False
    )

    mapper = digital.chunks_to_symbols_bc(
        points.tolist()
    )

    tx_filter = filter.interp_fir_filter_ccf(
        sps, tx_taps
    )

    timing = digital.symbol_sync_cc(
        digital.TED_GARDNER,
        float(sps),
        0.045,
        1.0 / np.sqrt(2.0),
        1.0,
        0.25,
        1,
        constellation,
        digital.IR_PFB_MF,
        nfilts,
        pfb_taps
    )

    normalize = blocks.multiply_const_cc(4.0)

    phase = blocks.multiply_const_cc(
        complex(np.exp(1j * phase_offset))
    )

    frequency = blocks.rotator_cc(frequency_offset)

    costas = digital.costas_loop_cc(
        0.02, 4, False
    )

    decoder = digital.constellation_decoder_cb(
        constellation
    )

    sink = blocks.vector_sink_b()

    tb.connect(source, mapper)
    tb.connect(mapper, tx_filter)

    if use_channel:
        channel = channels.channel_model(
            noise_voltage=0.0,
            frequency_offset=0.0,
            epsilon=1.0,
            taps=[1.0 + 0j],
            noise_seed=42,
            block_tags=False
        )

        tb.connect(tx_filter, channel)

        if restore_delay:
            delay = blocks.delay(
                gr.sizeof_gr_complex, 3
            )
            tb.connect(channel, delay)
            tb.connect(delay, timing)
        else:
            tb.connect(channel, timing)

    else:
        tb.connect(tx_filter, timing)

    tb.connect(timing, normalize)
    tb.connect(normalize, phase)
    tb.connect(phase, frequency)
    tb.connect(frequency, costas)
    tb.connect(costas, decoder)
    tb.connect(decoder, sink)

    tb.run()

    rx_indices = np.asarray(
        sink.data(), dtype=np.uint8
    )

    # Fixed alignment: compare from the beginning.
    fixed_n = min(
        len(tx_indices), len(rx_indices)
    )

    fixed_errors = int(np.count_nonzero(
        tx_indices[:fixed_n] != rx_indices[:fixed_n]
    ))

    fixed_ser = fixed_errors / max(1, fixed_n)

    # Best alignment: diagnostic only.
    best = None

    for tx_start in range(200):
        for rx_start in range(100):

            n = min(
                len(tx_indices) - tx_start,
                len(rx_indices) - rx_start
            )

            if n < 1000:
                continue

            errors = int(np.count_nonzero(
                tx_indices[tx_start:tx_start+n]
                != rx_indices[rx_start:rx_start+n]
            ))

            ser = errors / n

            if best is None or ser < best["SER"]:
                best = {
                    "tx_offset": tx_start,
                    "rx_offset": rx_start,
                    "symbols": n,
                    "errors": errors,
                    "SER": ser
                }

    return {
        "configuration": name,
        "tx_symbols": len(tx_indices),
        "rx_symbols": len(rx_indices),
        "fixed_alignment": {
            "symbols": fixed_n,
            "errors": fixed_errors,
            "SER": fixed_ser
        },
        "best_alignment": best
    }


def main():
    tests = [
        (
            "Direct path",
            False, False, 0.0, 0.0
        ),
        (
            "Channel without correction",
            True, False, 0.0, 0.0
        ),
        (
            "Channel with 3-sample delay",
            True, True, 0.0, 0.0
        ),
        (
            "Channel + delay + phase/frequency",
            True, True, 0.25, 0.020
        )
    ]

    for test in tests:
        print(f"\n===== {test[0]} =====")
        result = run_test(*test)
        print(result)


if __name__ == "__main__":
    main()
