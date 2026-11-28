"""Tests for scripts/scan_band.py (no hardware)."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import scan_band  # noqa: E402


def fake_rtl_power(path, sweeps=20, busy_channel=1, busy_every=4, seed=0):
    """Write an rtl_power-style CSV: 2 hops per sweep, flat floor, ch busy_channel active every busy_every sweeps."""
    rng = np.random.default_rng(seed)
    lines = []
    hops = [(864_500_000, 866_500_000), (866_500_000, 868_500_000)]
    step = 2000.0
    for s in range(sweeps):
        t = f"07:30:{s:02d}"
        for lo, hi in hops:
            f = lo + (np.arange(int((hi - lo) / step)) + 0.5) * step
            p = -40 + rng.normal(0, 0.5, len(f))
            if s % busy_every == 0:
                c = scan_band.CHANNELS_HZ[busy_channel]
                p[np.abs(f - c) < 300_000] += 15
            lines.append(", ".join(["2026-11-28", t, str(lo), str(hi), f"{step}", "10"] + [f"{x:.2f}" for x in p]))
    lines.append("2026-11-28, 07:31:00, 864500000, 866500000, 2000.0, 10, -40, -40")  # incomplete last sweep
    Path(path).write_text("\n".join(lines) + "\n")


def test_parse_and_stats(tmp_path):
    fake_rtl_power(tmp_path / "rtl_power.csv")
    f, p, t = scan_band.parse_rtl_power(tmp_path / "rtl_power.csv")
    assert p.shape == (20, 2000) and len(t) == 20 and np.all(np.diff(f) > 0)
    floor, st = scan_band.channel_stats(f, p)
    assert abs(floor + 40) < 0.2
    assert st[1]["busy_fraction"] == 0.25 and st[0]["busy_fraction"] == 0 and st[2]["busy_fraction"] == 0
    assert st[1]["above_floor_db"] > 3 and abs(st[0]["above_floor_db"]) < 0.5


def test_replot_existing_csv(tmp_path):
    fake_rtl_power(tmp_path / "rtl_power.csv")
    assert scan_band.main(["--input", str(tmp_path / "rtl_power.csv")]) == 0
    rec = json.loads((tmp_path / "summary.json").read_text())
    assert rec["sweeps"] == 20 and len(rec["channels"]) == 3 and (tmp_path / "scan.png").exists()


def test_refuses_when_pluto_lo_on(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(scan_band, "OUT", tmp_path)
    calls = []
    assert scan_band.main(["--minutes", "1"], run=lambda cmd: calls.append(cmd), lo_check=lambda uri: False) == 2
    assert not calls and "LO is ON" in capsys.readouterr().out


def test_scan_command_and_unreachable_pluto(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_band, "OUT", tmp_path)
    seen = {}

    def run(cmd):
        seen["cmd"] = cmd
        fake_rtl_power(cmd[-1])

        class R:
            returncode = 0
        return R()
    assert scan_band.main(["--minutes", "2"], run=run, lo_check=lambda uri: None) == 0
    c = seen["cmd"]
    assert c[0] == "rtl_power" and c[c.index("-f") + 1] == "864500000:868500000:2000"
    assert c[c.index("-e") + 1] == "120" and c[c.index("-g") + 1] == "28"
