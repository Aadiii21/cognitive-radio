"""
Software-only tests of the bpsk_frame_v2 TX waveform and BPSK receiver.

These tests use a *simulated* channel (rate mismatch, CFO, phase, fractional
delay, DC offset, 8-bit quantisation, AWGN). They show that the receiver
logic is self-consistent. They are NOT evidence of physical RF operation.
"""

import json
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import resample_poly
from scipy.special import erfc

from src.radio.bpsk_frame import (
    FrameSpec,
    bits_to_bytes,
    build_frame_waveform,
    bytes_to_bits,
    m_sequence_preamble,
    rrc_taps,
)
from src.radio.bpsk_receiver import calculate_ber, receive_bpsk

TX_RATE = 2_083_333.333
RX_RATE = 2_048_000.0
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_spec(total_symbols=4096, seed=1):
    rng = np.random.default_rng(seed)
    payload = rng.integers(0, 256, 64, dtype=np.uint8).tolist()
    return FrameSpec(preamble_bits=m_sequence_preamble().tolist(),
                     payload_bytes=payload, total_symbols=total_symbols)


def simulate_capture(spec, *, repeats=4, rx_rate=RX_RATE, tx_rate=TX_RATE, cfo_hz=0.0,
                     phase=0.0, esn0_db=None, dc=0j, start_offset=0, quantize=False,
                     amplitude=1.0, seed=0, n_capture=None):
    """Cyclic TX of one frame -> rate change -> CFO/phase -> noise -> DC -> 8-bit."""
    rng = np.random.default_rng(seed)
    frame = build_frame_waveform(spec).astype(np.complex128)
    tx = np.tile(frame, repeats)
    tx = np.roll(tx, -start_offset)
    if rx_rate != tx_rate:
        r = Fraction(rx_rate / tx_rate).limit_denominator(5000)
        rx = resample_poly(tx, r.numerator, r.denominator)
    else:
        rx = tx.copy()
    n = np.arange(len(rx))
    rx = amplitude * rx * np.exp(1j * (2 * np.pi * cfo_hz * n / rx_rate + phase))
    if esn0_db is not None:
        # Burst power at RX is amplitude^2 (unit-RMS burst). Es/N0 = P * sps_rx / sigma^2
        sps_rx = spec.sps * rx_rate / tx_rate
        sigma2 = amplitude ** 2 * sps_rx / 10 ** (esn0_db / 10)
        rx = rx + np.sqrt(sigma2 / 2) * (rng.standard_normal(len(rx)) + 1j * rng.standard_normal(len(rx)))
    rx = rx + dc
    if quantize:
        # RTL-SDR style uint8 I/Q, then the same unpacking as rtl_sdr_sensor.
        i = np.clip(np.round(rx.real + 127.5), 0, 255)
        q = np.clip(np.round(rx.imag + 127.5), 0, 255)
        rx = (i - 127.5) + 1j * (q - 127.5)
    if n_capture is not None:
        rx = rx[:n_capture]
    return rx.astype(np.complex64)


def test_bit_order_round_trip_and_lsb_convention():
    data = np.array([0x01, 0x80, 0xA5], dtype=np.uint8)
    lsb = bytes_to_bits(data, "lsb_first")
    assert lsb[:8].tolist() == [1, 0, 0, 0, 0, 0, 0, 0]
    assert bits_to_bytes(lsb, "lsb_first").tolist() == data.tolist()
    msb = bytes_to_bits(data, "msb_first")
    assert bits_to_bytes(msb, "msb_first").tolist() == data.tolist()


def test_preamble_has_unambiguous_autocorrelation():
    s = 1 - 2.0 * m_sequence_preamble()
    c = np.abs(np.correlate(s, s, "full"))
    assert c.max() == 64
    assert np.sort(c)[-2] <= 10  # old 0101 preamble: 63


def test_frame_symbols_at_k_times_sps_and_silent_padding():
    spec = make_spec()
    iq = build_frame_waveform(spec)
    mf = np.convolve(iq, rrc_taps(), mode="same")
    sym = mf[: spec.burst_symbols * spec.sps: spec.sps]
    assert np.all(np.sign(sym.real) == spec.burst_reference_symbols().real)
    tail_start = (spec.burst_symbols + 6) * spec.sps
    assert np.max(np.abs(iq[tail_start:-6 * spec.sps])) < 1e-6
    burst = iq[: spec.burst_symbols * spec.sps]
    assert np.mean(np.abs(burst) ** 2) == pytest.approx(1.0, rel=1e-4)


def test_clean_same_rate_recovers_payload_exactly():
    spec = make_spec()
    rx = simulate_capture(spec, rx_rate=TX_RATE, start_offset=1234)
    res = receive_bpsk(rx, spec, TX_RATE, TX_RATE)
    assert res.detected and res.frames_detected >= 3
    assert res.ber == 0.0
    expected_hex = bytes(spec.payload_bytes).hex()
    assert all(f.recovered_payload_hex == expected_hex for f in res.frames)
    assert all(f.payload_bits_compared == 512 for f in res.frames)


