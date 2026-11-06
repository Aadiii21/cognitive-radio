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

MODULATION = "16-QAM"  # Change to BPSK or QPSK for validation.

SER_LIMIT = 0.01
BER_LIMIT = 0.005
SYNC_LIMIT = 0.80


# ==================================================
# PACKET GENERATION
# ==================================================

def build_packet(points):

    rng = np.random.default_rng(2026)
    M = len(points)

    training = rng.integers(
        0, M, TRAINING_LENGTH, dtype=np.uint8
    )

    sync_word = rng.integers(
        0, M, SYNC_LENGTH, dtype=np.uint8
    )

    payload = rng.integers(
        0, M, PAYLOAD_LENGTH, dtype=np.uint8
    )

    pilot_rng = np.random.default_rng(9090)

    pilot = pilot_rng.integers(
        0, M, PILOT_LENGTH, dtype=np.uint8
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

def run_receiver(seed, points, constellation, packet, noise_voltage=None):

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

    tb = gr.top_block("Generalized pilot-assisted receiver")

    source = blocks.vector_source_b(
        packet.tolist(), False
    )

    mapper = digital.chunks_to_symbols_bc(
        points.tolist()
    )

    tx_filter = filter.interp_fir_filter_ccf(
        sps, tx_taps
    )

    if noise_voltage is None:
        noise_voltage = NOISE

    channel = channels.channel_model(
        noise_voltage=noise_voltage,
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

    costas_order = 2 if len(points) == 2 else 4
    costas = digital.costas_loop_cc(
        COSTAS_BANDWIDTH, costas_order, False
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
def symbols_to_bits(symbols, bits_per_symbol):
    symbols = np.asarray(symbols, dtype=np.uint16)

    shifts = np.arange(
        bits_per_symbol - 1, -1, -1
    )

    return (
        (symbols[:, None] >> shifts) & 1
    ).astype(np.uint8).reshape(-1)


def calculate_metrics(decoded, reference, bits_per_symbol):

    symbol_errors = int(
        np.count_nonzero(decoded != reference)
    )

    tx_bits = symbols_to_bits(reference, bits_per_symbol)
    rx_bits = symbols_to_bits(decoded, bits_per_symbol)

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
    pilot,
    noise_voltage=None
):

    rx = run_receiver(
        seed,
        points,
        constellation,
        packet,
        noise_voltage=noise_voltage
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
        print("\nBlock 4: phase tracking in 16-symbol windows")

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

    bits_per_symbol = int(np.log2(len(points)))

    ser, ber, symbol_errors, bit_errors = calculate_metrics(
        decoded, payload, bits_per_symbol
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

        block_tx_bits = symbols_to_bits(
            block_reference, bits_per_symbol
        )
        block_rx_bits = symbols_to_bits(
            block_decoded, bits_per_symbol
        )

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
            "BER": block_bit_errors / (block_length * bits_per_symbol)
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

    modulation_configs = {
        "BPSK": digital.constellation_bpsk,
        "QPSK": digital.constellation_qpsk,
        "16-QAM": digital.constellation_16qam,
    }

    if MODULATION not in modulation_configs:
        raise ValueError(f"Unsupported modulation: {MODULATION}")

    constellation = modulation_configs[MODULATION]().base()

    points = np.asarray(
        constellation.points(),
        dtype=np.complex64
    )

    bits_per_symbol = int(np.log2(len(points)))

    (
        packet,
        training,
        sync_word,
        payload,
        pilot,
        pilot_count
    ) = build_packet(points)

    print("=" * 78)
    print(f"GENERALIZED {MODULATION} PACKET RECEIVER")
    print("=" * 78)

    print(f"Constellation size:  {len(points)}")
    print(f"Bits per symbol:     {bits_per_symbol}")
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
            f"SER={result['SER']:.6f} | "
            f"BER={result['BER']:.6f} | "
            f"{'PASS' if result['packet_success'] else 'FAIL'}"
        )

    successful = sum(
        r["packet_success"] for r in results
    )

    ser_values = np.array([r["SER"] for r in results])
    ber_values = np.array([r["BER"] for r in results])

    print("\n" + "=" * 78)
    print("AGGREGATE RESULTS")
    print("=" * 78)

    print(f"Modulation:          {MODULATION}")
    print(f"Successful packets:  {successful}/{len(results)}")
    print(f"Packet success rate: {successful / len(results):.1%}")
    print(f"Mean SER:            {np.mean(ser_values):.6f}")
    print(f"Mean BER:            {np.mean(ber_values):.6f}")
    print(f"Worst SER:           {np.max(ser_values):.6f}")
    print(f"Worst BER:           {np.max(ber_values):.6f}")
    print(f"SER standard dev:    {np.std(ser_values):.6f}")
    print(f"BER standard dev:    {np.std(ber_values):.6f}")

    os.makedirs("results", exist_ok=True)

    output_file = (
        f"results/packet_receiver_{MODULATION.lower().replace('-', '')}_validation.csv"
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
