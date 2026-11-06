
#!/usr/bin/python3

from gnuradio import gr, blocks, digital, channels
import numpy as np


def run_test(name, constellation, noise=0.0):
    tb = gr.top_block(f"{name} packet link")

    # Deterministic payload
    rng = np.random.default_rng(42)
    payload = rng.integers(0, 256, 1000, dtype=np.uint8)

    source = blocks.vector_source_b(payload.tolist(), False)

    # Modulator: accepts packed payload bytes directly
    mod = digital.generic_mod(
        constellation=constellation,
        differential=False,
        samples_per_symbol=2,
        pre_diff_code=True,
        excess_bw=0.35,
    )

    # Channel
    channel = channels.channel_model(
        noise_voltage=noise,
        frequency_offset=0.0,
        epsilon=1.0,
        taps=[1.0 + 0j],
        noise_seed=42,
        block_tags=False,
    )

    # Demodulator
    demod = digital.generic_demod(
        constellation=constellation,
        differential=False,
        samples_per_symbol=2,
        pre_diff_code=True,
        excess_bw=0.35,
        log=True,
    )

    # Reconstruct payload bytes from recovered bits
    pack = blocks.repack_bits_bb(1, 8)
    sink = blocks.vector_sink_b()

    # Complete link
    tb.connect(source, mod)
    tb.connect(mod, channel)
    tb.connect(channel, demod)
    tb.connect(demod, pack)
    tb.connect(pack, sink)

    tb.run()

    received = np.array(sink.data(), dtype=np.uint8)

    # Compare bitstreams using LSB-first ordering
    bits_per_symbol = constellation.bits_per_symbol()

    tx_bits = np.unpackbits(payload, bitorder="big")
    rx_bits = np.unpackbits(received, bitorder="little")

    # Reverse recovered bit order within each constellation symbol.
    usable_bits = (len(rx_bits) // bits_per_symbol) * bits_per_symbol
    rx_bits = rx_bits[:usable_bits].reshape(
        -1, bits_per_symbol
    )[:, ::-1].reshape(-1)

    # Find best receiver alignment
    best_errors = None
    best_offset = 0
    best_length = 0

    for offset in range(0, min(200, len(rx_bits)), bits_per_symbol):
        length = min(len(tx_bits), len(rx_bits) - offset)

        if length <= 0:
            continue

        errors = int(np.count_nonzero(
            tx_bits[:length] != rx_bits[offset:offset + length]
        ))

        if best_errors is None or errors < best_errors:
            best_errors = errors
            best_offset = offset
            best_length = length

    return {
        "modulation": name,
        "tx_bytes": len(payload),
        "rx_bytes": len(received),
        "bit_offset": best_offset,
        "compared_bits": best_length,
        "bit_errors": best_errors,
        "bit_error_rate": best_errors / max(1, best_length),
    }


def main():
    modulations = [
        ("BPSK", digital.constellation_bpsk().base()),
        ("QPSK", digital.constellation_qpsk().base()),
        ("16-QAM", digital.constellation_16qam().base()),
    ]

    for name, constellation in modulations:
        print(f"\n===== {name} | Noiseless =====")

        result = run_test(name, constellation, noise=0.0)

        for key, value in result.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()