def test_impaired_channel_rate_mismatch_cfo_phase_dc_quantisation():
    spec = make_spec()
    cfo = 37_250.0
    rx = simulate_capture(spec, cfo_hz=cfo, phase=2.7, esn0_db=15, dc=3 + 2j,
                          start_offset=777, quantize=True, amplitude=20.0, seed=3)
    res = receive_bpsk(rx, spec, TX_RATE, RX_RATE)
    assert res.detected and res.frames_detected >= 3
    assert res.ber == 0.0
    for f in res.frames:
        est = res.coarse_cfo_hz + f.residual_cfo_hz
        # CFO was applied on the RX grid; receiver reports it on the TX grid
        # after rate conversion, i.e. the same physical frequency in Hz.
        assert est == pytest.approx(cfo, abs=100.0)
        assert f.preamble_bit_errors == 0
    assert abs(res.resample_ratio_error_ppm) < 1.0


def test_inverted_polarity_is_resolved_by_preamble():
    spec = make_spec()
    rx = simulate_capture(spec, rx_rate=TX_RATE, phase=np.pi, esn0_db=20, start_offset=50)
    res = receive_bpsk(rx, spec, TX_RATE, TX_RATE)
    assert res.ber == 0.0


def test_noise_only_produces_no_detection_and_no_ber():
    spec = make_spec()
    rng = np.random.default_rng(9)
    noise = (rng.standard_normal(4 * spec.frame_samples) + 1j * rng.standard_normal(4 * spec.frame_samples))
    res = receive_bpsk(noise.astype(np.complex64), spec, TX_RATE, RX_RATE)
    assert not res.detected
    assert res.ber is None and res.total_payload_bits_compared is None
    assert res.notes


def test_snr_estimate_tracks_true_esn0():
    spec = make_spec()
    for esn0 in (8.0, 14.0):
        rx = simulate_capture(spec, esn0_db=esn0, cfo_hz=-12_000, start_offset=300, seed=int(esn0))
        res = receive_bpsk(rx, spec, TX_RATE, RX_RATE)
        snr = np.mean([f.snr_db for f in res.frames])
        assert snr == pytest.approx(esn0, abs=1.5)


def test_ber_at_low_snr_is_consistent_with_bpsk_theory():
    spec = make_spec(total_symbols=2048)
    esn0 = 4.0
    errors = bits = 0
    for seed in range(6):
        rx = simulate_capture(spec, repeats=8, esn0_db=esn0, cfo_hz=5_000, phase=0.3,
                              start_offset=97 * seed, seed=100 + seed)
        res = receive_bpsk(rx, spec, TX_RATE, RX_RATE, max_frames=16)
        errors += res.total_payload_bit_errors
        bits += res.total_payload_bits_compared
    theory = 0.5 * erfc(np.sqrt(10 ** (esn0 / 10)))
    measured = errors / bits
    # ~20k bits, theory ~1.25e-2: allow implementation loss up to ~1 dB, no "better than theory" beyond noise.
    upper = 0.5 * erfc(np.sqrt(10 ** ((esn0 - 1.0) / 10)))
    assert bits > 15_000
    assert 0.5 * theory < measured < upper * 1.2


def test_calculate_ber_rejects_length_mismatch():
    with pytest.raises(ValueError):
        calculate_ber([0, 1, 1], [0, 1])
    assert calculate_ber([0, 1, 1, 0], [0, 1, 0, 0]) == (0.25, 1, 4)


def test_old_format_metadata_is_rejected():
    meta = json.loads((PROJECT_ROOT / "results/baseband/prepared/bpsk_joined_seed42.json").read_text())
    with pytest.raises(ValueError, match="bpsk_frame_v2"):
        FrameSpec.from_metadata(meta)


def test_prepared_v2_waveform_matches_its_metadata():
    meta_path = PROJECT_ROOT / "results/baseband/prepared/bpsk_frame_v2_seed42.json"
    meta = json.loads(meta_path.read_text())
    spec = FrameSpec.from_metadata(meta)
    iq = np.fromfile(PROJECT_ROOT / meta["iq_file"], dtype=np.complex64)
    assert len(iq) == meta["samples"] == spec.frame_samples
    np.testing.assert_allclose(iq, build_frame_waveform(spec), atol=1e-6)
    # Full-size frame through the impaired channel.
    rx = simulate_capture(spec, repeats=4, cfo_hz=21_000, phase=-1.0, esn0_db=12,
                          start_offset=100_000, quantize=True, amplitude=25.0, seed=5,
                          n_capture=1_048_576)
    res = receive_bpsk(rx, spec, TX_RATE, RX_RATE)
    assert res.frames_detected >= 3
    assert res.ber == 0.0
