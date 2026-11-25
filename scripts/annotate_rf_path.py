#!/usr/bin/env python3
"""Record the ACTUAL RF path for runs whose JSON says something else.

Adds an `rf_path_correction` block to result JSONs and capture sidecars whose
timestamp (from the file name, YYYYMMDD_HHMMSS) falls in [--from, --to].
The original `rf_path` field is left untouched, so the record keeps both what
the runner was told and what was actually wired. Prints every file it changes.

    python scripts/annotate_rf_path.py --from 20261123_135000 --to 20261123_140100 \
        --actual ota --note "antennas on Pluto and RTL-SDR; no cable, no attenuator"
"""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = re.compile(r"(\d{8}_\d{6})")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--from", dest="start", required=True, help="YYYYMMDD_HHMMSS (inclusive)")
    p.add_argument("--to", dest="end", required=True, help="YYYYMMDD_HHMMSS (inclusive)")
    p.add_argument("--actual", required=True, choices=["ota", "conducted"])
    p.add_argument("--antenna-separation-m", type=float, default=None)
    p.add_argument("--note", default="")
    p.add_argument("--dir", default=str(ROOT / "results" / "hardware"))
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)

    fix = {"actual_type": a.actual, "note": a.note,
           "annotated_at": datetime.now().isoformat(timespec="seconds"),
           "reason": "runner was run with a different --rf-path than the physical setup"}
    if a.antenna_separation_m is not None:
        fix["antenna_separation_m"] = a.antenna_separation_m
    changed = 0
    for f in sorted(Path(a.dir).rglob("*.json")):
        m = STAMP.search(f.name)
        if not m or not (a.start <= m.group(1) <= a.end):
            continue
        try:
            rec = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            print(f"  skip (unreadable): {f}")
            continue
        if not isinstance(rec, dict):
            continue
        rec["rf_path_correction"] = fix
        if not a.dry_run:
            f.write_text(json.dumps(rec, indent=2, default=str))
        changed += 1
        print(f"  {'would annotate' if a.dry_run else 'annotated'}: {f.relative_to(ROOT) if f.is_relative_to(ROOT) else f}")
    print(f"{changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
