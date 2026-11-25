#!/usr/bin/env python3
"""
Loopback experiment runner: Pluto TX -> RTL-SDR RX, conducted (attenuator) or OTA (antennas).

Modes
-----
Dry run (default; no hardware touched):
    python scripts/run_hardware_experiment.py
    Validates the waveform file and its metadata, prints the planned
    configuration and the occupied band.

Physical experiment (operator-confirmed; --rf-path conducted --attenuator-db N, or
--rf-path ota --antenna-separation-m D):
    python scripts/run_hardware_experiment.py --enable-rf --freq 866000000 --rf-path ota --antenna-separation-m 1
    1. device / connectivity checks
    2. load waveform + metadata + payload (bpsk_frame_v2 only)
    3. checklist present + typed operator confirmation
    4. Pluto starts CYCLIC transmission (non-blocking)
    5. RTL-SDR captures while the Pluto is transmitting
    6. Pluto stops (always, also on error)
    7. raw RX bytes + sidecar metadata saved (never the TX file)
    8. receiver: sync, demodulation, payload BER
    9. one result JSON

Receive-only RTL-SDR check (Pluto untouched, nothing transmitted):
    python scripts/run_hardware_experiment.py --rx-only --freq 866000000

Offline re-processing of a saved capture (no hardware):
    python scripts/run_hardware_experiment.py --rx-file results/hardware/captures/rx_....cu8

A BER is only reported when at least one preamble passes the detection
threshold. No value in the result file is a placeholder.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.radio import pluto_tx_adapter  # noqa: E402
from src.radio.pluto_pyadi_tx import PlutoPyadiTX  # noqa: E402
from src.radio.bpsk_frame import FrameSpec  # noqa: E402
from src.radio.multimod_receiver import MultimodFrameSpec, receive_multimod  # noqa: E402
from src.radio.bpsk_receiver import (  # noqa: E402
    DEFAULT_DETECTION_THRESHOLD,
    receive_bpsk,
)
from src.radio.hardware_config import (  # noqa: E402
    PLUTO_URI,
    RTL_DEFAULT_SAMPLE_RATE,
    RTL_SAMPLE_RATE_RANGES,
    is_supported_rtl_rate,
    rtl_exact_sample_rate,
    validate_pluto_sample_rate,
)
from src.radio.rtl_sdr_sensor import RTLSDRSensor, parse_rtl_exact_rate  # noqa: E402,F401

DEFAULT_WAVEFORM = PROJECT_ROOT / "results/baseband/prepared/bpsk_frame_v2_seed42.json"
CHECKLIST = PROJECT_ROOT / "docs/PHYSICAL_EXPERIMENT_CHECKLIST.md"
CAPTURE_DIR = PROJECT_ROOT / "results/hardware/captures"
RESULTS_DIR = PROJECT_ROOT / "results/hardware/experiment_results"
SRD_BAND_HZ = (865_000_000, 868_000_000)
CONFIRMATION_WORD = "TRANSMIT"


# ============================================================
# Waveform
# ============================================================
SUPPORTED_FORMATS = ("bpsk_frame_v2", "multimod_frame_v1")


def load_waveform(metadata_path):
    """Load a framed waveform (bpsk_frame_v2 or multimod_frame_v1).

    Returns (iq, metadata, spec): FrameSpec or MultimodFrameSpec.
    """
    metadata_path = Path(metadata_path)
    meta = json.loads(metadata_path.read_text())
    fmt = meta.get("format")
    if fmt == "multimod_frame_v1":
        spec = MultimodFrameSpec.from_metadata(meta)
    elif fmt == "bpsk_frame_v2":
        spec = FrameSpec.from_metadata(meta)
    else:
        raise ValueError(
            f"Waveform metadata format is {fmt!r}; supported: {SUPPORTED_FORMATS}. Older waveforms "
            f"(e.g. bpsk_joined_seed42, 0101 preamble) are not supported: use bpsk_frame_v2 or "
            f"multimod_frame_v1."
        )
    iq_path = Path(meta["iq_file"])
    if not iq_path.is_absolute():
        iq_path = PROJECT_ROOT / iq_path
    iq = np.fromfile(iq_path, dtype=np.complex64)
    if len(iq) != meta["samples"] or len(iq) != spec.frame_samples:
        raise ValueError(
            f"{iq_path}: {len(iq)} samples, metadata says {meta['samples']}, "
            f"frame spec implies {spec.frame_samples}."
        )
    if not np.all(np.isfinite(iq)):
        raise ValueError(f"{iq_path} contains non-finite samples.")
    meta["iq_file_resolved"] = str(iq_path)
    return iq, meta, spec


def frame_description(spec) -> str:
    if isinstance(spec, MultimodFrameSpec):
        return (f"{spec.modulation}: {spec.pilot_symbols} pilot + {spec.sync_symbols} sync + "
                f"{spec.payload_symbols_count} payload symbols ({len(spec.payload_bits)} bits) + "
                f"{spec.total_symbols - spec.burst_symbols} silent, {spec.sps} SPS, beta {spec.rolloff}")
    return (f"BPSK: {spec.preamble_len} preamble + {spec.payload_len} payload + "
            f"{spec.padding_symbols} silent symbols, {spec.sps} SPS, beta {spec.rolloff}")


def occupied_band(center_hz, symbol_rate, rolloff):
    half = symbol_rate * (1 + rolloff) / 2
    return center_hz - half, center_hz + half


class TransmitConfigError(SystemExit):
    """Raised (before or during TX) when the configuration must not be transmitted."""


RATE_TOLERANCE_HZ = 1.0          # waveform design rate vs requested TX rate
READBACK_RATE_TOLERANCE_PPM = 100.0
MIN_FRAMES_IN_CAPTURE = 2        # guarantees >= 1 complete burst for any start phase


def validate_configuration(args, meta, spec):
    """Fail closed on inconsistent TX/RX rate, capture length or band. No hardware access.

    Returns a dict of the derived values (recorded in the result file).
    """
    try:
        tx_rate = validate_pluto_sample_rate(args.tx_rate)
    except ValueError as e:
        raise TransmitConfigError(str(e)) from e
    design = float(meta["sample_rate_sps"])
    if abs(args.tx_rate - design) > RATE_TOLERANCE_HZ:
        raise TransmitConfigError(
            f"--tx-rate {args.tx_rate} S/s does not match the waveform design rate {design} S/s "
            f"({args.waveform}). The symbol rate and occupied band would differ from the "
            f"metadata. Regenerate the waveform for this rate or use --tx-rate {design:.0f}."
        )
    if not is_supported_rtl_rate(args.rx_rate):
        raise TransmitConfigError(
            f"--rx-rate {args.rx_rate} S/s is not supported by the RTL-SDR ({RTL_SAMPLE_RATE_RANGES})."
        )
    rx_exact = rtl_exact_sample_rate(int(round(args.rx_rate)))
    symbol_rate = tx_rate / spec.sps
    occupied = symbol_rate * (1 + spec.rolloff)
    if occupied >= rx_exact:
        raise TransmitConfigError(
            f"Occupied bandwidth {occupied:.0f} Hz does not fit in RTL-SDR rate {rx_exact:.0f} S/s."
        )
    frame_s = spec.frame_samples / tx_rate
    capture_s = args.capture_samples / rx_exact
    if capture_s < MIN_FRAMES_IN_CAPTURE * frame_s:
        need = int(np.ceil(MIN_FRAMES_IN_CAPTURE * frame_s * rx_exact))
        raise TransmitConfigError(
            f"Capture of {args.capture_samples} samples ({capture_s * 1e3:.1f} ms) is shorter than "
            f"{MIN_FRAMES_IN_CAPTURE} frames ({MIN_FRAMES_IN_CAPTURE * frame_s * 1e3:.1f} ms). "
            f"Use --capture-samples >= {need}."
        )
    lo, hi = enforce_band(args.freq, tx_rate, spec)
    return {
        "tx_rate_requested_hz": tx_rate,
        "waveform_design_rate_hz": design,
        "rx_rate_requested_hz": int(round(args.rx_rate)),
        "rx_rate_expected_exact_hz": rx_exact,
        "symbol_rate_baud": symbol_rate,
        "occupied_bandwidth_hz": occupied,
        "occupied_band_hz": [lo, hi],
        "frame_duration_s": frame_s,
        "capture_duration_s": capture_s,
        "frames_in_capture": capture_s / frame_s,
    }


MIN_PHYSICAL_ATTENUATION_DB = 30.0

TX_BACKENDS = ("pyadi", "gnuradio")


def resolve_tx(args):
    """Fill in args.tx_mode from the backend and refuse invalid pairs (no hardware access).

    pyadi (default, owner decision 2026-11-23: Python controls the hardware):
        pure-Python pyadi-iio, cyclic only.
    gnuradio: the original gr-iio adapter, stream (default) or cyclic.
    """
    backend = getattr(args, "tx_backend", None) or "pyadi"
    if backend not in TX_BACKENDS:
        raise TransmitConfigError(f"--tx-backend must be one of {TX_BACKENDS}")
    mode = getattr(args, "tx_mode", None) or ("cyclic" if backend == "pyadi" else "stream")
    if backend == "pyadi" and mode != "cyclic":
        raise TransmitConfigError("--tx-backend pyadi supports --tx-mode cyclic only.")
    args.tx_backend, args.tx_mode = backend, mode
    return backend, mode


def adapter_class_for(backend):
    return PlutoPyadiTX if backend == "pyadi" else pluto_tx_adapter.PlutoTXAdapter


def enforce_rf_path(args):
    """Declare the physical RF path; fail closed if it is incomplete.

    conducted: Pluto TX -> >= 30 dB physical 50-ohm attenuator -> RTL-SDR. The
      Pluto's TX attenuation is software: if it failed to apply, up to about
      +7 dBm reaches the RTL-SDR (commonly cited damage level +10 dBm); a
      physical pad of >= 30 dB keeps that worst case near -23 dBm.
    ota: antenna on each device (owner decision, 2026-11-23). The operator
      states the antenna separation, which is recorded with every result.
    """
    path = getattr(args, "rf_path", None)
    if path == "ota":
        sep = getattr(args, "antenna_separation_m", None)
        if sep is None or sep <= 0:
            raise TransmitConfigError(
                "--rf-path ota requires --antenna-separation-m <metres> (> 0): the distance "
                "between the Pluto TX and RTL-SDR antennas, recorded with the results.")
        if getattr(args, "attenuator_db", None) is not None:
            raise TransmitConfigError(
                "--attenuator-db is for --rf-path conducted. For OTA, state only "
                "--antenna-separation-m.")
        return {"type": "ota", "antenna_separation_m": float(sep)}
    if path != "conducted":
        raise TransmitConfigError(
            "--rf-path is required with --enable-rf: 'conducted' (cable through a physical "
            "50-ohm attenuator) or 'ota' (antennas, with --antenna-separation-m)."
        )
    att = getattr(args, "attenuator_db", None)
    if att is None or att < MIN_PHYSICAL_ATTENUATION_DB:
        raise TransmitConfigError(
            f"--attenuator-db must state the inline PHYSICAL attenuation, >= "
            f"{MIN_PHYSICAL_ATTENUATION_DB:.0f} dB (got {att}). The Pluto's software attenuation "
            f"does not count."
        )
    return {"type": "conducted", "physical_attenuation_db": float(att)}


def describe_rf_path(rf_path):
    if rf_path["type"] == "ota":
        return f"RF path: OTA, antennas {rf_path['antenna_separation_m']:g} m apart (no cable)"
    return f"RF path: conducted, {rf_path['physical_attenuation_db']:.0f} dB physical attenuator in line"


def enforce_band(center_hz, tx_rate, spec, band=SRD_BAND_HZ):
    """Fail closed unless the whole occupied band Rs*(1+beta) is inside `band`.

    Returns (lo, hi) on success. The check uses the nominal occupied
    bandwidth only; it is not a regulatory compliance assessment.
    """
    if center_hz is None:
        raise TransmitConfigError("--freq is required with --enable-rf (no default transmit frequency).")
    lo, hi = occupied_band(center_hz, tx_rate / spec.sps, spec.rolloff)
    if not (band[0] <= lo and hi <= band[1]):
        raise TransmitConfigError(
            f"Occupied band {lo / 1e6:.4f}-{hi / 1e6:.4f} MHz is not inside "
            f"{band[0] / 1e6:.3f}-{band[1] / 1e6:.3f} MHz. Not transmitting."
        )
    return lo, hi


# ============================================================
# RTL-SDR capture
# ============================================================
def unpack_rtl_u8(raw: np.ndarray) -> np.ndarray:
    """Unsigned 8-bit interleaved I/Q -> complex64 (same convention as rtl_sdr_sensor)."""
    raw = np.asarray(raw, dtype=np.uint8)
    if len(raw) % 2:
        raise ValueError("Odd number of bytes in an interleaved I/Q capture.")
    i = raw[0::2].astype(np.float32) - 127.5
    q = raw[1::2].astype(np.float32) - 127.5
    return (i + 1j * q).astype(np.complex64)


def clipping_fraction(raw: np.ndarray) -> float:
    raw = np.asarray(raw, dtype=np.uint8)
    return float(np.mean((raw == 0) | (raw == 255)))


def capture_rtl(frequency_hz, sample_rate_hz, gain_db, n_samples, discard_samples,
                device_index=0, timeout_s=30.0):
    """Capture RECEIVED raw bytes via RTLSDRSensor.capture_raw (single capture path)."""
    sensor = RTLSDRSensor(
        center_frequencies=[int(frequency_hz)],
        sample_rate=int(round(sample_rate_hz)),
        gain=gain_db,
        capture_samples=max(int(n_samples), 1024),
        device_index=device_index,
    )
    try:
        return sensor.capture_raw(frequency_hz, n_samples, discard_samples, timeout_s=timeout_s)
    finally:
        sensor.close()


# ============================================================
# Receiver stage
# ============================================================
def process_capture(rx_iq, spec, tx_rate, rx_rate, detection_threshold):
    if isinstance(spec, MultimodFrameSpec):
        res = receive_multimod(rx_iq, spec, tx_rate, rx_rate, detection_threshold=detection_threshold)
    else:
        res = receive_bpsk(rx_iq, spec, tx_rate, rx_rate, detection_threshold=detection_threshold)
    d = res.to_dict()
    d["status"] = "frames_detected" if res.detected else "no_frame_detected"
    return res, d


def print_receiver_summary(d):
    print(f"    Status          : {d['status']}")
    max_metric = d.get("max_detection_metric", d.get("max_sync_metric", 0.0))
    print(f"    Max sync metric : {max_metric:.3f} (threshold {d['detection_threshold']})")
    if d.get("coarse_cfo_hz") is not None:
        print(f"    Coarse CFO      : {d['coarse_cfo_hz']:.1f} Hz")
    for i, f in enumerate(d["frames"]):
        start = f.get("start_sample", f.get("sync_start_sample"))
        metric = f.get("detection_metric", f.get("sync_metric"))
        known = f.get("preamble_bit_errors", f.get("known_symbol_errors"))
        cfo = f.get("coarse_cfo_hz", d.get("coarse_cfo_hz") or 0.0) + f["residual_cfo_hz"]
        evm = f" EVM {f['evm_rms_percent']:.1f} %," if "evm_rms_percent" in f else ""
        print(f"    Frame {i}: start {start}{f['fractional_timing']:+.2f}, metric {metric:.3f}, "
              f"CFO {cfo:.0f} Hz, SNR {f['snr_db']:.1f} dB,{evm} known-symbol errs {known}, "
              f"payload errs {f['payload_bit_errors']}/{f['payload_bits_compared']}")
    if d["ber"] is not None:
        print(f"    Payload BER     : {d['ber']:.3e} "
              f"({d['total_payload_bit_errors']}/{d['total_payload_bits_compared']} bits, "
              f"{d['frames_detected']} frame(s))")
    for note in d["notes"]:
        print(f"    Note: {note}")


def write_result(record, results_dir=RESULTS_DIR):
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"experiment_result_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    path.write_text(json.dumps(record, indent=2, default=float))
    return path


# ============================================================
# Pre-flight checks
# ============================================================
def check_devices(backend="pyadi"):
    """Required software for the selected TX backend, plus rtl_sdr and iio_attr."""
    ok = True
    if backend == "pyadi":
        try:
            import adi  # noqa: F401
            import iio  # noqa: F401
            has = hasattr(adi, "Pluto")
        except Exception as e:  # report the reason; do not hide it
            print(f"    pyadi-iio / pylibiio import failed: {e}")
            has = False
        print(f"    pyadi-iio adi.Pluto: {has}")
    else:
        try:
            from gnuradio import iio  # noqa: F401
            has = hasattr(iio, "fmcomms2_sink_fc32")
        except Exception as e:
            print(f"    gnuradio.iio import failed: {e}")
            has = False
        print(f"    gnuradio.iio fmcomms2_sink_fc32: {has}")
    ok &= has
    for tool in ("rtl_sdr", "iio_attr"):
        found = subprocess.run(["which", tool], capture_output=True, text=True).returncode == 0
        print(f"    {tool} binary: {found}")
        ok &= found
    return ok


def check_pluto_connectivity(host):
    r = subprocess.run(["ping", "-c", "1", "-W", "2", host], capture_output=True, text=True)
    print(f"    {host} reachable: {r.returncode == 0}")
    return r.returncode == 0


def operator_confirmation(summary_lines, input_fn=input, rf_type="conducted"):
    """Checklist must exist AND the operator must type the confirmation word."""
    if not CHECKLIST.is_file():
        print(f"    Checklist not found: {CHECKLIST}")
        return False
    print("\n  ---- RF TRANSMISSION CONFIRMATION ----")
    for line in summary_lines:
        print(f"    {line}")
    print("    Confirm ALL of the following before continuing:")
    if rf_type == "ota":
        print("     - OTA: an antenna on the Pluto TX port and on the RTL-SDR, at the stated separation")
        print("     - No cable between Pluto TX and RTL-SDR")
    else:
        print("     - Conducted path only: Pluto TX -> 50-ohm attenuation -> RTL-SDR RX")
        print("     - Attenuation chain sized from MEASURED Pluto output, not the estimate")
        print("     - Never a direct Pluto TX -> RTL-SDR connection")
    print("     - Frequency, bandwidth and level permitted for this test")
    print(f"     - {CHECKLIST.relative_to(PROJECT_ROOT)} reviewed")
    try:
        answer = input_fn(f"  Type {CONFIRMATION_WORD} to transmit: ")
    except EOFError:
        answer = ""
    return answer.strip() == CONFIRMATION_WORD


# ============================================================
# Physical run (TX + RX overlap)
# ============================================================
LO_TOLERANCE_HZ = 1_000.0
GAIN_TOLERANCE_DB = 0.5


def verify_tx_readback(readback, args, spec, band_check=None):
    """Compare Pluto readback with the request. Returns list of fatal problems."""
    problems = []
    if abs(readback["tx_lo_hz"] - args.freq) > LO_TOLERANCE_HZ:
        problems.append(f"TX LO readback {readback['tx_lo_hz']:.0f} Hz != requested {args.freq} Hz")
    if abs(readback["tx_hardwaregain_db"] + args.attenuation) > GAIN_TOLERANCE_DB:
        problems.append(f"TX hardwaregain readback {readback['tx_hardwaregain_db']} dB != "
                        f"-{args.attenuation} dB requested")
    if readback["tx_sample_rate_hz"] <= 0:
        problems.append("TX sample rate readback is not positive")
    elif abs(readback["tx_sample_rate_hz"] / args.tx_rate - 1.0) * 1e6 > READBACK_RATE_TOLERANCE_PPM:
        problems.append(
            f"TX sample rate readback {readback['tx_sample_rate_hz']:.1f} S/s != requested "
            f"{args.tx_rate:.1f} S/s (> {READBACK_RATE_TOLERANCE_PPM:.0f} ppm): the Pluto is not "
            f"running the waveform at its design rate"
        )
    else:
        try:
            if band_check is not None:
                band_check(readback["tx_lo_hz"], readback["tx_sample_rate_hz"])
            else:
                enforce_band(readback["tx_lo_hz"], readback["tx_sample_rate_hz"], spec)
        except TransmitConfigError as e:
            problems.append(f"With read-back rate/LO: {e}")
    return problems


def run_physical(args, iq, meta, spec, input_fn=input, adapter_cls=None, capture_fn=None,
                 readback_fn=None):
    backend, _ = resolve_tx(args)
    adapter_cls = adapter_cls or adapter_class_for(backend)
    capture_fn = capture_fn or capture_rtl
    readback_fn = readback_fn or pluto_tx_adapter.read_pluto_tx_state

    # Fail closed before asking the operator anything.
    rf_path = enforce_rf_path(args)
    derived = validate_configuration(args, meta, spec)
    lo, hi = derived["occupied_band_hz"]
    summary = [
        f"Centre {args.freq / 1e6:.4f} MHz, occupied {lo / 1e6:.4f}-{hi / 1e6:.4f} MHz (inside 865-868 MHz)",
        f"TX rate requested {args.tx_rate:.0f} S/s (will be read back), symbol rate "
        f"{args.tx_rate / spec.sps:.0f} Bd",
        f"Pluto {args.pluto_uri}, TX attenuation {args.attenuation} dB, "
        f"amplitude scale {args.amplitude_scale} (peak {np.max(np.abs(iq)) * args.amplitude_scale:.3f})",
        f"RTL-SDR rate {args.rx_rate:.0f} S/s (exact {derived['rx_rate_expected_exact_hz']:.3f}), "
        f"gain {args.rx_gain} dB, {args.capture_samples} samples "
        f"= {derived['capture_duration_s'] * 1e3:.0f} ms = {derived['frames_in_capture']:.1f} frames",
        f"Waveform {frame_description(spec)}",
        describe_rf_path(rf_path),
        f"Order: Pluto {args.tx_mode} TX ({args.tx_backend}) start -> readback -> RTL-SDR capture "
        f"(TX running) -> TX stop",
    ]
    if not operator_confirmation(summary, input_fn, rf_path["type"]):
        print("  ABORTED: operator confirmation not given. Nothing transmitted.")
        return None

    tx = None
    tx_status = readback = raw = cap_info = None
    error = stop_error = None
    stage = "construct"
    try:
        tx = adapter_cls(uri=args.pluto_uri, sample_rate=int(round(args.tx_rate)),
                         bandwidth=args.tx_bandwidth, amplitude_scale=args.amplitude_scale,
                         cyclic=(args.tx_mode == "cyclic"))
        stage = "configure"
        tx.configure(args.freq, args.attenuation)
        stage = "prepare"
        tx.prepare(iq, args.amplitude_scale)
        stage = "start"
        pluto_tx_adapter.set_rf_enabled(True)
        print(f"  Starting Pluto {args.tx_mode} TX...")
        tx_status = tx.start()
        time.sleep(args.settle_s)
        stage = "readback"
        readback = readback_fn(args.pluto_uri)
        problems = verify_tx_readback(readback, args, spec)
        if problems:
            raise RuntimeError("TX readback verification failed: " + "; ".join(problems))
        print(f"  Pluto readback: rate {readback['tx_sample_rate_hz']:.1f} S/s, "
              f"LO {readback['tx_lo_hz']:.0f} Hz, gain {readback['tx_hardwaregain_db']} dB")
        stage = "capture"
        print("  Capturing with RTL-SDR while TX is running...")
        raw, cap_info = capture_fn(args.freq, args.rx_rate, args.rx_gain,
                                   args.capture_samples, args.discard_samples,
                                   args.rtl_device)
        stage = "done"
    except BaseException as e:  # recorded; TX is stopped and RF disabled in finally
        error = f"{stage}: {type(e).__name__}: {e}"
        if not isinstance(e, Exception):  # KeyboardInterrupt etc.: still clean up, then re-raise
            raise
    finally:
        try:
            if tx is not None:
                tx.stop()
        except Exception as e:
            stop_error = f"{type(e).__name__}: {e}"
        finally:
            pluto_tx_adapter.set_rf_enabled(False)
        print("  Pluto TX stopped, RF disabled." if stop_error is None
              else f"  WARNING: TX stop raised {stop_error}. RF flag disabled; check the Pluto.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tx_rate_used = readback["tx_sample_rate_hz"] if readback else None
    record = {
        "timestamp": datetime.now().isoformat(),
        "mode": f"physical_{rf_path['type']}_loopback",
        "rf_path": rf_path,
        "tx_backend": args.tx_backend,
        "tx_mode": args.tx_mode,
        "waveform_metadata": str(args.waveform),
        "waveform_format": meta["format"],
        "payload_hex": meta["payload_hex"],
        "payload_bit_order": meta["payload_bit_order"],
        "tx": {**(tx_status or {}), "amplitude_scale": args.amplitude_scale,
               "requested_sample_rate_hz": args.tx_rate,
               "requested_frequency_hz": args.freq,
               "requested_attenuation_db": args.attenuation,
               "readback": readback},
        "rx": cap_info,
        "derived_configuration": derived,
        "error": error,
        "stop_error": stop_error,
    }
    if error is not None:
        record["status"] = f"failed_at_{error.split(':', 1)[0]}"
        path = write_result(record)
        print(f"  FAILED ({error})\n  Record: {path}")
        return record

    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    cap_path = CAPTURE_DIR / f"rx_{stamp}.cu8"
    raw.tofile(cap_path)
    rx_rate_used = cap_info["actual_sample_rate_hz"]
    sidecar = {
        "data_kind": RX_CAPTURE_KIND,
        "content": "RTL-SDR received samples (raw uint8 interleaved I/Q). NOT transmit data.",
        "rx_center_frequency_hz": args.freq,
        "rx_sample_rate_hz": rx_rate_used,
        "rx_sample_rate_source": cap_info["actual_sample_rate_source"],
        "rx_sample_rate_requested_hz": cap_info["requested_sample_rate_hz"],
        "rx_gain_db": args.rx_gain,
        "rx_gain_mode": "auto (rtl_sdr -g 0)" if args.rx_gain == 0 else "manual",
        "rf_path": rf_path,
        "tx_sample_rate_hz": tx_rate_used,
        "tx_sample_rate_source": "pluto readback (ad9361-phy voltage0 output sampling_frequency)",
        "tx_readback": readback,
        "waveform_metadata": str(args.waveform),
        "waveform_payload_hex": meta["payload_hex"],
        "samples": int(len(raw) // 2),
        "clipping_fraction": clipping_fraction(raw),
        "capture": cap_info,
        "timestamp": record["timestamp"],
    }
    cap_path.with_suffix(".json").write_text(json.dumps(sidecar, indent=2))
    print(f"  RX capture saved: {cap_path} (+ .json)")
    print(f"    Clipped samples : {100 * sidecar['clipping_fraction']:.3f} %")

    res, d = process_capture(unpack_rtl_u8(raw), spec, tx_rate_used, rx_rate_used,
                             args.detection_threshold)
    record.update({"rx_capture_file": str(cap_path), "rx_sample_rate_hz_used": rx_rate_used,
                   "tx_sample_rate_hz_used": tx_rate_used,
                   "clipping_fraction": sidecar["clipping_fraction"], "receiver": d,
                   "status": d["status"]})
    print_receiver_summary(d)
    path = write_result(record)
    print(f"  Result: {path}")
    return record


# ============================================================
# Tone test: first RF-chain check (CW tone, TX on vs TX off)
# ============================================================
TONE_SAMPLES = 262_144
TONE_MAX_CFO_HZ = 100_000.0
TONE_MIN_OFFSET_HZ = 20_000.0
TONE_DETECT_DB = 15.0          # tone bin, TX on vs the same bin with TX off
TONE_WELCH_SEGMENT = 16_384


def make_tone(tx_rate, offset_hz, n=TONE_SAMPLES):
    """Unit-amplitude complex tone with an integer number of cycles per buffer
    (seamless when repeated). Returns (iq, exact_offset_hz)."""
    k = int(round(offset_hz * n / tx_rate))
    if k == 0:
        raise ValueError("tone offset rounds to 0 Hz")
    iq = np.exp(2j * np.pi * k * np.arange(n) / n).astype(np.complex64)
    return iq, k * tx_rate / n


def tone_band_check_factory(offset_hz):
    def check(lo_hz, tx_rate):
        f = lo_hz + offset_hz
        if not (SRD_BAND_HZ[0] <= f - TONE_MAX_CFO_HZ and f + TONE_MAX_CFO_HZ <= SRD_BAND_HZ[1]):
            raise TransmitConfigError(
                f"Tone at {f / 1e6:.4f} MHz (+-{TONE_MAX_CFO_HZ / 1e3:.0f} kHz CFO margin) is not "
                f"inside {SRD_BAND_HZ[0] / 1e6:.3f}-{SRD_BAND_HZ[1] / 1e6:.3f} MHz. Not transmitting.")
    return check


def validate_tone_configuration(args):
    if args.freq is None:
        raise TransmitConfigError("--freq is required with --enable-rf (no default transmit frequency).")
    try:
        tx_rate = validate_pluto_sample_rate(args.tx_rate)
    except ValueError as e:
        raise TransmitConfigError(str(e)) from e
    if not is_supported_rtl_rate(args.rx_rate):
        raise TransmitConfigError(f"--rx-rate {args.rx_rate} S/s is not supported by the RTL-SDR.")
    rx_exact = rtl_exact_sample_rate(int(round(args.rx_rate)))
    if abs(args.tone_offset_hz) < TONE_MIN_OFFSET_HZ:
        raise TransmitConfigError(f"--tone-offset-hz must be >= {TONE_MIN_OFFSET_HZ:.0f} Hz "
                                  f"(away from the RTL-SDR DC spike).")
    if abs(args.tone_offset_hz) + TONE_MAX_CFO_HZ > 0.4 * rx_exact:
        raise TransmitConfigError("Tone offset plus CFO margin exceeds 40 % of the RX rate.")
    if args.capture_samples < 4 * TONE_WELCH_SEGMENT:
        raise TransmitConfigError(f"--capture-samples must be >= {4 * TONE_WELCH_SEGMENT} for the tone test.")
    _, exact = make_tone(tx_rate, args.tone_offset_hz)
    tone_band_check_factory(exact)(args.freq, tx_rate)
    return {"tx_rate_requested_hz": tx_rate, "rx_rate_expected_exact_hz": rx_exact,
            "tone_offset_exact_hz": exact, "tone_frequency_hz": args.freq + exact}


def tone_psd(iq, fs):
    from scipy.signal import welch
    x = np.asarray(iq, dtype=np.complex128)
    x = x - np.mean(x)
    f, p = welch(x, fs=fs, nperseg=TONE_WELCH_SEGMENT, return_onesided=False)
    order = np.argsort(f)
    return f[order], p[order]


def analyze_tone(iq_on, iq_off, fs, offset_hz, max_cfo_hz=TONE_MAX_CFO_HZ):
    """Find the tone in the TX-on capture and compare that bin with TX off."""
    f, p_on = tone_psd(iq_on, fs)
    _, p_off = tone_psd(iq_off, fs)
    window = (np.abs(f - offset_hz) <= max_cfo_hz) & (np.abs(f) > 5_000.0)
    if not np.any(window):
        raise ValueError("tone search window is empty")
    idx = np.flatnonzero(window)
    k = idx[np.argmax(p_on[idx])]
    floor_on = float(np.median(p_on))
    on_vs_off = float(10 * np.log10(p_on[k] / max(p_off[k], 1e-30)))
    peak_over_floor = float(10 * np.log10(p_on[k] / max(floor_on, 1e-30)))
    detected = on_vs_off >= TONE_DETECT_DB
    return {
        "detected": bool(detected),
        "peak_frequency_hz": float(f[k]),
        "expected_frequency_hz": float(offset_hz),
        "implied_cfo_hz": float(f[k] - offset_hz),
        "implied_cfo_ppm_at_rf": None,
        "tone_bin_tx_on_vs_off_db": on_vs_off,
        "tone_peak_over_median_floor_db": peak_over_floor,
        "detect_threshold_db": TONE_DETECT_DB,
        "resolution_hz": float(fs / TONE_WELCH_SEGMENT),
        "rms_tx_on": float(np.sqrt(np.mean(np.abs(iq_on - np.mean(iq_on)) ** 2))),
        "rms_tx_off": float(np.sqrt(np.mean(np.abs(iq_off - np.mean(iq_off)) ** 2))),
    }


def _save_capture(raw, cap_info, args, tag, extra):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = CAPTURE_DIR / f"{tag}_{stamp}.cu8"
    raw.tofile(path)
    sidecar = {
        "data_kind": RX_CAPTURE_KIND,
        "content": "RTL-SDR received samples (raw uint8 interleaved I/Q). NOT transmit data.",
        "rx_center_frequency_hz": args.freq,
        "rx_sample_rate_hz": cap_info["actual_sample_rate_hz"],
        "rx_sample_rate_source": cap_info.get("actual_sample_rate_source"),
        "rx_gain_db": args.rx_gain,
        "rx_gain_mode": "auto (rtl_sdr -g 0)" if args.rx_gain == 0 else "manual",
        "samples": int(len(raw) // 2),
        "clipping_fraction": clipping_fraction(raw),
        "capture": cap_info,
        "timestamp": datetime.now().isoformat(),
        **extra,
    }
    path.with_suffix(".json").write_text(json.dumps(sidecar, indent=2, default=float))
    return path, sidecar


def run_tone_test(args, input_fn=input, adapter_cls=None, capture_fn=None, readback_fn=None):
    """CW tone: TX on -> readback -> capture -> TX stop -> capture again (baseline)."""
    backend, _ = resolve_tx(args)
    adapter_cls = adapter_cls or adapter_class_for(backend)
    capture_fn = capture_fn or capture_rtl
    readback_fn = readback_fn or pluto_tx_adapter.read_pluto_tx_state

    rf_path = enforce_rf_path(args)
    derived = validate_tone_configuration(args)
    tone, exact = make_tone(derived["tx_rate_requested_hz"], args.tone_offset_hz)
    summary = [
        f"CW tone at {derived['tone_frequency_hz'] / 1e6:.6f} MHz "
        f"(LO {args.freq / 1e6:.4f} MHz + {exact / 1e3:.3f} kHz)",
        f"Pluto {args.pluto_uri}, {args.tx_mode} TX ({args.tx_backend}), attenuation {args.attenuation} dB, "
        f"amplitude scale {args.amplitude_scale} (peak {args.amplitude_scale:.3f})",
        describe_rf_path(rf_path),
        f"RTL-SDR {args.rx_rate:.0f} S/s, gain {args.rx_gain} dB "
        f"({'auto' if args.rx_gain == 0 else 'manual'}), {args.capture_samples} samples",
        "Order: TX start -> readback -> capture (TX on) -> TX stop -> capture (TX off)",
    ]
    if not operator_confirmation(summary, input_fn, rf_path["type"]):
        print("  ABORTED: operator confirmation not given. Nothing transmitted.")
        return None

    tx = None
    tx_status = readback = None
    on = off = None
    error = stop_error = off_error = None
    stage = "construct"
    try:
        tx = adapter_cls(uri=args.pluto_uri, sample_rate=derived["tx_rate_requested_hz"],
                         bandwidth=args.tx_bandwidth, amplitude_scale=args.amplitude_scale,
                         cyclic=(args.tx_mode == "cyclic"))
        stage = "configure"
        tx.configure(args.freq, args.attenuation)
        stage = "prepare"
        tx.prepare(tone, args.amplitude_scale)
        stage = "start"
        pluto_tx_adapter.set_rf_enabled(True)
        print(f"  Starting Pluto {args.tx_mode} tone TX...")
        tx_status = tx.start()
        time.sleep(args.settle_s)
        stage = "readback"
        readback = readback_fn(args.pluto_uri)
        problems = verify_tx_readback(readback, args, None, band_check=tone_band_check_factory(exact))
        if problems:
            raise RuntimeError("TX readback verification failed: " + "; ".join(problems))
        stage = "capture"
        print("  Capturing with TX ON...")
        on = capture_fn(args.freq, args.rx_rate, args.rx_gain, args.capture_samples,
                        args.discard_samples, args.rtl_device)
        stage = "done"
    except BaseException as e:
        error = f"{stage}: {type(e).__name__}: {e}"
        if not isinstance(e, Exception):
            raise
    finally:
        try:
            if tx is not None:
                tx.stop()
        except Exception as e:
            stop_error = f"{type(e).__name__}: {e}"
        finally:
            pluto_tx_adapter.set_rf_enabled(False)
        print("  Pluto TX stopped, RF disabled." if stop_error is None
              else f"  WARNING: TX stop raised {stop_error}. RF flag disabled; check the Pluto.")

    record = {
        "timestamp": datetime.now().isoformat(),
        "mode": f"physical_{rf_path['type']}_tone_test",
        "rf_path": rf_path,
        "tx_backend": args.tx_backend,
        "tx_mode": args.tx_mode,
        "tx": {**(tx_status or {}), "amplitude_scale": args.amplitude_scale,
               "requested_frequency_hz": args.freq, "requested_attenuation_db": args.attenuation,
               "tone_offset_hz": exact, "readback": readback},
        "derived_configuration": derived,
        "error": error,
        "stop_error": stop_error,
    }
    if error is not None:
        record["status"] = f"failed_at_{error.split(':', 1)[0]}"
        print(f"  FAILED ({error})\n  Record: {write_result(record)}")
        return record

    if stop_error is None:
        time.sleep(max(args.settle_s, 0.5))
        try:
            print("  Capturing with TX OFF (baseline)...")
            off = capture_fn(args.freq, args.rx_rate, args.rx_gain, args.capture_samples,
                             args.discard_samples, args.rtl_device)
        except Exception as e:
            off_error = f"{type(e).__name__}: {e}"
    else:
        off_error = "TX may still be on (stop failed); no baseline captured"

    raw_on, info_on = on
    on_path, side_on = _save_capture(raw_on, info_on, args, "tone_on",
                                     {"tx_signal": "cw_tone", "tone_offset_hz": exact, "tx_active": True,
                                      "rf_path": rf_path, "tx_readback": readback})
    record.update({"tx_on_capture": str(on_path), "clipping_fraction_tx_on": side_on["clipping_fraction"]})
    print(f"  TX-on capture : {on_path} (clipping {100 * side_on['clipping_fraction']:.3f} %)")
    if off is None:
        record["status"] = "baseline_capture_failed"
        record["baseline_error"] = off_error
        print(f"  Baseline capture failed: {off_error}\n  Record: {write_result(record)}")
        return record
    raw_off, info_off = off
    off_path, side_off = _save_capture(raw_off, info_off, args, "tone_off",
                                       {"tx_signal": "none (after tone TX stopped)", "tx_active": False,
                                        "rf_path": rf_path})
    analysis = analyze_tone(unpack_rtl_u8(raw_on), unpack_rtl_u8(raw_off),
                            info_on["actual_sample_rate_hz"], exact)
    analysis["implied_cfo_ppm_at_rf"] = analysis["implied_cfo_hz"] / (args.freq + exact) * 1e6
    record.update({"tx_off_capture": str(off_path),
                   "clipping_fraction_tx_off": side_off["clipping_fraction"],
                   "tone_analysis": analysis,
                   "status": "tone_detected" if analysis["detected"] else "tone_not_detected"})
    print(f"  TX-off capture: {off_path}")
    print(f"  Tone          : {'DETECTED' if analysis['detected'] else 'NOT detected'} - "
          f"bin TX-on vs TX-off {analysis['tone_bin_tx_on_vs_off_db']:.1f} dB "
          f"(threshold {TONE_DETECT_DB:.0f}), peak {analysis['peak_frequency_hz'] / 1e3:.2f} kHz, "
          f"implied CFO {analysis['implied_cfo_hz']:.0f} Hz ({analysis['implied_cfo_ppm_at_rf']:.1f} ppm)")
    print(f"  RMS TX on/off : {analysis['rms_tx_on']:.2f} / {analysis['rms_tx_off']:.2f} LSB")
    print(f"  Result: {write_result(record)}")
    return record


# ============================================================
# Receive-only hardware check (no transmission)
# ============================================================
def run_rx_only(args, meta, spec, capture_fn=None):
    """Capture with the RTL-SDR only. The Pluto is never touched.

    Exercises the physical capture path (rate, clipping, provenance, file
    format) and the receiver's no-detection path. Expected receiver status
    with no transmitter: no_frame_detected.
    """
    capture_fn = capture_fn or capture_rtl
    if args.freq is None:
        raise TransmitConfigError("--freq is required with --rx-only.")
    if not is_supported_rtl_rate(args.rx_rate):
        raise TransmitConfigError(f"--rx-rate {args.rx_rate} not supported by the RTL-SDR.")
    rx_exact = rtl_exact_sample_rate(int(round(args.rx_rate)))
    print(f"  RX-ONLY: RTL-SDR capture at {args.freq / 1e6:.4f} MHz, {rx_exact:.3f} S/s, "
          f"gain {args.rx_gain} dB, {args.capture_samples} samples. Pluto not used.")
    raw, cap_info = capture_fn(args.freq, args.rx_rate, args.rx_gain,
                               args.capture_samples, args.discard_samples, args.rtl_device)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    cap_path = CAPTURE_DIR / f"rx_only_{stamp}.cu8"
    raw.tofile(cap_path)
    sidecar = {
        "data_kind": RX_CAPTURE_KIND,
        "content": "RTL-SDR received samples (raw uint8 interleaved I/Q), receive-only: "
                   "NO transmitter active. NOT transmit data.",
        "tx_active": False,
        "rx_center_frequency_hz": args.freq,
        "rx_sample_rate_hz": cap_info["actual_sample_rate_hz"],
        "rx_sample_rate_source": cap_info["actual_sample_rate_source"],
        "rx_sample_rate_requested_hz": cap_info["requested_sample_rate_hz"],
        "rx_gain_db": args.rx_gain,
        "tx_sample_rate_hz": float(meta["sample_rate_sps"]),
        "tx_sample_rate_source": "waveform design rate (no transmission in this capture)",
        "waveform_metadata": str(args.waveform),
        "waveform_payload_hex": meta["payload_hex"],
        "samples": int(len(raw) // 2),
        "clipping_fraction": clipping_fraction(raw),
        "capture": cap_info,
        "timestamp": datetime.now().isoformat(),
    }
    cap_path.with_suffix(".json").write_text(json.dumps(sidecar, indent=2))
    iq = unpack_rtl_u8(raw)
    print(f"  RX capture saved: {cap_path} (+ .json)")
    print(f"    Clipped samples : {100 * sidecar['clipping_fraction']:.3f} %")
    print(f"    Mean I/Q        : {iq.real.mean():+.2f} / {iq.imag.mean():+.2f} (of +-127.5)")
    print(f"    RMS             : {np.sqrt(np.mean(np.abs(iq) ** 2)):.2f}")
    res, d = process_capture(iq, spec, sidecar["tx_sample_rate_hz"], sidecar["rx_sample_rate_hz"],
                             args.detection_threshold)
    print_receiver_summary(d)
    record = {
        "timestamp": sidecar["timestamp"],
        "mode": "rx_only_hardware_check",
        "tx_active": False,
        "rx_capture_file": str(cap_path),
        "rx": cap_info,
        "clipping_fraction": sidecar["clipping_fraction"],
        "receiver": d,
        "status": d["status"],
        "note": "No transmitter: a detected frame here would indicate a false detection.",
    }
    print(f"  Result: {write_result(record)}")
    return record


# ============================================================
# Offline re-processing
# ============================================================
RX_CAPTURE_KIND = "rtl_sdr_rx_capture"
SIMULATED_CAPTURE_KIND = "simulated_rx_capture"
ACCEPTED_CAPTURE_KINDS = (RX_CAPTURE_KIND, SIMULATED_CAPTURE_KIND)


class ProvenanceError(SystemExit):
    """The capture cannot be shown to be RX data for this waveform."""


def load_capture_with_provenance(rx_path, meta):
    """Load a capture and its sidecar. Fails closed on any provenance gap."""
    rx_path = Path(rx_path)
    if not rx_path.is_file():
        raise ProvenanceError(f"Capture not found: {rx_path}")
    sidecar_path = rx_path.with_suffix(".json")
    if not sidecar_path.is_file():
        raise ProvenanceError(f"Missing sidecar {sidecar_path}: RX provenance unknown. Not processing.")
    try:
        sidecar = json.loads(sidecar_path.read_text())
    except json.JSONDecodeError as e:
        raise ProvenanceError(f"Sidecar {sidecar_path} is not valid JSON: {e}") from e
    if not isinstance(sidecar, dict):
        raise ProvenanceError(f"Sidecar {sidecar_path} is not a JSON object.")
    kind = sidecar.get("data_kind")
    if kind not in ACCEPTED_CAPTURE_KINDS:
        raise ProvenanceError(f"Sidecar data_kind {kind!r} not in {ACCEPTED_CAPTURE_KINDS}.")
    if sidecar.get("waveform_payload_hex") != meta["payload_hex"]:
        raise ProvenanceError("Sidecar waveform_payload_hex does not match the selected waveform.")
    for key in ("rx_sample_rate_hz", "tx_sample_rate_hz"):
        v = sidecar.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
            raise ProvenanceError(f"Sidecar {key} missing or invalid: {v!r}")

    if rx_path.suffix == ".cu8":
        raw = np.fromfile(rx_path, dtype=np.uint8)
        rx = unpack_rtl_u8(raw)
        clip = clipping_fraction(raw)
    elif rx_path.suffix in (".cf32", ".cfile"):
        rx = np.fromfile(rx_path, dtype=np.complex64)
        clip = None
    else:
        raise ProvenanceError(f"Unsupported capture format: {rx_path.suffix}")
    expected = sidecar.get("samples")
    if not isinstance(expected, int) or expected != len(rx):
        raise ProvenanceError(f"Sidecar samples {expected!r} != file samples {len(rx)}.")
    return rx, sidecar, clip


def run_offline(args, spec, meta):
    rx_path = Path(args.rx_file)
    rx, sidecar, clip = load_capture_with_provenance(rx_path, meta)
    rx_rate = args.rx_rate_override or sidecar["rx_sample_rate_hz"]
    tx_rate = args.tx_rate_override or sidecar["tx_sample_rate_hz"]
    kind = sidecar["data_kind"]
    print(f"  Offline processing {rx_path} [{kind}] ({len(rx)} samples, "
          f"RX {rx_rate:.1f} S/s, TX {tx_rate:.1f} S/s)")
    res, d = process_capture(rx, spec, float(tx_rate), float(rx_rate), args.detection_threshold)
    print_receiver_summary(d)
    record = {
        "timestamp": datetime.now().isoformat(),
        "mode": "offline_reprocessing",
        "data_kind": kind,
        "simulated": kind == SIMULATED_CAPTURE_KIND,
        "rx_capture_file": str(rx_path),
        "rx_sidecar": sidecar,
        "rx_sample_rate_hz_used": float(rx_rate),
        "tx_sample_rate_hz_used": float(tx_rate),
        "rate_overrides": {"rx": args.rx_rate_override, "tx": args.tx_rate_override},
        "clipping_fraction": clip,
        "waveform_metadata": str(args.waveform),
        "payload_hex": meta["payload_hex"],
        "receiver": d,
        "status": d["status"],
    }
    if not args.no_save:
        print(f"  Result: {write_result(record)}")
    return record


# ============================================================
# CLI
# ============================================================
def build_parser():
    p = argparse.ArgumentParser(description="Pluto -> RTL-SDR loopback runner (conducted or OTA)")
    p.add_argument("--waveform", default=str(DEFAULT_WAVEFORM),
                   help="bpsk_frame_v2 metadata JSON (default: seed 42 frame)")
    p.add_argument("--freq", type=int, default=None,
                   help="Centre frequency Hz. Required with --enable-rf.")
    p.add_argument("--tx-rate", type=float, default=2_083_333.0,
                   help="Pluto TX sample rate (default 2083333)")
    p.add_argument("--rx-rate", type=float, default=float(RTL_DEFAULT_SAMPLE_RATE),
                   help="RTL-SDR sample rate (default 2048000: verified on this RTL-SDR, "
                        "exact in the RTL2832 resampler). The receiver resamples using "
                        "the actual TX and RX rates.")
    p.add_argument("--tx-bandwidth", type=int, default=1_000_000)
    p.add_argument("--pluto-uri", default=PLUTO_URI)
    p.add_argument("--attenuation", type=int, default=30,
                   help="Pluto TX attenuation dB (higher = less power)")
    p.add_argument("--amplitude-scale", type=float, default=0.1)
    p.add_argument("--rx-gain", type=float, default=28.0,
                   help="RTL-SDR tuner gain dB; 0 selects automatic gain (rtl_sdr -g 0)")
    p.add_argument("--rtl-device", type=int, default=0)
    p.add_argument("--capture-samples", type=int, default=1_048_576)
    p.add_argument("--discard-samples", type=int, default=262_144,
                   help="RTL samples dropped at capture start (tuner settling)")
    p.add_argument("--settle-s", type=float, default=1.0,
                   help="Seconds between TX start and RX capture")
    p.add_argument("--detection-threshold", type=float, default=DEFAULT_DETECTION_THRESHOLD)
    p.add_argument("--enable-rf", action="store_true", help="Physical transmission (operator-confirmed)")
    p.add_argument("--rf-path", choices=["conducted", "ota"], default=None,
                   help="Required with --enable-rf: 'conducted' (cable through a physical 50-ohm "
                        "attenuator, with --attenuator-db) or 'ota' (antennas, with "
                        "--antenna-separation-m)")
    p.add_argument("--antenna-separation-m", type=float, default=None,
                   help="Required with --rf-path ota: TX-RX antenna distance in metres (recorded)")
    p.add_argument("--attenuator-db", type=float, default=None,
                   help=f"Required with --enable-rf: inline physical attenuation in dB "
                        f"(>= {MIN_PHYSICAL_ATTENUATION_DB:.0f})")
    p.add_argument("--tx-backend", choices=list(TX_BACKENDS), default="pyadi",
                   help="pyadi (default): pure-Python pyadi-iio, cyclic buffer. "
                        "gnuradio: the original gr-iio adapter.")
    p.add_argument("--tx-mode", choices=["stream", "cyclic"], default=None,
                   help="Default: cyclic for pyadi, stream for gnuradio. pyadi supports cyclic only.")
    p.add_argument("--tone", action="store_true",
                   help="With --enable-rf: transmit a CW tone instead of a frame and check the "
                        "RTL-SDR sees it (first RF-chain test)")
    p.add_argument("--tone-offset-hz", type=float, default=100_000.0,
                   help="Tone offset from --freq (default 100 kHz, away from the RTL DC spike)")
    p.add_argument("--rx-only", action="store_true",
                   help="Receive-only RTL-SDR hardware check; the Pluto is not used")
    p.add_argument("--rx-file", default=None, help="Re-process a saved capture (.cu8/.cf32), no hardware")
    p.add_argument("--rx-rate-override", type=float, default=None)
    p.add_argument("--tx-rate-override", type=float, default=None)
    p.add_argument("--no-save", action="store_true", help="Offline mode: do not write a result file")
    return p


def main(argv=None, input_fn=input):
    args = build_parser().parse_args(argv)
    if sum(bool(x) for x in (args.enable_rf, args.rx_file, args.rx_only)) > 1:
        raise SystemExit("--enable-rf, --rx-only and --rx-file are mutually exclusive.")

    print("=" * 64)
    print("  PLUTO -> RTL-SDR LOOPBACK RUNNER")
    print("=" * 64)
    iq, meta, spec = load_waveform(args.waveform)
    print(f"  Waveform : {meta['iq_file_resolved']}")
    print(f"  Frame    : {frame_description(spec)}")
    print(f"  Payload  : {meta['payload_hex'][:32]}... ({meta['payload_bit_order']})")

    if args.rx_file:
        return run_offline(args, spec, meta)
    if args.rx_only:
        if subprocess.run(["which", "rtl_sdr"], capture_output=True).returncode != 0:
            raise SystemExit("rtl_sdr binary not found.")
        return run_rx_only(args, meta, spec)

    if args.freq is not None:
        lo, hi = occupied_band(args.freq, args.tx_rate / spec.sps, spec.rolloff)
        inside = SRD_BAND_HZ[0] <= lo and hi <= SRD_BAND_HZ[1]
        print(f"  Occupied : {lo / 1e6:.4f}-{hi / 1e6:.4f} MHz "
              f"({'inside' if inside else 'NOT inside'} 865-868 MHz)")

    if not args.enable_rf and args.tone:
        derived = validate_tone_configuration(args) if args.freq is not None else None
        if derived:
            print(f"  Tone     : {derived['tone_frequency_hz'] / 1e6:.6f} MHz, TX {derived['tx_rate_requested_hz']} S/s, "
                  f"RX {derived['rx_rate_expected_exact_hz']:.0f} S/s")
        print("  DRY RUN (tone): no hardware accessed, nothing transmitted.")
        return {"status": "dry_run_ok", "derived_configuration": derived}

    if not args.enable_rf:
        derived = None
        if args.freq is not None:
            derived = validate_configuration(args, meta, spec)   # same checks as the RF path
            print(f"  TX rate  : {derived['tx_rate_requested_hz']} S/s (waveform design "
                  f"{derived['waveform_design_rate_hz']:.0f}), symbol rate {derived['symbol_rate_baud']:.1f} Bd")
            print(f"  RX rate  : {derived['rx_rate_requested_hz']} S/s "
                  f"(exact {derived['rx_rate_expected_exact_hz']:.3f})")
            print(f"  Capture  : {derived['capture_duration_s'] * 1e3:.0f} ms = "
                  f"{derived['frames_in_capture']:.1f} frames")
        else:
            print("  (pass --freq to validate the full TX/RX configuration)")
        print("  DRY RUN: no hardware accessed, nothing transmitted.")
        return {"status": "dry_run_ok", "derived_configuration": derived}

    enforce_rf_path(args)                      # fails closed before touching hardware
    resolve_tx(args)
    if args.tone:
        validate_tone_configuration(args)
    else:
        validate_configuration(args, meta, spec)
    print("  Pre-flight:")
    if not check_devices(args.tx_backend):
        raise SystemExit("Required SDR software/hardware not available.")
    host = args.pluto_uri.split(":", 1)[1] if args.pluto_uri.startswith("ip:") else None
    if host and not check_pluto_connectivity(host):
        raise SystemExit("Pluto not reachable.")
    if args.tone:
        return run_tone_test(args, input_fn=input_fn)
    return run_physical(args, iq, meta, spec, input_fn=input_fn)


if __name__ == "__main__":
    main()
