"""Tests for scripts/verify_closed_loop_captures.py on a simulated session relabelled as real (no hardware)."""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import run_channel_switching_demo as demo  # noqa: E402
import verify_closed_loop_captures as vcl  # noqa: E402


def make_session(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "OUT_SIM", tmp_path / "sessions")
    a = demo.build_parser().parse_args(["--simulate", "--rounds-per-phase", "1", "--save-captures"])
    a.channels = [int(f) for f in a.channels]
    a.settle_s = 0.0
    out = demo.run_session(a)["out"]
    rec = json.loads((out / "session.json").read_text())
    rec["mode"] = "real_radios"
    (out / "session.json").write_text(json.dumps(rec))
    # simulated readback has no tx_lo/gain fields in the same form; give each sidecar a real-style readback
    for side in (out / "captures").glob("*.json"):
        d = json.loads(side.read_text())
        d["tx_readback"] = {"tx_lo_hz": d["rx_center_frequency_hz"], "tx_hardwaregain_db": -float(d["tx_attenuation_db"]),
                            "tx_sample_rate_hz": demo.TX_RATE}
        side.write_text(json.dumps(d))
    return out


def test_clean_session_verifies(tmp_path, monkeypatch):
    out = make_session(tmp_path, monkeypatch)
    r = vcl.verify_session(out, vcl.load_waveforms())
    assert r["ok"] and r["captures_checked"] == 5 * 4 and r["max_esn0_diff_db"] < 1e-9


def test_tampered_log_is_caught(tmp_path, monkeypatch):
    out = make_session(tmp_path, monkeypatch)
    with open(out / "rounds.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    rows[1]["data_bit_errors"] = str(int(float(rows[1]["data_bit_errors"])) + 5)   # wrong error count
    rows[2]["modulation"] = "BPSK" if rows[2]["modulation"] != "BPSK" else "QPSK"    # wrong decision
    with open(out / "rounds.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    side = out / "captures" / "r01_probe_ch1.json"
    d = json.loads(side.read_text())
    d["tx_readback"]["tx_hardwaregain_db"] = -3.0                                   # readback not matching
    side.write_text(json.dumps(d))
    r = vcl.verify_session(out, vcl.load_waveforms())
    assert not r["ok"]
    assert any(m["tag"].startswith("r02_data") for m in r["decode_mismatches"])
    assert [m["round"] for m in r["replay_mismatches"]] == ["3"]
    assert any("r01_probe_ch1" in p for p in r["readback_problems"])
