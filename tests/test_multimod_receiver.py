"""
Synthetic-IQ tests for src/radio/multimod_receiver.py (multimod_frame_v1).

Every test uses a simulated channel with fixed seeds. These tests show the
receiver logic is self-consistent. They are NOT evidence of conducted or
over-the-air RF operation.
"""

from fractions import Fraction

import numpy as np
import pytest
from scipy.signal import resample_poly
from scipy.special import erfc

from src.radio.bpsk_receiver import fractional_advance
from src.radio.multimod_frame import (
    build_framed_waveform,
    demap_symbols,
    m_sequence_127,
    map_bits,
)
from src.radio.multimod_receiver import MultimodFrameSpec, receive_multimod

TX = 2_083_333.0
RX = 2_048_000.0
MODS = ("BPSK", "QPSK", "16QAM")
SMALL = dict(total_symbols=4096, payload_bytes=128)   # 16 384-sample cyclic buffer


def Q(x):
    return 0.5 * erfc(x / np.sqrt(2))


THEORY = {
    "BPSK": lambda e: Q(np.sqrt(2 * e)),
    "QPSK": lambda e: Q(np.sqrt(e)),
    "16QAM": lambda e: 0.75 * Q(np.sqrt(e / 5)),   # Gray, nearest-neighbour approx.
}


def frame(mod, **kw):
    iq, meta, bits = build_framed_waveform(mod, **{**SMALL, **kw})
    return iq, MultimodFrameSpec.from_metadata(meta), bits, meta


