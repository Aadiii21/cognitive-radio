import csv
import re
from pathlib import Path
from collections import defaultdict

LOG = Path("results/automatic_interference.log")
CSV_OUT = Path("results/automatic_interference_events.csv")
SUMMARY_OUT = Path("results/automatic_interference_summary.txt")

phase_pattern = re.compile(
    r"\[EXPERIMENT\] Phase (\d+): (.*?) \| "
    r"Noise amplitudes=\(([^)]+)\)"
)

joint_pattern = re.compile(
    r"\[JOINT\] SNR=\(([^)]+)\) \| "
    r"Channel=(\d+) \| "
    r"Modulation=(.*?) \| "
    r"Enabled=(True|False) \| "
    r"Action=(.*?) \| "
    r"HandoffRemaining=(\d+)"
)

if not LOG.exists():
    raise FileNotFoundError(f"Log not found: {LOG}")

events = []
phases = []
current_phase = "Phase 1: Channel 2 strongest"

for line in LOG.read_text(errors="replace").splitlines():

    phase_match = phase_pattern.search(line)

    if phase_match:
        phase_number, description, amplitudes = phase_match.groups()

        current_phase = f"Phase {phase_number}: {description}"
        phases.append({
            "phase": current_phase,
            "amplitudes": amplitudes,
        })
        continue

    joint_match = joint_pattern.search(line)

    if joint_match:
        snrs, channel, modulation, enabled, action, remaining = (
            joint_match.groups()
        )

        snr_values = [float(x.strip()) for x in snrs.split(",")]

        if len(snr_values) != 3:
            continue

        events.append({
            "event": len(events) + 1,
            "phase": current_phase,
            "snr_ch0_db": snr_values[0],
            "snr_ch1_db": snr_values[1],
            "snr_ch2_db": snr_values[2],
            "selected_channel": int(channel),
            "modulation": modulation,
            "enabled": enabled,
            "action": action,
            "handoff_remaining": int(remaining),
        })

fields = [
    "event",
    "phase",
    "snr_ch0_db",
    "snr_ch1_db",
    "snr_ch2_db",
    "selected_channel",
    "modulation",
    "enabled",
    "action",
    "handoff_remaining",
]

with CSV_OUT.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(events)

phase_events = defaultdict(list)

for event in events:
    phase_events[event["phase"]].append(event)

switches = sum(e["action"] == "switch_channel" for e in events)
disabled = sum(e["enabled"] == "False" for e in events)
enabled = sum(e["enabled"] == "True" for e in events)

with SUMMARY_OUT.open("w") as f:
    f.write("AUTOMATIC INTERFERENCE EXPERIMENT SUMMARY\n")
    f.write("=" * 48 + "\n\n")

    f.write(f"Controller events: {len(events)}\n")
    f.write(f"Phase changes: {len(phases)}\n")
    f.write(f"Channel switches: {switches}\n")
    f.write(f"Transmission-enabled events: {enabled}\n")
    f.write(f"Transmission-disabled events: {disabled}\n\n")

    f.write("PHASE DETAILS\n")
    f.write("-" * 48 + "\n")

    for phase, phase_rows in phase_events.items():
        f.write(f"\n{phase}\n")

        for event in phase_rows:
            f.write(
                f"  Event {event['event']}: "
                f"SNR=({event['snr_ch0_db']:.2f}, "
                f"{event['snr_ch1_db']:.2f}, "
                f"{event['snr_ch2_db']:.2f}) dB | "
                f"Channel={event['selected_channel']} | "
                f"{event['modulation']} | "
                f"Enabled={event['enabled']} | "
                f"Action={event['action']} | "
                f"Handoff={event['handoff_remaining']}\n"
            )

print(f"Parsed controller events: {len(events)}")
print(f"Detected experiment phases: {len(phases)}")
print(f"Channel switches: {switches}")
print(f"Transmission enabled: {enabled}")
print(f"Transmission disabled: {disabled}")
print(f"\nCSV: {CSV_OUT}")
print(f"Summary: {SUMMARY_OUT}")
