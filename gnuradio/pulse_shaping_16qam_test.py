
#!/usr/bin/python3

from gnuradio import gr, blocks, digital, filter
from gnuradio.filter import firdes
import numpy as np


def main():
    rng = np.random.default_rng(42)
    payload = rng.integers(0, 256, 1000, dtype=np.uint8)

    sps = 4
    rolloff = 0.35
    num_taps = 81

    constellation = digital.constellation_16qam().base()
    points = np.asarray(
        constellation.points(), dtype=np.complex64
    )

    bits = np.unpackbits(payload, bitorder="big")
    tx_indices = (
        bits.reshape(-1, 4)
        @ np.array([8, 4, 2, 1])
    ).astype(np.uint8)

    tx_symbols = points[tx_indices]

    taps = firdes.root_raised_cosine(
        sps, sps, 1.0, rolloff, num_taps
    )

    tb = gr.top_block("RRC diagnostic")

    source = blocks.vector_source_b(
        tx_indices.tolist(), False
    )
    mapper = digital.chunks_to_symbols_bc(points.tolist())

    tx_filter = filter.interp_fir_filter_ccf(sps, taps)
    rx_filter = filter.fir_filter_ccf(1, taps[::-1])

    sink = blocks.vector_sink_c()

    tb.connect(source, mapper, tx_filter, rx_filter, sink)
    tb.run()

    samples = np.asarray(sink.data(), dtype=np.complex64)

    # Combined group delay: 80 samples.
    delay = num_taps - 1

    print("\n===== RRC SAMPLING PHASE SEARCH =====")

    best = None

    for phase in range(sps):
        start = delay + phase
        rx = samples[start::sps][:len(tx_symbols)]
        n = min(len(rx), len(tx_symbols))

        if n < 100:
            continue

        tx = tx_symbols[:n]
        rx = rx[:n]

        # Least-squares complex gain.
        gain = np.vdot(tx, rx) / np.vdot(tx, tx)
        corrected = rx / gain

        distances = np.abs(
            corrected[:, None] - points[None, :]
        )
        decisions = np.argmin(distances, axis=1)

        ser = np.mean(decisions != tx_indices[:n])

        result = {
            "phase": phase,
            "gain": gain,
            "gain_magnitude": abs(gain),
            "SER": float(ser),
            "symbols": n,
        }

        print(result)

        if best is None or ser < best["SER"]:
            best = result

    print("\n===== BEST RESULT =====")
    print(best)


if __name__ == "__main__":
    main()

