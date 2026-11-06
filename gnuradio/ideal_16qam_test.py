
#!/usr/bin/python3

from gnuradio import gr, blocks, digital
import numpy as np


def main():
    # Deterministic payload
    rng = np.random.default_rng(42)
    payload = rng.integers(0, 256, 1000, dtype=np.uint8)

    # 16-QAM constellation
    constellation = digital.constellation_16qam().base()
    points = constellation.points()

    # Expected transmitter symbol indices.
    tx_bits = np.unpackbits(payload, bitorder="big")
    tx_indices = (
        tx_bits.reshape(-1, 4)
        @ np.array([8, 4, 2, 1])
    ).astype(np.uint8)

    # GNU Radio flowgraph
    tb = gr.top_block("Ideal 16-QAM test")

    source = blocks.vector_source_b(
        payload.tolist(), False
    )

    unpack = blocks.packed_to_unpacked_bb(
        4, gr.GR_MSB_FIRST
    )

    mapper = digital.chunks_to_symbols_bc(points)

    decoder = digital.constellation_decoder_cb(
        constellation
    )

    sink = blocks.vector_sink_b()

    # Direct noiseless symbol link
    tb.connect(source, unpack)
    tb.connect(unpack, mapper)
    tb.connect(mapper, decoder)
    tb.connect(decoder, sink)

    tb.run()

    rx_indices = np.asarray(
        sink.data(), dtype=np.uint8
    )

    # Compare transmitter and receiver decisions
    n = min(len(tx_indices), len(rx_indices))

    errors = int(np.count_nonzero(
        tx_indices[:n] != rx_indices[:n]
    ))

    ser = errors / max(1, n)

    print("\n===== IDEAL 16-QAM RESULTS =====")
    print("Transmitted symbols:", len(tx_indices))
    print("Received decisions:", len(rx_indices))
    print("Compared symbols:", n)
    print("Symbol errors:", errors)
    print("Symbol error rate:", ser)

    print("\nFirst 20 transmitted:", tx_indices[:20].tolist())
    print("First 20 received:   ", rx_indices[:20].tolist())


if __name__ == "__main__":
    main()
