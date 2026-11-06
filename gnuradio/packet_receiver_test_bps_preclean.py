#!/usr/bin/python3

from gnuradio import gr, blocks, digital, filter, channels
from gnuradio.filter import firdes

import numpy as np
import csv
import os


# ==================================================
# FIXED EXPERIMENT CONFIGURATION
# ==================================================

NOISE = 0.045
PHASE_OFFSET = 0.25
FREQUENCY_OFFSET = 0.020
COSTAS_BANDWIDTH = 0.02

TRAINING_LENGTH = 400
SYNC_LENGTH = 64
PAYLOAD_LENGTH = 2000
GUARD_LENGTH = 128

PILOT_LENGTH = 16
DATA_PER_PILOT = 128

SEEDS = list(range(40, 50))

SER_LIMIT = 0.01
BER_LIMIT = 0.005
SYNC_LIMIT = 0.80


# ==================================================
# PACKET GENERATION
# ==================================================

def build_packet(points):

    rng = np.random.default_rng(2026)

    training = rng.integers(
        0, 16, TRAINING_LENGTH, dtype=np.uint8
    )

    sync_word = rng.integers(
        0, 16, SYNC_LENGTH, dtype=np.uint8
    )

    payload = rng.integers(
        0, 16, PAYLOAD_LENGTH, dtype=np.uint8
    )

    pilot_rng = np.random.default_rng(9090)

    pilot = pilot_rng.integers(
        0, 16, PILOT_LENGTH, dtype=np.uint8
    )

    framed_payload = []
    pilot_block_count = 0

    for start in range(0, PAYLOAD_LENGTH, DATA_PER_PILOT):

        end = min(
            start + DATA_PER_PILOT,
            PAYLOAD_LENGTH
        )

        framed_payload.extend(pilot.tolist())
        framed_payload.extend(payload[start:end].tolist())

        pilot_block_count += 1

    guard = np.zeros(
        GUARD_LENGTH, dtype=np.uint8
    )

    packet = np.concatenate([
        training,
        sync_word,
        np.asarray(framed_payload, dtype=np.uint8),
        guard
    ]).astype(np.uint8)

    return (
        packet,
        training,
        sync_word,
        payload,
        pilot,
        pilot_block_count
    )


# ==================================================
# GNU RADIO RECEIVER
# ==================================================

def run_receiver(seed, points, constellation, packet):

    tx_symbols = points[packet]

    sps = 4
    nfilts = 32
    rolloff = 0.35

    tx_taps = firdes.root_raised_cosine(
        1.0,
        sps,
        1.0,
        rolloff,
        44
    )

    pfb_taps = firdes.root_raised_cosine(
        float(nfilts),
        float(nfilts * sps),
        1.0,
        rolloff,
        44 * nfilts
    )

    tb = gr.top_block("Pilot-assisted 16-QAM receiver")

    source = blocks.vector_source_b(
        packet.tolist(), False
    )

    mapper = digital.chunks_to_symbols_bc(
        points.tolist()
    )

    tx_filter = filter.interp_fir_filter_ccf(
        sps, tx_taps
    )

    channel = channels.channel_model(
        noise_voltage=NOISE,
        frequency_offset=0.0,
        epsilon=1.0,
        taps=[1.0 + 0j],
        noise_seed=seed,
        block_tags=False
    )

    delay = blocks.delay(
        gr.sizeof_gr_complex, 3
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
        complex(np.exp(1j * PHASE_OFFSET))
    )

    frequency = blocks.rotator_cc(
        FREQUENCY_OFFSET
    )

    costas = digital.costas_loop_cc(
        COSTAS_BANDWIDTH, 4, False
    )

    sink = blocks.vector_sink_c()

    tb.connect(source, mapper)
    tb.connect(mapper, tx_filter)
    tb.connect(tx_filter, channel)
    tb.connect(channel, delay)
    tb.connect(delay, timing)
    tb.connect(timing, normalize)
    tb.connect(normalize, phase)
    tb.connect(phase, frequency)
    tb.connect(frequency, costas)
    tb.connect(costas, sink)

    tb.run()

    return np.asarray(
        sink.data(), dtype=np.complex64
    )


