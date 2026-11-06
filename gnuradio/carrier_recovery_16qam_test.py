#!/usr/bin/python3

from gnuradio import gr, blocks, digital, filter, channels
from gnuradio.filter import firdes
import numpy as np


def run_test(seed):
    rng = np.random.default_rng(42)
    payload = rng.integers(0, 256, 1000, dtype=np.uint8)

    sps = 4
    nfilts = 32
    rolloff = 0.35

    noise = 0.045
    phase_offset = 0.25
    frequency_offset = 0.020

    constellation = digital.constellation_16qam().base()
    points = np.asarray(constellation.points(), dtype=np.complex64)

    bits = np.unpackbits(payload, bitorder="big")
    tx_indices = (
        bits.reshape(-1, 4) @ np.array([8, 4, 2, 1])
    ).astype(np.uint8)

    tx_symbols = points[tx_indices]

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

    tb = gr.top_block("16-QAM automatic phase estimation")

    source = blocks.vector_source_b(tx_indices.tolist(), False)
    mapper = digital.chunks_to_symbols_bc(points.tolist())
    tx_filter = filter.interp_fir_filter_ccf(sps, tx_taps)

    channel = channels.channel_model(
        noise_voltage=noise,
        frequency_offset=0.0,
        epsilon=1.0,
        taps=[1.0 + 0j],
        noise_seed=seed,
        block_tags=False
    )

    delay = blocks.delay(gr.sizeof_gr_complex, 3)

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
    costas = digital.costas_loop_cc(0.02, 4, False)

    rx_sink = blocks.vector_sink_c()

    tb.connect(source, mapper)
    tb.connect(mapper, tx_filter)
    tb.connect(tx_filter, channel)
    tb.connect(channel, delay)
    tb.connect(delay, timing)
    tb.connect(timing, normalize)
    tb.connect(normalize, phase)
    tb.connect(phase, frequency)
    tb.connect(frequency, costas)
    tb.connect(costas, rx_sink)

    tb.run()

    rx = np.asarray(rx_sink.data(), dtype=np.complex64)

    n = min(len(tx_symbols), len(rx))
    tx = tx_symbols[:n]
    rx = rx[:n]

    # Known training region after acquisition.
    training_start = 300
    training_end = 500

    if n <= training_end:
        raise RuntimeError("Insufficient received symbols")

    training_tx = tx[training_start:training_end]
    training_rx = rx[training_start:training_end]

    # Estimate complex channel gain and residual phase.
    correlation = np.sum(
        training_rx * np.conj(training_tx)
    )

    estimated_phase = np.angle(correlation)
    estimated_gain = abs(correlation) / np.sum(
        np.abs(training_tx) ** 2
    )

    correction = np.exp(-1j * estimated_phase)

    # Evaluate only payload symbols after the training region.
    payload_tx = tx[training_end:]
    payload_rx = rx[training_end:] * correction

    distances = np.abs(
        payload_rx[:, None] - points[None, :]
    )

    decoded = np.argmin(
        distances, axis=1
    ).astype(np.uint8)

    tx_payload_indices = tx_indices[training_end:]

    symbol_errors = np.count_nonzero(
        decoded != tx_payload_indices[:len(decoded)]
    )

    tx_bits = np.unpackbits(
        tx_payload_indices[:len(decoded)]
    )

    rx_bits = np.unpackbits(decoded)

    bit_errors = np.count_nonzero(tx_bits != rx_bits)

    ser = symbol_errors / len(decoded)
    ber = bit_errors / len(tx_bits)

    print(f"\nSeed: {seed}")
    print(f"Received symbols: {n}")
    print(f"Training region: {training_start}:{training_end}")
    print(f"Estimated phase: {estimated_phase:.5f} rad")
    print(f"Estimated phase: {np.rad2deg(estimated_phase):.2f} degrees")
    print(f"Estimated gain: {estimated_gain:.5f}")
    print(f"Applied correction: {np.rad2deg(-estimated_phase):.2f} degrees")
    print(f"Payload symbols evaluated: {len(decoded)}")
    print(f"Symbol errors: {symbol_errors}")
    print(f"Bit errors: {bit_errors}")
    print(f"SER: {ser:.6f}")
    print(f"BER: {ber:.6f}")


def main():
    print("16-QAM automatic quadrant/phase estimation")
    print("Noise: 0.045")
    print("Costas bandwidth: 0.02")
    print("Training symbols: 300-499")

    for seed in [42, 44]:
        run_test(seed)


if __name__ == "__main__":
    main()
