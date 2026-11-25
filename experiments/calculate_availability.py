import csv
from pathlib import Path

path = Path("results/decision_trace.csv")

with path.open() as f:
    rows = list(csv.DictReader(f))

if len(rows) < 2:
    raise SystemExit("Insufficient decision records.")

timestamps = [float(r["timestamp"]) for r in rows]
enabled = [r["enabled"].lower() == "true" for r in rows]

total_time = 0.0
enabled_time = 0.0
disabled_time = 0.0

intervals = []

for i in range(len(rows) - 1):
    dt = timestamps[i + 1] - timestamps[i]

    if dt <= 0:
        raise ValueError(f"Invalid timestamp interval at row {i + 1}")

    intervals.append(dt)
    total_time += dt

    if enabled[i]:
        enabled_time += dt
    else:
        disabled_time += dt

availability = 100 * enabled_time / total_time

print("TRANSMISSION AVAILABILITY")
print("=" * 42)
print(f"Decision records:       {len(rows)}")
print(f"Observation duration:   {total_time:.3f} seconds")
print(f"Enabled duration:       {enabled_time:.3f} seconds")
print(f"Disabled duration:      {disabled_time:.3f} seconds")
print(f"Availability:           {availability:.3f}%")
print(f"Downtime:               {100 - availability:.3f}%")
print()
print("TIMING")
print("-" * 42)
print(f"Mean decision interval: {sum(intervals)/len(intervals):.4f} s")
print(f"Minimum interval:       {min(intervals):.6f} s")
print(f"Maximum interval:       {max(intervals):.6f} s")
print()
print("HANDOFFS")
print("-" * 42)

switches = sum(r["action"] == "switch_channel" for r in rows)
print(f"Channel switch decisions: {switches}")

disabled_intervals = sum(not x for x in enabled[:-1])
print(f"Disabled intervals:       {disabled_intervals}")