# ==================================================
# SYNCHRONIZATION DETECTION
# ==================================================

def detect_sync(rx, points, sync_word):

    sync_symbols = points[sync_word]

    correlation = np.correlate(
        rx, sync_symbols, mode="valid"
    )

    window_energy = np.convolve(
        np.abs(rx) ** 2,
        np.ones(len(sync_word)),
        mode="valid"
    )

    reference_energy = np.sum(
        np.abs(sync_symbols) ** 2
    )

    scores = np.abs(correlation) / np.sqrt(
        np.maximum(
            window_energy * reference_energy,
            1e-12
        )
    )

    position = int(np.argmax(scores))
    score = float(scores[position])

    return position, score


# ==================================================
# PILOT-ASSISTED PHASE TRACKING
# ==================================================

def estimate_pilot_gains(
    rx,
    points,
    pilot,
    payload_start,
    payload_length
):
    pilot_symbols = points[pilot]

    pilot_centers = []
    pilot_gains = []
    data_symbols = []
    data_positions = []

    cursor = 0
    data_collected = 0

    denominator = np.sum(np.abs(pilot_symbols) ** 2)

    while data_collected < payload_length:
        pilot_start = payload_start + cursor
        pilot_end = pilot_start + PILOT_LENGTH

        rx_pilot = rx[pilot_start:pilot_end]

        if len(rx_pilot) != PILOT_LENGTH:
            raise RuntimeError(
                f"Incomplete pilot block at offset {cursor}"
            )

        gain = np.sum(
            rx_pilot * np.conj(pilot_symbols)
        ) / denominator

        pilot_centers.append(
            pilot_start + PILOT_LENGTH / 2.0
        )
        pilot_gains.append(gain)

        cursor += PILOT_LENGTH

        data_count = min(
            DATA_PER_PILOT,
            payload_length - data_collected
        )

        data_start = payload_start + cursor
        data_end = data_start + data_count

        rx_data = rx[data_start:data_end]

        if len(rx_data) != data_count:
            raise RuntimeError(
                f"Incomplete data block at offset {cursor}: "
                f"expected {data_count}, received {len(rx_data)}"
            )

        data_symbols.extend(rx_data.tolist())
        data_positions.extend(range(data_start, data_end))

        data_collected += data_count
        cursor += data_count

    return (
        np.asarray(data_symbols, dtype=np.complex64),
        np.asarray(data_positions, dtype=np.float64),
        np.asarray(pilot_centers, dtype=np.float64),
        np.asarray(pilot_gains, dtype=np.complex128)
    )
def correct_payload(
    received,
    positions,
    pilot_centers,
    pilot_gains,
    points
):
    # Stage 1: coarse pilot-based amplitude and phase correction.
    pilot_phase = np.unwrap(np.angle(pilot_gains))
    pilot_amplitude = np.abs(pilot_gains)

    estimated_phase = np.interp(
        positions,
        pilot_centers,
        pilot_phase
    )

    estimated_amplitude = np.interp(
        positions,
        pilot_centers,
        pilot_amplitude
    )

    estimated_amplitude = np.maximum(
        estimated_amplitude, 1e-8
    )

    coarse_correction = (
        estimated_amplitude *
        np.exp(1j * estimated_phase)
    )

    coarse_corrected = received / coarse_correction

    # Stage 2: local blind phase search.
    # This uses the constellation geometry, not transmitted payload data.
    window_size = 16
    step_size = 8

    phase_candidates = np.deg2rad(
        np.arange(-45.0, 46.0, 1.0)
    )

    n = len(coarse_corrected)
    window_starts = list(
        range(0, max(1, n - window_size + 1), step_size)
    )

    final_start = max(0, n - window_size)

    if not window_starts or window_starts[-1] != final_start:
        window_starts.append(final_start)

    phase_centers = []
    residual_phases = []

    for start in window_starts:
        end = min(start + window_size, n)
        window = coarse_corrected[start:end]

        if len(window) < 4:
            continue

        best_phase = 0.0
        best_cost = float("inf")

        for candidate in phase_candidates:
            rotated = window * np.exp(-1j * candidate)

            distances = np.abs(
                rotated[:, None] - points[None, :]
            )

            nearest_distances = np.min(
                distances ** 2,
                axis=1
            )

            cost = float(np.mean(nearest_distances))

            if cost < best_cost:
                best_cost = cost
                best_phase = candidate

        phase_centers.append((start + end - 1) / 2.0)
        residual_phases.append(best_phase)

    if not residual_phases:
        return coarse_corrected, pilot_phase, pilot_amplitude

    residual_phases = np.unwrap(
        np.asarray(residual_phases)
    )

    local_phase = np.interp(
        np.arange(n),
        np.asarray(phase_centers),
        residual_phases
    )

    corrected = coarse_corrected * np.exp(-1j * local_phase)

    return corrected, pilot_phase, pilot_amplitude
