#!/usr/bin/python3

import csv
import numpy as np

from gnuradio import gr, blocks, digital, filter, channels
from gnuradio.filter import firdes

import packet_receiver_general as receiver


NOISE_LEVELS = np.round(
    np.arange(0.020, 0.1001, 0.005), 3
)

SEEDS = range(40, 70)

MODULATIONS = {
    "BPSK": digital.constellation_bpsk,
    "QPSK": digital.constellation_qpsk,
    "16-QAM": digital.constellation_16qam,
}


def normalized_constellation(factory):
    original = factory().base()

    original_points = np.asarray(
        original.points(), dtype=np.complex128
    )

    power = np.mean(np.abs(original_points) ** 2)
    points = original_points / np.sqrt(power)

    constellation = digital.constellation_calcdist(
        points.tolist(),
        original.pre_diff_code(),
        original.rotational_symmetry(),
        original.dimensionality(),
        digital.constellation_calcdist.NO_NORMALIZATION
    ).base()

    return constellation, np.asarray(
        constellation.points(), dtype=np.complex64
    )


def measure(factory, noise_voltage, seed):

    _, points = normalized_constellation(factory)

    packet, *_ = receiver.build_packet(points)

    tb = gr.top_block("Channel SNR calibration")

    source = blocks.vector_source_b(packet.tolist(), False)
    mapper = digital.chunks_to_symbols_bc(points.tolist())

    sps = 4
    taps = firdes.root_raised_cosine(
        1.0, sps, 1.0, 0.35, 44
    )

    tx_filter = filter.interp_fir_filter_ccf(sps, taps)

    noisy = channels.channel_model(
        noise_voltage=float(noise_voltage),
        frequency_offset=0.0,
        epsilon=1.0,
        taps=[1.0 + 0j],
        noise_seed=int(seed),
        block_tags=False
    )

    clean = channels.channel_model(
        noise_voltage=0.0,
        frequency_offset=0.0,
        epsilon=1.0,
        taps=[1.0 + 0j],
        noise_seed=int(seed),
        block_tags=False
    )

    subtract = blocks.sub_cc()
    signal_sink = blocks.vector_sink_c()
    noise_sink = blocks.vector_sink_c()

    tb.connect(source, mapper)
    tb.connect(mapper, tx_filter)

    tb.connect(tx_filter, clean)
    tb.connect(tx_filter, noisy)

    tb.connect(clean, signal_sink)
    tb.connect(noisy, (subtract, 0))
    tb.connect(clean, (subtract, 1))
    tb.connect(subtract, noise_sink)

    tb.run()

    signal = np.asarray(signal_sink.data(), dtype=np.complex128)
    noise = np.asarray(noise_sink.data(), dtype=np.complex128)

    length = min(len(signal), len(noise))
    signal = signal[:length]
    noise = noise[:length]

    start = min(200, length // 10)
    end = length - start

    signal = signal[start:end]
    noise = noise[start:end]

    signal_power = float(np.mean(np.abs(signal) ** 2))
    noise_power = float(np.mean(np.abs(noise) ** 2))

    snr_db = 10.0 * np.log10(
        signal_power / max(noise_power, 1e-15)
    )

    return signal_power, noise_power, snr_db


def main():

    output = "results/channel_snr_calibration.csv"

    rows = []

    total = len(MODULATIONS) * len(NOISE_LEVELS) * len(SEEDS)
    completed = 0

    for name, factory in MODULATIONS.items():

        print(f"\nCalibrating {name}", flush=True)

        for noise in NOISE_LEVELS:

            for seed in SEEDS:

                signal_power, noise_power, snr_db = measure(
                    factory, noise, seed
                )

                rows.append({
                    "modulation": name,
                    "noise_voltage": float(noise),
                    "seed": seed,
                    "signal_power": signal_power,
                    "noise_power": noise_power,
                    "snr_db": snr_db,
                })

                completed += 1

                if completed % 30 == 0:
                    print(
                        f"Progress: {completed}/{total}",
                        flush=True
                    )

    with open(output, "w", newline="") as f:

        writer = csv.DictWriter(
            f, fieldnames=rows[0].keys()
        )

        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {completed} measurements to {output}")

    print("\nAVERAGE SNR BY NOISE VOLTAGE")

    for name in MODULATIONS:

        print(f"\n{name}")

        for noise in NOISE_LEVELS:

            values = [
                r["snr_db"] for r in rows
                if r["modulation"] == name
                and r["noise_voltage"] == float(noise)
            ]

            print(
                f"Noise={noise:.3f} | "
                f"SNR={np.mean(values):.3f} dB | "
                f"SD={np.std(values):.3f}"
            )


if __name__ == "__main__":
    main()
