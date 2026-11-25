import csv
from collections import Counter
from pathlib import Path

results = Path("results")

with (results / "decision_trace.csv").open() as f:
    trace = list(csv.DictReader(f))

with (results / "automatic_interference_events.csv").open() as f:
    events = list(csv.DictReader(f))

timestamps = [float(r["timestamp"]) for r in trace]
enabled = [r["enabled"].lower() == "true" for r in trace]

total_time = sum(
    timestamps[i + 1] - timestamps[i]
    for i in range(len(trace) - 1)
)

enabled_time = sum(
    (timestamps[i + 1] - timestamps[i])
    for i in range(len(trace) - 1)
    if enabled[i]
)

availability = 100 * enabled_time / total_time

switches = [
    i for i, row in enumerate(events)
    if row["action"] == "switch_channel"
]

successful_handoffs = sum(
    any(
        later["selected_channel"] == events[i]["selected_channel"]
        and later["enabled"] == "True"
        and later["handoff_remaining"] == "0"
        for later in events[i + 1:]
    )
    for i in switches
)

phase_targets = {
    "Phase 1: Channel 2 strongest": 2,
    "Phase 2: Channel 0 strongest": 0,
    "Phase 3: Channel 1 strongest": 1,
}

phase_results = {}
for phase, target in phase_targets.items():
    phase_events = [e for e in events if e["phase"] == phase]
    if phase_events:
        selected = int(phase_events[-1]["selected_channel"])
        phase_results[phase] = selected == target

modulations = Counter(e["modulation"] for e in events)

metrics = [
    ("Decision records", len(trace)),
    ("Controller transition events", len(events)),
    ("Observation duration (s)", round(total_time, 4)),
    ("Enabled duration (s)", round(enabled_time, 4)),
    ("Disabled duration (s)", round(total_time - enabled_time, 4)),
    ("Transmission availability (%)", round(availability, 3)),
    ("Channel switches", len(switches)),
    ("Successful handoffs", successful_handoffs),
    ("Handoff completion (%)",
     round(100 * successful_handoffs / len(switches), 3)
     if switches else 0),
    ("Channel selection accuracy (%)",
     round(100 * sum(phase_results.values()) / len(phase_results), 3)
     if phase_results else 0),
]

for modulation, count in sorted(modulations.items()):
    metrics.append((f"{modulation} event count", count))
    metrics.append((
        f"{modulation} event share (%)",
        round(100 * count / len(events), 3)
    ))

with (results / "final_experiment_metrics.csv").open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["metric", "value"])
    writer.writerows(metrics)

print("FINAL EXPERIMENT METRICS")
print("=" * 42)
for name, value in metrics:
    print(f"{name}: {value}")

print("\nSaved: results/final_experiment_metrics.csv")