def calculate_metrics(decoded, reference):

    symbol_errors = int(
        np.count_nonzero(decoded != reference)
    )

    tx_bits = np.unpackbits(reference)
    rx_bits = np.unpackbits(decoded)

    bit_errors = int(
        np.count_nonzero(tx_bits != rx_bits)
    )

    ser = symbol_errors / len(reference)
    ber = bit_errors / len(tx_bits)

    return ser, ber, symbol_errors, bit_errors


# ==================================================
# COMPLETE PACKET EVALUATION
# ==================================================

def evaluate_seed(
    seed,
    points,
    constellation,
    packet,
    training,
    sync_word,
    payload,
    pilot
):

    rx = run_receiver(
        seed,
        points,
        constellation,
        packet
    )

    sync_position, sync_score = detect_sync(
        rx, points, sync_word
    )

    payload_start = sync_position + SYNC_LENGTH

    (
        rx_payload,
        data_positions,
        pilot_centers,
        pilot_gains
    ) = estimate_pilot_gains(
        rx,
        points,
        pilot,
        payload_start,
        PAYLOAD_LENGTH
    )

    if len(rx_payload) != PAYLOAD_LENGTH:
        raise RuntimeError(
            f"Seed {seed}: incorrect payload length"
        )

    corrected, pilot_phase, pilot_amplitude = correct_payload(
        rx_payload,
        data_positions,
        pilot_centers,
        pilot_gains,
        points
    )

    distances = np.abs(
        corrected[:, None] - points[None, :]
    )

    decoded = np.argmin(
        distances,
        axis=1
    ).astype(np.uint8)

    # Diagnose received constellation alignment before hard decoding.
    if seed == 43:
        print("\\nConstellation alignment by payload block:")

        for block_index in range(16):
            start = block_index * DATA_PER_PILOT
            end = min(start + DATA_PER_PILOT, PAYLOAD_LENGTH)

            expected = points[payload[start:end]]
            observed = corrected[start:end]

            gain = np.sum(
                observed * np.conj(expected)
            ) / np.sum(np.abs(expected) ** 2)

            residual = observed - gain * expected
            residual_rms = np.sqrt(
                np.mean(np.abs(residual) ** 2)
            )

            print(
                f"Block {block_index + 1:02d} | "
                f"Gain phase: {np.rad2deg(np.angle(gain)):+8.3f} deg | "
                f"Gain amplitude: {abs(gain):.5f} | "
                f"Residual RMS: {residual_rms:.5f}"
            )

    if seed == 43:
        print("\\nBlock 4: phase tracking in 16-symbol windows")

        block_start = 3 * DATA_PER_PILOT

        for chunk in range(8):
            start = block_start + chunk * 16
            end = start + 16

            expected = points[payload[start:end]]
            observed = corrected[start:end]

            gain = np.sum(
                observed * np.conj(expected)
            ) / np.sum(np.abs(expected) ** 2)

            residual = observed - gain * expected

            chunk_errors = np.count_nonzero(
                decoded[start:end] != payload[start:end]
            )

            print(
                f"Chunk {chunk + 1} | "
                f"Phase: {np.rad2deg(np.angle(gain)):+8.3f} deg | "
                f"Amplitude: {abs(gain):.5f} | "
                f"Residual RMS: {np.sqrt(np.mean(np.abs(residual)**2)):.5f} | "
                f"Errors: {chunk_errors}/16"
            )

    if seed == 43:
        print("\\nORACLE CORRECTION TEST - BLOCK 4")

        block_start = 3 * DATA_PER_PILOT
        oracle_errors = 0

        for chunk in range(8):
            start = block_start + chunk * 16
            end = start + 16

            expected = points[payload[start:end]]
            observed = corrected[start:end]

            gain = np.sum(
                observed * np.conj(expected)
            ) / np.sum(np.abs(expected) ** 2)

            locally_corrected = observed / gain

            local_decoded = np.argmin(
                np.abs(
                    locally_corrected[:, None] -
                    points[None, :]
                ),
                axis=1
            )

            errors = int(np.count_nonzero(
                local_decoded != payload[start:end]
            ))

            oracle_errors += errors

            print(
                f"Chunk {chunk + 1} | "
                f"Oracle errors: {errors}/16 | "
                f"Estimated phase: "
                f"{np.rad2deg(np.angle(gain)):+.2f} deg"
            )

        print(f"Total oracle errors: {oracle_errors}/128")

    ser, ber, symbol_errors, bit_errors = calculate_metrics(
        decoded, payload
    )

    # Diagnose errors within each pilot interval.
    block_diagnostics = []
    offset = 0

    for block_index in range(len(pilot_gains)):
        block_length = min(
            DATA_PER_PILOT,
            PAYLOAD_LENGTH - offset
        )

        if block_length <= 0:
            break

        block_reference = payload[offset:offset + block_length]
        block_decoded = decoded[offset:offset + block_length]

        block_symbol_errors = int(
            np.count_nonzero(
                block_decoded != block_reference
            )
        )

        block_tx_bits = np.unpackbits(block_reference)
        block_rx_bits = np.unpackbits(block_decoded)

        block_bit_errors = int(
            np.count_nonzero(
                block_tx_bits != block_rx_bits
            )
        )

        block_diagnostics.append({
            "block": block_index + 1,
            "symbol_errors": block_symbol_errors,
            "bit_errors": block_bit_errors,
            "SER": block_symbol_errors / block_length,
            "BER": block_bit_errors / (block_length * 8)
        })

        offset += block_length

    phase_range = np.rad2deg(
        np.max(pilot_phase) - np.min(pilot_phase)
    )

    amplitude_variation = (
        np.std(pilot_amplitude) /
        max(np.mean(pilot_amplitude), 1e-8)
    )

    packet_success = (
        sync_score >= SYNC_LIMIT
        and ser <= SER_LIMIT
        and ber <= BER_LIMIT
    )

    if seed == 43:
        print("\\n--- SEED 43 BLOCK DIAGNOSTICS ---")
        for block in block_diagnostics:
            print(
                f"Block {block['block']:02d} | "
                f"Errors: {block['symbol_errors']:3d} | "
                f"BER: {block['BER']:.6f} | "
                f"SER: {block['SER']:.6f}"
            )

        if seed == 43:
            block_start = 3 * DATA_PER_PILOT
            block_end = min(
                block_start + DATA_PER_PILOT,
                PAYLOAD_LENGTH
            )

            error_positions = np.flatnonzero(
                decoded[block_start:block_end] !=
                payload[block_start:block_end]
            ) + block_start

            print("\\nSeed 43 error positions in block 4:")
            print(error_positions.tolist())

            print("\\nError positions relative to block 4:")
            print(
                (error_positions - block_start).tolist()
            )

        if seed == 43:
            block_start = 3 * DATA_PER_PILOT
            block_end = min(
                block_start + DATA_PER_PILOT,
                PAYLOAD_LENGTH
            )

            error_positions = np.flatnonzero(
                decoded[block_start:block_end] !=
                payload[block_start:block_end]
            ) + block_start

            print("\\nSeed 43 error positions in block 4:")
            print(error_positions.tolist())

            print("\\nError positions relative to block 4:")
            print(
                (error_positions - block_start).tolist()
            )

        print("\\nPilot estimates for seed 43:")
        for i, (phase, amplitude) in enumerate(
            zip(pilot_phase, pilot_amplitude), start=1
        ):
            print(
                f"Pilot {i:02d} | "
                f"Phase: {np.rad2deg(phase):+9.3f} deg | "
                f"Amplitude: {amplitude:.5f}"
            )

        print("--------------------------------")

    return {
        "seed": seed,
        "received_symbols": len(rx),
        "sync_position": sync_position,
        "sync_score": sync_score,
        "pilot_blocks": len(pilot_gains),
        "phase_range_degrees": phase_range,
        "amplitude_variation": amplitude_variation,
        "payload_symbols": len(decoded),
        "symbol_errors": symbol_errors,
        "bit_errors": bit_errors,
        "SER": ser,
        "BER": ber,
        "packet_success": packet_success
    }


