#!/usr/bin/env python3
"""Closed-loop channel-switching demo on real radios: Pluto TX -> air -> RTL-SDR RX.

Every round:
  1. SENSE   the Pluto sends a short BPSK probe frame on each of three channels in
             turn; the RTL-SDR retunes, captures it and the multimod receiver
             measures Es/N0 on that channel.
  2. DECIDE  the original CalibratedCognitiveController (unchanged) picks the
             channel and modulation from the three measurements.
  3. SEND    the Pluto sends a data frame in the chosen modulation on the chosen
             channel; the RTL-SDR captures it and the receiver measures BER.

Channel quality is scripted: each channel's TX attenuation follows a phase
schedule (default: a different channel is best in each phase, then all are
mediocre, then all are poor). Sensing, decisions, retuning, transmission and reception are real
over the air; only the "interference" is emulated by TX power, and the
results say so.

  # 1. software only (no hardware), to see what a session looks like
  python scripts/run_channel_switching_demo.py --simulate

  # 2. on real radios (antennas on both, D = separation in metres)
  python scripts/run_channel_switching_demo.py --enable-rf --rf-path ota --antenna-separation-m D

  # 3. the same with a 2 dB safety margin in the controller's decisions
  python scripts/run_channel_switching_demo.py --enable-rf --rf-path ota --antenna-separation-m D --margin-db 2

Safety gates (same as scripts/run_hardware_experiment.py): --enable-rf, a declared
RF path, every channel's occupied band inside 865-868 MHz, the operator types
TRANSMIT once for the session, the TX LO must not be powered down, and every
transmission's LO / gain / rate is read back and checked before capturing. The
transmitter is always stopped, also on errors or Ctrl-C.

Outputs (one folder per session):
  results/hardware/closed_loop/<session>/          real radios
  results/hardware/closed_loop_simulated/<session>/ --simulate
    rounds.csv     one row per round: per-channel Es/N0, decision, data BER
    session.json   configuration, schedule, readbacks, summary
    session.png    Es/N0 per channel, chosen channel, modulation and BER per round
    captures/      raw .cu8 + .json sidecar for every probe and data capture
                   (simulated sessions keep only the .json unless --save-captures)
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_hardware_experiment as hx  # noqa: E402
from src.calibrated_controller import CalibratedCognitiveController  # noqa: E402
from src.radio import pluto_tx_adapter  # noqa: E402
from src.radio.hardware_config import PLUTO_URI, RTL_DEFAULT_SAMPLE_RATE  # noqa: E402

WAVEFORM_DIR = ROOT / "results" / "baseband" / "multimod_v2"
WAVEFORMS = {"BPSK": "bpsk_framed_seed42.json", "QPSK": "qpsk_framed_seed42.json",
             "16-QAM": "16qam_framed_seed42.json"}
PROBE_MODULATION = "BPSK"
DEFAULT_CHANNELS_HZ = [865_700_000, 866_500_000, 867_300_000]
# Pluto TX attenuation (dB) per channel, per phase. From the 23 Nov OTA sweep: 0 dB -> ~22 dB Es/N0
# (16-QAM), 10 dB -> ~11 dB (QPSK), 20 dB -> ~4.5 dB (BPSK / unusable).
DEFAULT_SCHEDULE = [
    {"name": "A: channel 0 best", "attenuation_db": [0, 10, 20]},
    {"name": "B: channel 1 best", "attenuation_db": [20, 0, 10]},
    {"name": "C: channel 2 best", "attenuation_db": [10, 20, 0]},
    {"name": "D: all mediocre", "attenuation_db": [10, 15, 20]},
    # Added after the first real session (28 Nov), whose best channel never fell below the QPSK cut-off:
    # here every channel is poor, so the best one lands in the BPSK range (~4-8.8 dB Es/N0).
    {"name": "E: all poor", "attenuation_db": [15, 20, 20]},
]
SPS = 4
SNR_FLOOR_DB, SNR_CEIL_DB = -5.0, 30.0      # controller input range (channel model / calibration range)
ESN0_TO_CAL_SNR_DB = 10 * np.log10(SPS)      # calibration SNR is per sample at 4 SPS: Es/N0 - 6.02 dB
TX_RATE = 2_083_333.0
OUT_REAL = ROOT / "results" / "hardware" / "closed_loop"
OUT_SIM = ROOT / "results" / "hardware" / "closed_loop_simulated"


def esn0_to_controller_snr(esn0_db, margin_db=0.0):
    """Receiver Es/N0 (dB) -> the controller's calibration SNR (dB), clipped to its valid range.

    margin_db: safety margin; the controller sees the link margin_db worse than measured
    (same definition as margin_db in scripts/sensitivity_analysis.py)."""
    if esn0_db is None or not np.isfinite(esn0_db):
        return SNR_FLOOR_DB
    return float(np.clip(esn0_db - ESN0_TO_CAL_SNR_DB - margin_db, SNR_FLOOR_DB, SNR_CEIL_DB))


# ============================================================ simulated radios (--simulate)
class SimulatedAir:
    """Stand-in for Pluto + air + RTL-SDR. Es/N0 = base - slope * attenuation (fit to the 23 Nov sweep)."""

    def __init__(self, seed=1, base_esn0_db=22.0, slope=0.9, cfo_hz=-10_600.0, rms_lsb=12.0):
        self.rng = np.random.default_rng(seed)
        self.base, self.slope, self.cfo, self.rms = base_esn0_db, slope, cfo_hz, rms_lsb
        self.current = None    # (frequency, attenuation, iq)

    def esn0_for(self, attenuation_db):
        return self.base - self.slope * attenuation_db

    def capture(self, frequency_hz, rx_rate, gain_db, n_samples, discard_samples, device_index=0):
        from scipy.signal import resample_poly
        freq, att, iq = self.current
        assert freq == frequency_hz, "simulated RX tuned to a different frequency than TX"
        active = np.abs(iq) > 1e-9
        p_active = float(np.mean(np.abs(iq[active]) ** 2))
        n_tx = int(np.ceil((n_samples + 4096) * TX_RATE / rx_rate)) + len(iq)
        start = int(self.rng.integers(0, len(iq)))
        x = np.tile(iq, n_tx // len(iq) + 2)[start:start + n_tx] / np.sqrt(p_active)
        n = np.arange(len(x))
        x = x * np.exp(1j * (2 * np.pi * self.cfo * n / TX_RATE + self.rng.uniform(0, 2 * np.pi)))
        sigma2 = SPS / 10 ** (self.esn0_for(att) / 10)
        x = x + np.sqrt(sigma2 / 2) * (self.rng.standard_normal(len(x)) + 1j * self.rng.standard_normal(len(x)))
        y = resample_poly(x, 1565, 1592)[:n_samples]
        scale = self.rms / np.sqrt(np.mean(np.abs(y) ** 2))
        i = np.clip(np.round(y.real * scale + 127.5), 0, 255)
        q = np.clip(np.round(y.imag * scale + 127.5), 0, 255)
        raw = np.empty(2 * len(y), np.uint8)
        raw[0::2], raw[1::2] = i, q
        return raw, {"actual_sample_rate_hz": float(rx_rate), "actual_sample_rate_source": "simulated",
                     "requested_sample_rate_hz": int(rx_rate), "returncode": 0}

    def make_tx_class(self):
        air = self

        class SimTX:
            def __init__(self, uri, sample_rate, bandwidth, amplitude_scale, cyclic=True):
                self.rate = sample_rate

            def configure(self, frequency, attenuation):
                self.freq, self.att = frequency, attenuation

            def prepare(self, iq, amplitude_scale=None):
                self.iq = np.asarray(iq)

            def start(self):
                if not pluto_tx_adapter.RF_ENABLED:
                    raise RuntimeError("RF not enabled")
                air.current = (self.freq, self.att, self.iq)
                return {"backend": "simulated"}

            def stop(self):
                air.current = None
                return {}

            def readback(self):
                return {"tx_lo_hz": float(self.freq), "tx_hardwaregain_db": -float(self.att),
                        "tx_sample_rate_hz": float(self.rate), "uri": "simulated"}

        return SimTX


# ============================================================ hardware helpers
def read_lo_powerdown(uri, run=subprocess.run):
    """True if the Pluto TX LO is powered down (it would then transmit nothing although readback passes)."""
    try:
        out = run(["iio_attr", "-u", uri, "-o", "-c", "ad9361-phy", "altvoltage1", "powerdown"],
                  capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        raise hx.TransmitConfigError(
            f"The Pluto at {uri} is not responding (iio_attr timed out). Check `ping -c 3 192.168.2.1`; "
            "if it fails, re-plug the Pluto's USB cable and wait about 30 s.")
    if getattr(out, "returncode", 0) not in (0, None) and not (out.stdout or "").strip():
        raise hx.TransmitConfigError(f"Could not read the Pluto TX LO state at {uri}: "
                                     f"{(getattr(out, 'stderr', '') or '').strip() or 'no output'}")
    val = (out.stdout or "").strip().splitlines()[-1:] or [""]
    return val[0].strip() == "1"


class _Args:
    """Minimal namespace for hx.verify_tx_readback."""

    def __init__(self, freq, attenuation, tx_rate):
        self.freq, self.attenuation, self.tx_rate = freq, attenuation, tx_rate


def _rf(on):
    """Set the RF-enable flag without the per-call console banner (printed once per session instead)."""
    pluto_tx_adapter.RF_ENABLED = bool(on)


# ============================================================ one transmission + capture
def transmit_and_capture(ctx, freq, attenuation, modulation, tag):
    """Start TX, verify readback, capture, stop TX (always). Returns (receiver dict, capture record)."""
    iq, meta, spec = ctx["waveforms"][modulation]
    ctx["burst_t0"] = time.time()
    tx = None
    readback = raw = cap_info = None
    error = None
    try:
        tx = ctx["tx_cls"](uri=ctx["uri"], sample_rate=int(round(TX_RATE)), bandwidth=ctx["tx_bandwidth"],
                           amplitude_scale=ctx["amplitude_scale"], cyclic=True)
        tx.configure(int(freq), float(attenuation))
        tx.prepare(iq, ctx["amplitude_scale"])
        _rf(True)
        tx.start()
        time.sleep(ctx["settle_s"])
        readback = tx.readback() if ctx["simulate"] else ctx["readback_fn"](ctx["uri"])
        problems = hx.verify_tx_readback(readback, _Args(freq, attenuation, TX_RATE), spec)
        if problems:
            raise RuntimeError("TX readback verification failed: " + "; ".join(problems))
        raw, cap_info = ctx["capture_fn"](int(freq), ctx["rx_rate"], ctx["rx_gain"], ctx["capture_samples"],
                                          ctx["discard_samples"], ctx["rtl_device"])
    except BaseException as e:
        error = f"{type(e).__name__}: {e}"
        if not isinstance(e, Exception):
            raise
    finally:
        try:
            if tx is not None:
                tx.stop()
        finally:
            _rf(False)
    if error:
        raise RuntimeError(f"{tag} at {freq / 1e6:.3f} MHz, att {attenuation} dB: {error}")

    cap_dir = ctx["out"] / "captures"
    cap_dir.mkdir(parents=True, exist_ok=True)
    cap_path = cap_dir / f"{tag}.cu8"
    if ctx["save_captures"]:
        raw.tofile(cap_path)
    rx_rate_used = cap_info["actual_sample_rate_hz"]
    tx_rate_used = readback["tx_sample_rate_hz"]
    sidecar = {
        "data_kind": hx.SIMULATED_CAPTURE_KIND if ctx["simulate"] else hx.RX_CAPTURE_KIND,
        "content": ("SIMULATED received samples" if ctx["simulate"] else
                    "RTL-SDR received samples (raw uint8 interleaved I/Q). NOT transmit data."),
        "experiment": "closed_loop_channel_switching", "tag": tag,
        "rx_center_frequency_hz": int(freq), "rx_sample_rate_hz": rx_rate_used, "rx_gain_db": ctx["rx_gain"],
        "rf_path": ctx["rf_path"], "tx_attenuation_db": attenuation, "tx_readback": readback,
        "tx_sample_rate_hz": tx_rate_used, "waveform_metadata": str(WAVEFORM_DIR / WAVEFORMS[modulation]),
        "waveform_payload_hex": meta["payload_hex"], "samples": int(len(raw) // 2),
        "clipping_fraction": hx.clipping_fraction(raw), "capture": cap_info,
        "timestamp": datetime.now().isoformat(),
    }
    cap_path.with_suffix(".json").write_text(json.dumps(sidecar, indent=2, default=str))
    _, d = hx.process_capture(hx.unpack_rtl_u8(raw), spec, tx_rate_used, rx_rate_used, 0.6)
    if ctx.get("verbose", True):
        fs = frame_stats(d)
        es = "no frame" if fs["esn0_db"] is None else f"Es/N0 {fs['esn0_db']:.1f} dB"
        print(f"    {tag:24s} {freq / 1e6:.1f} MHz, att {attenuation:>4} dB: {es}  "
              f"({time.time() - ctx['burst_t0']:.1f} s)", flush=True)
    return d, {"file": cap_path.name, "clipping_fraction": sidecar["clipping_fraction"], "readback": readback}


def frame_stats(d):
    frames = d.get("frames") or []
    if not frames:
        return {"frames": 0, "esn0_db": None, "bit_errors": None, "bits": None, "ber": None}
    esn0 = 10 * np.log10(np.mean([10 ** (f["snr_db"] / 10) for f in frames]))
    errs = int(d.get("total_payload_bit_errors") or 0)
    bits = int(d.get("total_payload_bits_compared") or 0)
    return {"frames": len(frames), "esn0_db": round(float(esn0), 2), "bit_errors": errs, "bits": bits,
            "ber": errs / bits if bits else None}


# ============================================================ session
def build_schedule(args):
    if args.schedule:
        sched = json.loads(Path(args.schedule).read_text())
    else:
        sched = DEFAULT_SCHEDULE
    for ph in sched:
        if len(ph["attenuation_db"]) != len(args.channels):
            raise hx.TransmitConfigError(f"Schedule phase {ph['name']!r} needs {len(args.channels)} attenuations.")
        for a in ph["attenuation_db"]:
            if not 0 <= float(a) <= 89.75:
                raise hx.TransmitConfigError(f"Attenuation {a} dB outside the Pluto range 0-89.75 dB.")
    return sched


def preflight(args, waveforms):
    """All checks that need no hardware. Raises TransmitConfigError (fail closed)."""
    if len(set(args.channels)) != len(args.channels) or len(args.channels) < 2:
        raise hx.TransmitConfigError("Give at least two distinct channel frequencies.")
    bands = []
    _, _, spec = waveforms[PROBE_MODULATION]
    for f in args.channels:
        lo, hi = hx.enforce_band(f, TX_RATE, spec)
        bands.append((lo, hi))
    for (l1, h1), (l2, h2) in zip(sorted(bands), sorted(bands)[1:]):
        if l2 < h1:
            raise hx.TransmitConfigError(f"Channels overlap: {h1 / 1e6:.4f} MHz > {l2 / 1e6:.4f} MHz.")
    if not 0 < args.amplitude_scale <= 0.25:
        raise hx.TransmitConfigError("--amplitude-scale must be in (0, 0.25].")
    if not args.simulate:
        if not args.enable_rf and not getattr(args, "dry_run", False):
            raise hx.TransmitConfigError("Real radios need --enable-rf (or use --simulate / --dry-run).")
        return hx.enforce_rf_path(args), bands
    return {"type": "simulated"}, bands


def run_session(args, input_fn=input, tx_cls=None, capture_fn=None, readback_fn=None, lo_check=None):
    waveforms = {m: hx.load_waveform(WAVEFORM_DIR / f) for m, f in WAVEFORMS.items()}
    for m, (_, meta, _) in waveforms.items():
        if abs(float(meta["sample_rate_sps"]) - TX_RATE) > 1.0:
            raise hx.TransmitConfigError(f"{m} waveform rate {meta['sample_rate_sps']} != {TX_RATE}")
    rf_path, bands = preflight(args, waveforms)
    schedule = build_schedule(args)
    rounds_total = len(schedule) * args.rounds_per_phase

    air = None
    if getattr(args, "dry_run", False):
        pass
    elif args.simulate:
        air = SimulatedAir(seed=args.seed)
        tx_cls, capture_fn = air.make_tx_class(), air.capture
    else:
        if not hx.check_devices("pyadi"):
            raise hx.TransmitConfigError("Pre-flight failed (pyadi-iio / rtl_sdr / iio_attr missing).")
        from src.radio.pluto_pyadi_tx import PlutoPyadiTX
        tx_cls = tx_cls or PlutoPyadiTX
        capture_fn = capture_fn or hx.capture_rtl
        readback_fn = readback_fn or pluto_tx_adapter.read_pluto_tx_state
        if (lo_check or read_lo_powerdown)(args.pluto_uri):
            raise hx.TransmitConfigError(
                "The Pluto TX LO is powered down, so nothing would be transmitted although readback would "
                "pass. Run: iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 0")

    summary = [
        f"Channels: " + ", ".join(f"{f / 1e6:.3f} MHz ({lo / 1e6:.3f}-{hi / 1e6:.3f})"
                                  for f, (lo, hi) in zip(args.channels, bands)) + " - all inside 865-868 MHz",
        f"{len(schedule)} phases x {args.rounds_per_phase} rounds = {rounds_total} rounds; each round = "
        f"{len(args.channels)} probes + 1 data burst = {rounds_total * (len(args.channels) + 1)} bursts, "
        f"about {rounds_total * (len(args.channels) + 1) * 2.5 / 60:.1f} min on real radios "
        f"(~2.4 s per burst on 28 Nov)",
        "Schedule (Pluto TX attenuation per channel, dB): " +
        "; ".join(f"{p['name']} {p['attenuation_db']}" for p in schedule),
        f"Pluto {args.pluto_uri}, amplitude scale {args.amplitude_scale}, cyclic TX (pyadi), "
        f"stopped after every burst",
        f"RTL-SDR {args.rx_rate} S/s, gain {args.rx_gain} dB, {args.capture_samples} samples per capture",
        f"Controller: CalibratedCognitiveController, switch penalty {args.switch_penalty}, "
        f"min utility gain {args.min_utility_gain}, safety margin {args.margin_db} dB",
        hx.describe_rf_path(rf_path) if rf_path["type"] != "simulated" else "SIMULATED: no hardware used",
    ]
    if getattr(args, "dry_run", False):
        print("\n  DRY RUN (nothing transmitted, no hardware accessed). The session would be:")
        for line in summary:
            print(f"    {line}")
        return {"out": None, "rows": [], "summary": summarize([], schedule, args.channels), "error": None,
                "dry_run": True}
    if not args.simulate:
        if not hx.operator_confirmation(summary, input_fn, rf_path["type"]):
            print("  ABORTED: operator confirmation not given. Nothing transmitted.")
            return None
    else:
        print("\n  SIMULATION (no hardware):")
        for line in summary:
            print(f"    {line}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = (OUT_SIM if args.simulate else OUT_REAL) / f"session_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    ctx = {"waveforms": waveforms, "tx_cls": tx_cls, "capture_fn": capture_fn, "readback_fn": readback_fn,
           "uri": args.pluto_uri, "amplitude_scale": args.amplitude_scale, "settle_s": args.settle_s,
           "rx_rate": args.rx_rate, "rx_gain": args.rx_gain, "capture_samples": args.capture_samples,
           "discard_samples": args.discard_samples, "rtl_device": args.rtl_device, "simulate": args.simulate,
           "verbose": not args.simulate, "burst_t0": time.time(),
           "rf_path": rf_path, "out": out, "tx_bandwidth": int(args.tx_bandwidth), "save_captures": (not args.simulate) or args.save_captures}
    controller = CalibratedCognitiveController(initial_channel=0, switch_delay_steps=2,
                                               switch_penalty=args.switch_penalty,
                                               min_utility_gain=args.min_utility_gain)
    rows, error = [], None
    t0 = time.time()
    if not args.simulate:
        print("\n  RF TRANSMISSION: ENABLED for this session (each burst is started, verified and stopped)")
    try:
        r = 0
        for p, phase in enumerate(schedule):
            for _ in range(args.rounds_per_phase):
                r += 1
                atts = phase["attenuation_db"]
                probes = []
                for c, f in enumerate(args.channels):
                    d, cap = transmit_and_capture(ctx, f, atts[c], PROBE_MODULATION, f"r{r:02d}_probe_ch{c}")
                    probes.append({**frame_stats(d), "clipping": cap["clipping_fraction"]})
                snrs = [esn0_to_controller_snr(pr["esn0_db"], args.margin_db) for pr in probes]
                decision = controller.decide(snrs)
                ch, mod = decision.channel, decision.modulation
                d, cap = transmit_and_capture(ctx, args.channels[ch], atts[ch], mod, f"r{r:02d}_data_ch{ch}_{mod}")
                data = frame_stats(d)
                row = {"round": r, "phase": phase["name"], "time_s": round(time.time() - t0, 1)}
                for c, pr in enumerate(probes):
                    row[f"att_ch{c}_db"] = atts[c]
                    row[f"esn0_ch{c}_db"] = pr["esn0_db"]
                    row[f"frames_ch{c}"] = pr["frames"]
                row.update({"controller_snr_db": ";".join(f"{s:.2f}" for s in snrs),
                            "action": decision.action, "channel": ch,
                            "frequency_mhz": args.channels[ch] / 1e6, "modulation": mod,
                            "expected_utility": round(float(decision.expected_utility), 4),
                            "data_frames": data["frames"], "data_esn0_db": data["esn0_db"],
                            "data_bit_errors": data["bit_errors"], "data_bits": data["bits"],
                            "data_ber": data["ber"], "data_clipping": cap["clipping_fraction"]})
                rows.append(row)
                es = " ".join(f"{pr['esn0_db'] if pr['esn0_db'] is not None else '--':>6}" for pr in probes)
                ber = "no frame" if data["ber"] is None else f"{data['bit_errors']}/{data['bits']}"
                print(f"  round {r:2d} [{phase['name']}] Es/N0 per channel: {es} dB -> "
                      f"{decision.action:14s} ch{ch} {mod:6s} data Es/N0 {data['esn0_db']} dB, errors {ber}")
    except KeyboardInterrupt:
        error = "interrupted by operator"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    finally:
        pluto_tx_adapter.set_rf_enabled(False)   # prints the RF DISABLED banner once

    if rows:
        with open(out / "rounds.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        plot_session(rows, args.channels, out / "session.png", simulated=args.simulate)
    summary_rec = summarize(rows, schedule, args.channels)
    (out / "session.json").write_text(json.dumps({
        "timestamp": stamp, "mode": "simulated" if args.simulate else "real_radios",
        "channel_quality": "scripted by Pluto TX attenuation per channel (emulated interference)",
        "rf_path": rf_path, "channels_hz": args.channels, "occupied_bands_hz": bands, "schedule": schedule,
        "rounds_per_phase": args.rounds_per_phase, "controller": {
            "class": "CalibratedCognitiveController", "switch_penalty": args.switch_penalty,
            "min_utility_gain": args.min_utility_gain, "switch_delay_steps": 2,
            "margin_db": args.margin_db,
            "input": "receiver Es/N0 - 6.02 dB - margin_db, clipped to [-5, 30] dB"},
        "pluto_uri": args.pluto_uri, "amplitude_scale": args.amplitude_scale, "rx_rate": args.rx_rate,
        "rx_gain_db": args.rx_gain, "capture_samples": args.capture_samples, "error": error,
        "summary": summary_rec}, indent=2, default=str))
    print(f"\n  {len(rows)} of {rounds_total} rounds done in {time.time() - t0:.0f} s"
          + (f"; STOPPED: {error}" if error else ""))
    print(f"  Switches: {summary_rec['switches']}, picked the best channel in "
          f"{summary_rec['best_channel_rounds']}/{len(rows)} rounds, data BER {summary_rec['data_ber']}")
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"  Results: {shown}/ (rounds.csv, session.json, session.png, captures/)")
    return {"out": out, "rows": rows, "summary": summary_rec, "error": error}


def summarize(rows, schedule, channels):
    if not rows:
        return {"rounds": 0, "switches": 0, "best_channel_rounds": 0, "data_ber": None}
    best_ok = 0
    for r in rows:
        es = [r[f"esn0_ch{c}_db"] if r[f"esn0_ch{c}_db"] is not None else -99 for c in range(len(channels))]
        best_ok += int(r["channel"] == int(np.argmax(es)))
    errs = sum(r["data_bit_errors"] or 0 for r in rows)
    bits = sum(r["data_bits"] or 0 for r in rows)
    mods = {}
    for r in rows:
        mods[r["modulation"]] = mods.get(r["modulation"], 0) + 1
    return {"rounds": len(rows), "switches": sum(r["action"] == "switch_channel" for r in rows),
            "best_channel_rounds": best_ok, "data_bit_errors": errs, "data_bits": bits,
            "data_ber": (errs / bits) if bits else None, "modulation_rounds": mods,
            "rounds_without_data_frame": sum(1 for r in rows if not r["data_frames"])}


def plot_session(rows, channels, path, simulated=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rr = [r["round"] for r in rows]
    colors = ["#2F5D8A", "#2E7D57", "#B8621B", "#7A3E9D"]
    fig, axes = plt.subplots(3, 1, figsize=(8.5, 7.2), sharex=True,
                             gridspec_kw={"height_ratios": [2.2, 1, 1.2]})
    ax = axes[0]
    for c, f in enumerate(channels):
        y = [r[f"esn0_ch{c}_db"] if r[f"esn0_ch{c}_db"] is not None else np.nan for r in rows]
        ax.plot(rr, y, "o-", color=colors[c % 4], ms=4, label=f"ch{c} {f / 1e6:.1f} MHz")
    for th, lab in ((6.8, "BPSK"), (9.9, "QPSK"), (16.7, "16-QAM")):
        ax.axhline(th, color="#999", ls=":", lw=0.8)
        ax.text(rr[-1] + 0.3, th, f"{lab} 1e-3", fontsize=7, va="center", color="#666")
    ax.set_ylabel("Probe Es/N0 (dB)")
    h, l = ax.get_legend_handles_labels()
    fig.legend(h, l, fontsize=8, ncol=len(channels), loc="upper center", bbox_to_anchor=(0.5, 0.935), frameon=False)
    ax.grid(alpha=0.3)
    phases, starts = [], []
    for r in rows:
        if not phases or phases[-1] != r["phase"]:
            phases.append(r["phase"])
            starts.append(r["round"])
    for a in axes:
        for s in starts[1:]:
            a.axvline(s - 0.5, color="#bbb", lw=0.8)
    for s, ph in zip(starts, phases):
        ax.text(s - 0.4, ax.get_ylim()[1], ph.split(":")[0], fontsize=8, va="bottom")
    ax = axes[1]
    ax.step(rr, [r["channel"] for r in rows], where="mid", color="black")
    sw = [r["round"] for r in rows if r["action"] == "switch_channel"]
    ax.scatter(sw, [next(x["channel"] for x in rows if x["round"] == s) for s in sw], color="#C0392B", zorder=3,
               s=30, label="switch")
    ax.set_yticks(range(len(channels)), [f"ch{c}" for c in range(len(channels))])
    ax.set_ylabel("Chosen channel")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.3)
    ax = axes[2]
    levels = {"BPSK": 1, "QPSK": 2, "16-QAM": 4}
    ax.bar(rr, [levels[r["modulation"]] for r in rows], color=[colors[r["channel"] % 4] for r in rows])
    for r in rows:
        txt = "no frame" if r["data_ber"] is None else f"{r['data_bit_errors']}/{r['data_bits']}"
        ax.text(r["round"], levels[r["modulation"]] + 0.1, txt, fontsize=6, ha="center", rotation=90, va="bottom")
    ax.set_yticks([1, 2, 4], ["BPSK", "QPSK", "16-QAM"])
    ax.set_ylim(0, 6.2)
    ax.set_ylabel("Modulation\n(bit errors)")
    ax.set_xlabel("Round")
    ax.grid(alpha=0.3, axis="y")
    title = ("SIMULATED session (no hardware)" if simulated else
             "Closed-loop channel switching on real radios (Pluto -> air -> RTL-SDR)")
    fig.suptitle(title + "\nchannel quality scripted by Pluto TX power", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=180)
    plt.close(fig)


def build_parser():
    p = argparse.ArgumentParser(description="Closed-loop channel-switching demo (Pluto -> RTL-SDR).")
    p.add_argument("--simulate", action="store_true", help="no hardware: simulated air and radios")
    p.add_argument("--dry-run", action="store_true", help="run every check and show the plan; no hardware access")
    p.add_argument("--enable-rf", action="store_true")
    p.add_argument("--rf-path", choices=["conducted", "ota"], default=None)
    p.add_argument("--antenna-separation-m", type=float, default=None)
    p.add_argument("--attenuator-db", type=float, default=None)
    p.add_argument("--channels", type=float, nargs="+", default=DEFAULT_CHANNELS_HZ, help="centre frequencies, Hz")
    p.add_argument("--schedule", default=None, help="JSON file: [{name, attenuation_db: [...]}, ...]")
    p.add_argument("--rounds-per-phase", type=int, default=3)
    p.add_argument("--switch-penalty", type=float, default=0.15)
    p.add_argument("--min-utility-gain", type=float, default=0.10)
    p.add_argument("--margin-db", type=float, default=0.0,
                   help="safety margin: the controller sees each channel this many dB worse than measured")
    p.add_argument("--pluto-uri", default=PLUTO_URI)
    p.add_argument("--amplitude-scale", type=float, default=0.1)
    p.add_argument("--tx-bandwidth", type=int, default=1_000_000, help="Pluto TX RF bandwidth, Hz")
    p.add_argument("--rx-rate", type=float, default=RTL_DEFAULT_SAMPLE_RATE)
    p.add_argument("--rx-gain", type=float, default=28.0)
    p.add_argument("--rtl-device", type=int, default=0)
    p.add_argument("--capture-samples", type=int, default=524_288)
    p.add_argument("--discard-samples", type=int, default=262_144)
    p.add_argument("--settle-s", type=float, default=0.5)
    p.add_argument("--seed", type=int, default=1, help="--simulate only")
    p.add_argument("--save-captures", action="store_true",
                   help="--simulate only: also save the simulated raw captures (real runs always save them)")
    return p


def main(argv=None, input_fn=input):
    try:
        sys.stdout.reconfigure(line_buffering=True)   # show progress at once, also through `| tee`
    except (AttributeError, ValueError):
        pass
    a = build_parser().parse_args(argv)
    a.channels = [int(f) for f in a.channels]
    if not 0.0 <= a.margin_db <= 10.0:
        print("  NOT TRANSMITTING: --margin-db must be between 0 and 10 dB.")
        return 2
    if a.simulate:
        a.settle_s = 0.0
    try:
        res = run_session(a, input_fn=input_fn)
    except hx.TransmitConfigError as e:
        print(f"  NOT TRANSMITTING: {e}")
        return 2
    return 0 if res and not res["error"] else 1


if __name__ == "__main__":
    sys.exit(main())
