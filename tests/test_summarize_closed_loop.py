"""Tests for scripts/summarize_closed_loop.py, on simulated sessions relabelled as real (no hardware)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import run_channel_switching_demo as demo  # noqa: E402
import summarize_closed_loop as scl  # noqa: E402


def make_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "OUT_SIM", tmp_path / "sessions")
    outs = []
    for i, margin in enumerate(["0", "0", "2"]):
        a = demo.build_parser().parse_args(["--simulate", "--rounds-per-phase", "2", "--seed", str(i + 1),
                                            "--margin-db", margin])
        a.channels = [int(f) for f in a.channels]
        a.settle_s = 0.0
        res = demo.run_session(a)
        # unique folder names (sessions in the same second would collide)
        new = res["out"].with_name(f"session_{i}")
        res["out"].rename(new)
        rec = json.loads((new / "session.json").read_text())
        rec["mode"], rec["timestamp"] = "real_radios", f"s{i}"
        (new / "session.json").write_text(json.dumps(rec))
        outs.append(new)
    # an aborted session and a simulated one are skipped
    bad = tmp_path / "sessions" / "session_9"
    bad.mkdir()
    (bad / "session.json").write_text(json.dumps({"mode": "real_radios", "error": "interrupted by operator"}))
    return outs


def test_summary(tmp_path, monkeypatch, capsys):
    make_sessions(tmp_path, monkeypatch)
    assert scl.main(["--sessions", str(tmp_path / "sessions"), "--out-dir", str(tmp_path / "out")]) == 0
    s = json.loads((tmp_path / "out" / "analysis" / "closed_loop_summary.json").read_text())
    assert s["sessions_counted"] == 3 and len(s["skipped"]) == 1
    m0 = s["by_margin"]["margin_0_db"]
    assert m0["rounds"] == 20 and m0["best_channel_rounds"] == 20
    assert m0["switches_needed"] == 6 and m0["switches_made_when_needed"] == 6 and m0["unnecessary_switches"] == 0
    assert set(m0["per_modulation"]) == {"BPSK", "QPSK", "16-QAM"}
    lo, hi = m0["best_channel_ci95"]
    assert hi == 1.0 and 0.8 < lo < 0.9
    assert "margin_2_db" in s["by_margin"]
    assert (tmp_path / "out" / "figures" / "closed_loop_repeatability.png").exists()
    assert "skipped session_9" in capsys.readouterr().out


def test_unnecessary_and_late_switch_counted():
    rec = {"channels_hz": [1, 2, 3], "rounds_per_phase": 2, "timestamp": "x",
           "controller": {"switch_penalty": 0.15},
           "schedule": [{"name": "A", "attenuation_db": [0, 10, 20]}, {"name": "B", "attenuation_db": [20, 0, 10]}]}

    def row(ch, act):
        return {"channel": str(ch), "action": act, "modulation": "QPSK", "data_bit_errors": "0", "data_bits": "2048",
                "data_esn0_db": "12", "esn0_ch0_db": "1", "esn0_ch1_db": "2", "esn0_ch2_db": "0"}
    # phase A: a pointless switch to ch2; phase B: switch to ch1 one round late
    rows = [row(0, "stay"), row(2, "switch_channel"), row(2, "stay"), row(1, "switch_channel")]
    s = scl.analyse_session(rec, rows)
    assert s["switches"] == 2 and s["switches_needed"] == 1 and s["switches_made_when_needed"] == 1
    assert s["max_switch_latency_rounds"] == 1 and s["unnecessary_switches"] == 1
