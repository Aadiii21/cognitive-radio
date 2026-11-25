import csv
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

RESULTS = Path("results")

with (RESULTS / "decision_trace.csv").open() as f:
    rows = list(csv.DictReader(f))

if len(rows) < 2:
    raise SystemExit("Insufficient decision trace data.")

# Extract data
timestamps = np.array([float(r["timestamp"]) for r in rows])
time = timestamps - timestamps[0]

snr = np.array([
    [
        float(r["snr_ch0_db"]),
        float(r["snr_ch1_db"]),
        float(r["snr_ch2_db"]),
    ]
    for r in rows
])

selected = np.array([int(r["channel"]) for r in rows])
best = np.argmax(snr, axis=1)

enabled = np.array([
    r["enabled"].lower() == "true" for r in rows
])

actions = [r["action"] for r in rows]

# Detect actual transitions in the strongest-SNR channel
phase_changes = np.where(best[1:] != best[:-1])[0] + 1

phase_boundaries = [0.0] + [
    float(time[i]) for i in phase_changes
] + [float(time[-1])]

phase_names = [
    "Phase 1: Channel 2 strongest",
    "Phase 2: Channel 0 strongest",
    "Phase 3: Channel 1 strongest",
]

phase_colors = ["#e8f1fb", "#fcebdc", "#e5f3e8"]

# Detect channel-switch decisions
handoff_indices = [
    i for i, action in enumerate(actions)
    if action == "switch_channel"
]

handoff_times = [float(time[i]) for i in handoff_indices]

# Figure configuration
plt.rcParams.update({
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 9,
    "figure.titlesize": 15,
})

fig, axes = plt.subplots(
    3, 1,
    figsize=(13, 9),
    sharex=True,
    gridspec_kw={"height_ratios": [1.3, 1, 0.8]},
)

# Shade phases consistently across all panels
for ax in axes:
    for i in range(min(3, len(phase_names))):
        start = phase_boundaries[i]
        end = phase_boundaries[i + 1]

        ax.axvspan(
            start, end,
            color=phase_colors[i],
            alpha=0.65,
            zorder=0,
        )

# Plot 1: SNR
ax = axes[0]

for i in range(3):
    ax.plot(
        time, snr[:, i],
        label=f"Channel {i}",
        linewidth=1.3,
    )

ax.set_ylabel("SNR (dB)")
ax.set_title("Measured Channel Signal-to-Noise Ratio", loc="left")
ax.set_ylim(6.5, 27.0)
ax.legend(
    ncol=3,
    loc="lower center",
    bbox_to_anchor=(0.5, 1.12),
)
ax.grid(True, alpha=0.25)

# Phase labels
for i, name in enumerate(phase_names):
    midpoint = (
        phase_boundaries[i] + phase_boundaries[i + 1]
    ) / 2

    ax.text(
       midpoint, 25.5,
        name,
        ha="center",
        va="center",
        fontsize=8,
        fontweight="bold",
    )

# Plot 2: Channel selection
ax = axes[1]

ax.step(
    time, selected,
    where="post",
    label="Controller-selected channel",
    linewidth=1.7,
)

ax.step(
    time, best,
    where="post",
    linestyle="--",
    label="Highest-SNR channel",
    linewidth=1.3,
)

ax.set_ylabel("Channel index")
ax.set_title("Channel Selection", loc="left")
ax.set_yticks([0, 1, 2])
ax.set_ylim(-0.3, 2.3)
ax.legend(loc="upper right")
ax.grid(True, alpha=0.25)

# Plot 3: Transmission state
ax = axes[2]

ax.step(
    time,
    enabled.astype(int),
    where="post",
    linewidth=1.7,
)

ax.set_ylabel("Transmission")
ax.set_xlabel("Elapsed time (seconds)")
ax.set_title("Effective Transmission State", loc="left")
ax.set_yticks([0, 1])
ax.set_yticklabels(["Disabled", "Enabled"])
ax.set_ylim(-0.2, 1.2)
ax.grid(True, alpha=0.25)

# Mark handoff events on every panel
for i, handoff_time in enumerate(handoff_times):
    for ax in axes:
        ax.axvline(
            handoff_time,
            color="#b22222",
            linestyle=":",
            linewidth=1.2,
            alpha=0.85,
        )

    handoff_labels = [
        "Initial handoff",
        "Handoff 1",
        "Handoff 2",
    ]

    axes[2].annotate(
        handoff_labels[i],
        xy=(handoff_time, 0.05),
        xytext=(4, 9),
        textcoords="offset points",
        color="#b22222",
        fontsize=8,
        fontweight="bold",
    )

fig.suptitle(
    "Software-in-the-Loop Cognitive Radio Experiment",
    fontweight="bold",
    y=0.99,
)

fig.text(
    0.5, 0.01,
    "Shaded regions indicate measured interference phases. "
    "Dotted red lines indicate channel-switch decisions.",
    ha="center",
    fontsize=8,
)

fig.tight_layout(rect=[0.02, 0.04, 0.99, 0.96])

png_path = RESULTS / "cognitive_radio_experiment_final.png"
pdf_path = RESULTS / "cognitive_radio_experiment_final.pdf"

fig.savefig(png_path, dpi=300, bbox_inches="tight")
fig.savefig(pdf_path, bbox_inches="tight")

print(f"Saved: {png_path}")
print(f"Saved: {pdf_path}")
print(f"Detected phase transitions: {len(phase_changes)}")
print(f"Detected handoff decisions: {len(handoff_times)}")

plt.show()
