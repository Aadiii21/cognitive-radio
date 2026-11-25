import csv
from collections import Counter, defaultdict
from pathlib import Path

path = Path("results/automatic_interference_events.csv")

with path.open() as f:
    events = list(csv.DictReader(f))

phases = defaultdict(list)

for event in events:
    phases[event["phase"]].append(event)

expected_channels = {
    "Phase 1: Channel 2 strongest": 2,
    "Phase 2: Channel 0 strongest": 0,
    "Phase 3: Channel 1 strongest": 1,
}

correct = 0
total = 0

for phase, rows in phases.items():
    if phase not in expected_channels:
        continue

    expected = expected_channels[phase]
    final_channel = int(rows[-1]["selected_channel"])

    total += 1
    correct += final_channel == expected

switches = [
    i for i, event in enumerate(events)
    if event["action"] == "switch_channel"
]

successful_handoffs = 0

for i in switches:
    channel = events[i]["selected_channel"]

    if any(
        later["selected_channel"] == channel
        and later["enabled"] == "True"
        and later["handoff_remaining"] == "0"
        for later in events[i + 1:]
    ):
        successful_handoffs += 1

modulations = Counter(e["modulation"] for e in events)

print("COGNITIVE RADIO PERFORMANCE")
print("=" * 40)

print(f"Channel selection accuracy: {correct}/{total} "
      f"({100 * correct / total:.1f}%)" if total else "No phases found")

print(f"Handoffs completed: {successful_handoffs}/{len(switches)}")

print("\nModulation distribution:")
for modulation, count in modulations.items():
    print(f"  {modulation}: {count}/{len(events)} "
          f"({100 * count / len(events):.1f}%)")

print("\nTransmission availability:")
print("  Not calculated: event timestamps are not available.")
