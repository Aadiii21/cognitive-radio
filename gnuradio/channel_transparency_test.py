#!/usr/bin/python3

from gnuradio import gr, blocks, channels, filter, digital
from gnuradio.filter import firdes
import numpy as np


def compare_with_alignment(before, after, max_lag=64):
    best = None

    for lag in range(-max_lag, max_lag + 1):

        x_start = max(0, -lag)
        y_start = max(0, lag)

        n = min(
            len(before) - x_start,
            len(after) - y_start
        )

        if n < 100:
            continue

        x = before[x_start:x_start+n]
        y = after[y_start:y_start+n]

        energy_x = np.vdot(x, x).real
        energy_y = np.vdot(y, y).real

        if energy_x <= 1e-12 or energy_y <= 1e-12:
            continue

        correlation = abs(np.vdot(x, y)) / np.sqrt(
            energy_x * energy_y
        )

        if best is None or correlation > best["correlation"]:
            gain = np.vdot(x, y) / energy_x
            residual = y - gain * x

            best = {
                "lag": lag,
                "samples": n,
                "correlation": float(correlation),
                "gain": gain,
                "input_rms": float(np.sqrt(np.mean(np.abs(x)**2))),
                "output_rms": float(np.sqrt(np.mean(np.abs(y)**2))),
                "residual_rms": float(
                    np.sqrt(np.mean(np.abs(residual)**2))
                ),
                "max_difference": float(
                    np.max(np.abs(y - x))
                )
            }

    return best


def run_test(noise_voltage):
    rng = np.random.default_rng(42)

    payload = rng.integers(
        0, 256, 1000, dtype=np.uint8
    )

    bits = np.unpackbits(payload, bitorder="big")

    indices = (
        bits.reshape(-1, 4)
        @ np.array([8, 4, 2, 1])
    ).astype(np.uint8)

    constellation = digital.constellation_16qam().base()
    points = constellation.points()

    sps = 4

    taps = firdes.root_raised_cosine(
        1.0, sps, 1.0, 0.35, 44
    )

    tb = gr.top_block("Channel transparency test")

    source = blocks.vector_source_b(
        indices.tolist(), False
    )

    mapper = digital.chunks_to_symbols_bc(points)

    tx_filter = filter.interp_fir_filter_ccf(
        sps, taps
    )

    channel = channels.channel_model(
        noise_voltage=noise_voltage,
        frequency_offset=0.0,
        epsilon=1.0,
        taps=[1.0 + 0j],
        noise_seed=42,
        block_tags=False
    )

    before_sink = blocks.vector_sink_c()
    after_sink = blocks.vector_sink_c()

    tb.connect(source, mapper)
    tb.connect(mapper, tx_filter)

    tb.connect(tx_filter, before_sink)
    tb.connect(tx_filter, channel)
    tb.connect(channel, after_sink)

    tb.run()

    before = np.asarray(
        before_sink.data(), dtype=np.complex64
    )

    after = np.asarray(
        after_sink.data(), dtype=np.complex64
    )

    result = compare_with_alignment(before, after)

    print(f"\n===== Noise voltage: {noise_voltage} =====")
    print(f"Input samples: {len(before)}")
    print(f"Output samples: {len(after)}")
    print("Best aligned comparison:")
    print(result)


def main():
    run_test(0.0)
    run_test(0.05)


if __name__ == "__main__":
    main()