def channel(iq, *, reps=4, offset=0, rx_rate=RX, ppm=0.0, frac=0.0, cfo=0.0, phase=0.0,
            gain=1.0, esn0=None, seed=0, cut=None):
    """Cyclic TX -> fractional delay -> clock/rate change -> gain/phase/CFO -> AWGN."""
    rng = np.random.default_rng(seed)
    x = np.roll(np.tile(iq.astype(np.complex128), reps), -offset)
    if frac:
        x = fractional_advance(x, -frac)            # delay by `frac` TX samples
    actual_tx = TX * (1 + ppm * 1e-6)
    if rx_rate != TX or ppm:
        r = Fraction(rx_rate / actual_tx).limit_denominator(5000)
        x = resample_poly(x, r.numerator, r.denominator)
    n = np.arange(len(x))
    x = gain * x * np.exp(1j * (2 * np.pi * cfo * n / rx_rate + phase))
    if esn0 is not None:
        sigma2 = gain ** 2 * (4 * rx_rate / TX) / 10 ** (esn0 / 10)
        x = x + np.sqrt(sigma2 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    if cut is not None:
        x = x[:cut]
    return x.astype(np.complex64)


# ------------------------------------------------------------------ format
@pytest.mark.parametrize("mod,bps", [("BPSK", 1), ("QPSK", 2), ("16QAM", 4)])
def test_map_demap_all_labels_round_trip_and_unit_energy(mod, bps):
    labels = np.array([[(v >> i) & 1 for i in range(bps)] for v in range(2 ** bps)], np.uint8).ravel()
    s = map_bits(labels, mod)
    assert np.array_equal(demap_symbols(s, mod), labels)
    assert np.mean(np.abs(s) ** 2) == pytest.approx(1.0)
    assert len(np.unique(np.round(s, 9))) == 2 ** bps
    # Regression: uint8 input used to map bit 1 to +255.
    assert np.max(np.abs(s)) < 1.5


def test_sync_word_is_maximal_length_and_orthogonal_to_pilot():
    s = m_sequence_127().real
    periodic = [np.dot(s, np.roll(s, k)) for k in range(127)]
    assert periodic[0] == 127 and set(np.round(periodic[1:])) == {-1}
    assert abs(s.sum()) == 1


def test_metadata_checks():
    _, spec, _, meta = frame("QPSK")
    assert spec.payload_symbols_count == 512 and spec.burst_symbols == 64 + 127 + 512
    with pytest.raises(ValueError, match="inconsistent"):
        MultimodFrameSpec.from_metadata({**meta, "payload_symbols": 999})
    with pytest.raises(ValueError, match="multimod_frame_v1"):
        MultimodFrameSpec.from_metadata({**meta, "format": "bpsk_frame_v2"})


# ------------------------------------------------------------- round trips
@pytest.mark.parametrize("mod", MODS)
def test_noiseless_integer_timing_round_trip(mod):
    iq, spec, bits, meta = frame(mod)
    r = receive_multimod(channel(iq, rx_rate=TX, offset=700), spec, TX, TX)
    assert r.detected and r.frames_detected >= 3
    assert r.ber == 0.0
    assert all(f.recovered_payload_hex == meta["payload_hex"] for f in r.frames)
    assert all(f.known_symbol_errors == 0 for f in r.frames)
    # An ideal matched filter on this TX waveform gives 42.8-43.1 dB
    # (41-tap RRC pair). The receiver must get close to that floor.
    assert all(np.isfinite(f.evm_rms_percent) and f.snr_db > 40 for f in r.frames)


@pytest.mark.parametrize("mod", MODS)
def test_dc_offset_removed_without_biasing_the_dc_pilot(mod):
    # Regression: whole-capture mean subtraction cost 7-14 dB at CFO = 0.
    iq, spec, _, meta = frame(mod)
    y = channel(iq, rx_rate=TX, offset=700) + (0.3 - 0.2j)   # receiver DC offset
    r = receive_multimod(y, spec, TX, TX)
    assert r.ber == 0.0 and all(f.snr_db > 40 for f in r.frames)


@pytest.mark.parametrize("mod", MODS)
@pytest.mark.parametrize("cfo", [-73_000.0, -12_500.0, 9_000.0, 64_000.0])
def test_cfo_positive_and_negative(mod, cfo):
    iq, spec, _, _ = frame(mod)
    r = receive_multimod(channel(iq, cfo=cfo, offset=1234, esn0=25, seed=1), spec, TX, RX)
    assert r.frames_detected >= 3 and r.ber == 0.0
    for f in r.frames:
        assert f.coarse_cfo_hz + f.residual_cfo_hz == pytest.approx(cfo, abs=200)


@pytest.mark.parametrize("mod", MODS)
@pytest.mark.parametrize("frac", [0.13, 0.5, 0.81])
def test_fractional_timing(mod, frac):
    iq, spec, _, _ = frame(mod)
    r = receive_multimod(channel(iq, rx_rate=TX, frac=frac, offset=333, esn0=30, seed=2), spec, TX, TX)
    assert r.frames_detected >= 3 and r.ber == 0.0


@pytest.mark.parametrize("mod", MODS)
def test_random_gain_and_phase(mod):
    iq, spec, _, _ = frame(mod)
    rng = np.random.default_rng(7)
    for trial in range(3):
        g, ph = float(rng.uniform(0.05, 40.0)), float(rng.uniform(-np.pi, np.pi))
        r = receive_multimod(channel(iq, gain=g, phase=ph, cfo=-20_000, offset=99 + trial,
                                     esn0=25, seed=trial), spec, TX, RX)
        assert r.frames_detected >= 3 and r.ber == 0.0


@pytest.mark.parametrize("mod", MODS)
@pytest.mark.parametrize("ppm", [-50.0, 50.0])
def test_sample_rate_offset_ppm(mod, ppm):
    iq, spec, _, _ = frame(mod, payload_bytes=256)     # longest payloads: worst drift
    r = receive_multimod(channel(iq, ppm=ppm, cfo=31_000, offset=4321, esn0=25, seed=3), spec, TX, RX)
    assert r.frames_detected >= 3 and r.ber == 0.0


# ------------------------------------------------------- detection behaviour
@pytest.mark.parametrize("mod", MODS)
def test_noise_only_produces_no_frame_and_no_ber(mod):
    _, spec, _, _ = frame(mod)
    for seed in range(5):
        rng = np.random.default_rng(100 + seed)
        noise = rng.standard_normal(300_000) + 1j * rng.standard_normal(300_000)
        r = receive_multimod(noise, spec, TX, RX)
        assert not r.detected and r.ber is None and r.total_payload_bits_compared is None
        assert r.max_sync_metric < r.detection_threshold


def test_zero_padding_and_repetitions_give_exactly_one_detection_per_frame():
    iq, spec, _, _ = frame("QPSK")
    reps, offset = 6, 2000
    y = channel(iq, reps=reps, rx_rate=TX, offset=offset, esn0=30)
    r = receive_multimod(y, spec, TX, TX, max_frames=16)
    starts = [f.sync_start_sample for f in r.frames]
    # Sync starts are at k*frame + 64*sps - offset; complete frames only.
    expected = [k * spec.frame_samples + 64 * 4 - offset for k in range(reps + 1)]
    expected = [e for e in expected if e - 64 * 4 - 32 >= 0 and e + (spec.burst_symbols - 64) * 4 + 32 <= len(y)]
    assert starts == expected
    assert len(set(starts)) == len(starts)
    assert np.all(np.diff(starts) == spec.frame_samples)


@pytest.mark.parametrize("mod", MODS)
def test_truncated_frame_is_reported_not_decoded(mod):
    iq, spec, _, _ = frame(mod)
    # Cut the capture in the middle of the third burst's payload.
    third_sync = 2 * spec.frame_samples + 64 * 4
    cut = third_sync + 127 * 4 + 40 * 4
    y = channel(iq, reps=3, rx_rate=TX, offset=0, esn0=30, cut=cut)
    r = receive_multimod(y, spec, TX, TX)
    assert r.truncated_frames >= 1
    assert all(f.sync_start_sample + (spec.burst_symbols - 64) * 4 <= len(y) for f in r.frames)
    assert r.ber == 0.0


def test_capture_shorter_than_burst():
    iq, spec, _, _ = frame("BPSK")
    r = receive_multimod(iq[:500], spec, TX, TX)
    assert not r.detected and r.notes


def test_input_validation():
    _, spec, _, _ = frame("BPSK")
    with pytest.raises(ValueError):
        receive_multimod(np.array([], complex), spec, TX, RX)
    with pytest.raises(ValueError):
        receive_multimod(np.array([np.nan, 1j]), spec, TX, RX)
    with pytest.raises(ValueError, match="max_cfo_hz"):
        receive_multimod(np.ones(10_000, complex), spec, TX, RX, max_cfo_hz=300_000)
    with pytest.raises(ValueError, match="inconsistent"):
        receive_multimod(np.ones(10_000, complex), spec, TX, 256_000)


# ------------------------------------------------------------- BER / SNR / EVM
@pytest.mark.parametrize("mod,esn0", [("BPSK", 4.0), ("QPSK", 7.0), ("16QAM", 13.0)])
def test_ber_and_snr_estimate_match_awgn_theory(mod, esn0):
    iq, spec, _, _ = frame(mod, payload_bytes=256)
    errors = bits = 0
    snr = []
    for seed in range(4):
        y = channel(iq, reps=8, offset=300 + 77 * seed, cfo=23_000, phase=0.7, esn0=esn0, seed=seed)
        r = receive_multimod(y, spec, TX, RX, max_frames=16)
        assert r.frames_detected >= 6
        errors += r.total_payload_bit_errors
        bits += r.total_payload_bits_compared
        snr += [f.snr_db for f in r.frames]
    theory = THEORY[mod](10 ** (esn0 / 10))
    measured = errors / bits
    assert bits >= 40_000
    # Measured (pre-commit): 1.02-1.23x theory. Allow statistical spread and
    # <= ~0.5 dB implementation loss; never "better than theory" by > 2x.
    assert 0.5 * theory < measured < 1.6 * theory
    assert np.mean(snr) == pytest.approx(esn0, abs=0.75)


@pytest.mark.parametrize("mod", MODS)
def test_evm_matches_noise_level(mod):
    iq, spec, _, _ = frame(mod)
    r = receive_multimod(channel(iq, esn0=20, offset=50, seed=9), spec, TX, RX)
    for f in r.frames:
        assert f.evm_rms_percent == pytest.approx(10.0, rel=0.25)   # 1/sqrt(100) = 10 %
        assert np.isfinite(f.snr_db) and np.isfinite(f.ber)


def test_detection_probability_at_low_snr():
    iq, spec, _, _ = frame("QPSK")
    detected = possible = 0
    for seed in range(4):
        y = channel(iq, reps=8, offset=500 + 31 * seed, cfo=-41_000, esn0=2.0, seed=seed)
        r = receive_multimod(y, spec, TX, RX, max_frames=16)
        detected += r.frames_detected
        possible += int(len(y) * TX / RX // spec.frame_samples) - 1
    assert detected / possible >= 0.9    # measured 42/42 at 2 dB


@pytest.mark.parametrize("mod", MODS)
def test_full_size_script_frame_decodes(mod, tmp_path):
    """The exact waveform scripts/run_multimod_experiment.py writes (65 536 symbols)."""
    import json
    from src.radio.multimod_frame import save_framed_waveform
    iq_path, meta_path, _, _ = save_framed_waveform(tmp_path, mod, payload_bytes=128,
                                                    total_symbols=65536, sps=4,
                                                    sample_rate=2083333, seed=42)
    meta = json.loads(meta_path.read_text())
    spec = MultimodFrameSpec.from_metadata(meta)
    iq = np.fromfile(iq_path, dtype=np.complex64)
    assert len(iq) == meta["samples"] == 262_144
    y = channel(iq, reps=5, offset=100_000, cfo=-27_000, phase=1.3, esn0=20, seed=4)[:1_048_576]
    r = receive_multimod(y, spec, TX, RX)
    assert r.frames_detected >= 3 and r.ber == 0.0
    assert all(f.recovered_payload_hex == meta["payload_hex"] for f in r.frames)


def test_preparation_script_runs_without_pythonpath(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    out = subprocess.run([sys.executable, str(root / "scripts/run_multimod_experiment.py"),
                          "--modulations", "QPSK", "--output-dir", str(tmp_path)],
                         capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "RF status: NOT TRANSMITTED" in out.stdout
