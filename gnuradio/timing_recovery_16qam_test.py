
#!/usr/bin/python3

from gnuradio import gr, blocks, digital, filter
from gnuradio.filter import firdes
import numpy as np


def main():
    rng = np.random.default_rng(42)
    payload = rng.integers(0, 256, 1000, dtype=np.uint8)

    sps = 4
    rolloff = 0.35
    nfilts = 32
    filter_symbols = 11

    # 16-QAM constellation
    constellation = digital.constellation_16qam().base()
    points = np.asarray(
        constellation.points(), dtype=np.complex64
    )

    # Transmitted symbol indices
    bits = np.unpackbits(payload, bitorder="big")
    tx_indices = (
        bits.reshape(-1, 4)
        @ np.array([8, 4, 2, 1])
    ).astype(np.uint8)

    tx_symbols = points[tx_indices]

    # Transmitter RRC filter
    tx_taps = firdes.root_raised_cosine(
        1.0,
        sps,
        1.0,
        rolloff,
        filter_symbols * sps
    )

    # PFB matched-filter prototype:
    # Designed at nfilts * sps sampling rate.
    pfb_taps = firdes.root_raised_cosine(
        float(nfilts),
        float(nfilts * sps),
        1.0,
        rolloff,
        filter_symbols * sps * nfilts
    )

    print("PFB arms:", nfilts)
    print("PFB tap count:", len(pfb_taps))

    tb = gr.top_block("Correct PFB timing recovery")

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

    sink = blocks.vector_sink_c()

    tb.connect(source, mapper)
    tb.connect(mapper, tx_filter)
    tb.connect(tx_filter, timing)
    tb.connect(timing, sink)

    tb.run()

    rx = np.asarray(
        sink.data(), dtype=np.complex64
    )

    print("\nRecovered samples:", len(rx))

    # Search alignment and estimate constant complex gain.
    best = None

    for tx_start in range(200):
        for rx_start in range(100):
            n = min(
                len(tx_symbols) - tx_start,
                len(rx) - rx_start
            )

            if n < 1000:
                continue

            tx = tx_symbols[tx_start:tx_start+n]
            received = rx[rx_start:rx_start+n]

            gain = np.vdot(tx, received) / np.vdot(tx, tx)

            if abs(gain) < 1e-8:
                continue

            corrected = received / gain

            distances = np.abs(
                corrected[:, None] - points[None, :]
            )

            decisions = np.argmin(distances, axis=1)

            ser = float(np.mean(
                decisions != tx_indices[tx_start:tx_start+n]
            ))

            if best is None or ser < best["SER"]:
                best = {
                    "tx_offset": tx_start,
                    "rx_offset": rx_start,
                    "symbols": n,
                    "gain": complex(gain),
                    "gain_magnitude": float(abs(gain)),
                    "SER": ser
                }

    print("\n===== PFB TIMING RECOVERY RESULTS =====")
    print("Transmitted symbols:", len(tx_symbols))
    print("Best alignment:", best)


if __name__ == "__main__":
    main()

