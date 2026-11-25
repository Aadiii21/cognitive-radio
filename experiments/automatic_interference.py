import sys

from PyQt5 import Qt
sys.path.insert(0, "/tmp/cognitive-radio-grcc")

from joint_cognitive_radio import joint_cognitive_radio


SCHEDULE = [
    ("Phase 1: Channel 2 strongest", (0.281, 0.126, 0.050)),
    ("Phase 2: Channel 0 strongest", (0.050, 0.281, 0.126)),
    ("Phase 3: Channel 1 strongest", (0.126, 0.050, 0.281)),
]

PHASE_DURATION_MS = 10_000
SETTLING_DURATION_MS = 2_000


def main():
    app = Qt.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    tb = joint_cognitive_radio()

    phase_timer = Qt.QTimer(app)
    phase_timer.setSingleShot(True)

    settling_timer = Qt.QTimer(app)
    settling_timer.setSingleShot(True)

    state = {"phase": 0}

    def mark_measurement_start(name):
        print(
            f"[EXPERIMENT] Measurement window started: {name}",
            flush=True,
        )

    def apply_phase():
        index = state["phase"]

        if index >= len(SCHEDULE):
            print("[EXPERIMENT] Schedule complete.", flush=True)
            phase_timer.stop()
            settling_timer.stop()
            tb.stop()
            tb.wait()
            tb.hide()
            app.quit()
            return

        name, amplitudes = SCHEDULE[index]
        a0, a1, a2 = amplitudes

        print(
            f"\n[EXPERIMENT] {name} | "
            f"Noise amplitudes=({a0}, {a1}, {a2})",
            flush=True,
        )

        tb.set_noise_amp(a0)
        tb.set_noise_amp_2(a1)
        tb.set_noise_amp_1(a2)

        print(
            f"[EXPERIMENT] Settling for "
            f"{SETTLING_DURATION_MS / 1000:.0f} seconds",
            flush=True,
        )

        settling_timer.timeout.connect(
            lambda phase_name=name: mark_measurement_start(phase_name)
        )
        settling_timer.start(SETTLING_DURATION_MS)

        state["phase"] += 1
        phase_timer.start(PHASE_DURATION_MS)

    phase_timer.timeout.connect(apply_phase)

    tb.start()
    tb.show()

    print("[EXPERIMENT] Flowgraph started.", flush=True)
    Qt.QTimer.singleShot(1000, apply_phase)

    try:
        app.exec_()
    except KeyboardInterrupt:
        print("[EXPERIMENT] Interrupted by user.", flush=True)
        phase_timer.stop()
        settling_timer.stop()
        tb.stop()
        tb.wait()


if __name__ == "__main__":
    main()