def main():

    constellation = digital.constellation_16qam().base()

    points = np.asarray(
        constellation.points(),
        dtype=np.complex64
    )

    (
        packet,
        training,
        sync_word,
        payload,
        pilot,
        pilot_count
    ) = build_packet(points)

    print("=" * 78)
    print("PILOT-ASSISTED 16-QAM PACKET RECEIVER")
    print("=" * 78)

    print(f"Noise voltage:       {NOISE}")
    print(f"Phase offset:        {PHASE_OFFSET}")
    print(f"Frequency offset:    {FREQUENCY_OFFSET}")
    print(f"Costas bandwidth:    {COSTAS_BANDWIDTH}")
    print(f"Training symbols:    {TRAINING_LENGTH}")
    print(f"Sync symbols:        {SYNC_LENGTH}")
    print(f"Payload symbols:     {PAYLOAD_LENGTH}")
    print(f"Pilot symbols/block: {PILOT_LENGTH}")
    print(f"Data symbols/block:  {DATA_PER_PILOT}")
    print(f"Pilot blocks:        {pilot_count}")
    print(f"Noise seeds:         {SEEDS}")

    results = []

    for seed in SEEDS:

        result = evaluate_seed(
            seed,
            points,
            constellation,
            packet,
            training,
            sync_word,
            payload,
            pilot
        )

        results.append(result)

        print(
            f"\nSeed {seed:2d} | "
            f"Sync={result['sync_position']:4d} | "
            f"Score={result['sync_score']:.4f} | "
            f"Phase range={result['phase_range_degrees']:+8.2f}° | "
            f"SER={result['SER']:.6f} | "
            f"BER={result['BER']:.6f} | "
            f"{'PASS' if result['packet_success'] else 'FAIL'}"
        )

    # Aggregate metrics.
    successful = sum(
        r["packet_success"] for r in results
    )

    ser_values = np.array([
        r["SER"] for r in results
    ])

    ber_values = np.array([
        r["BER"] for r in results
    ])

    print("\n" + "=" * 78)
    print("AGGREGATE RESULTS")
    print("=" * 78)

    print(f"Successful packets: {successful}/{len(results)}")
    print(f"Packet success rate: {successful / len(results):.1%}")

    print(f"Mean SER: {np.mean(ser_values):.6f}")
    print(f"Mean BER: {np.mean(ber_values):.6f}")

    print(f"Worst SER: {np.max(ser_values):.6f}")
    print(f"Worst BER: {np.max(ber_values):.6f}")

    print(
        f"SER standard deviation: "
        f"{np.std(ser_values):.6f}"
    )

    print(
        f"BER standard deviation: "
        f"{np.std(ber_values):.6f}"
    )

    # Save CSV.
    os.makedirs("results", exist_ok=True)

    output_file = (
        "results/packet_receiver_pilot_validation.csv"
    )

    with open(output_file, "w", newline="") as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(results[0].keys())
        )

        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
