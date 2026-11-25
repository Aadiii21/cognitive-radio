import os
import selectors
import signal
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CaptureResult:
    data: bytes
    stderr: str
    returncode: int


def _stop_process(process):
    if process.poll() is not None:
        return

    try:
        process.send_signal(signal.SIGINT)
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def capture_exact(command: Sequence[str], expected_bytes: int, timeout_s=15.0):
    """Read an exact byte count from a streaming subprocess, then stop it."""
    if not command:
        raise ValueError("Command cannot be empty.")
    if expected_bytes <= 0:
        raise ValueError("expected_bytes must be positive.")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive.")

    process = subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

    if process.stdout is None:
        _stop_process(process)
        raise RuntimeError("Capture process stdout was not created.")

    stdout = process.stdout
    selector = selectors.DefaultSelector()
    selector.register(stdout, selectors.EVENT_READ)
    payload = bytearray()
    deadline = time.monotonic() + timeout_s

    try:
        while len(payload) < expected_bytes:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TimeoutError(
                    f"Capture timed out after {timeout_s:.1f}s; "
                    f"received {len(payload)} of {expected_bytes} bytes."
                )

            chunk = os.read(
                stdout.fileno(),
                min(65536, expected_bytes - len(payload)),
            )

            if not chunk:
                raise RuntimeError(
                    f"Capture process closed stdout after "
                    f"{len(payload)} of {expected_bytes} bytes."
                )

            payload.extend(chunk)
    except BaseException:
        selector.close()
        _stop_process(process)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
        raise

    selector.close()
    _stop_process(process)

    stderr = ""
    if process.stderr:
        stderr = process.stderr.read().decode(errors="replace")
        process.stderr.close()

    stdout.close()
    return CaptureResult(
        data=bytes(payload),
        stderr=stderr,
        returncode=process.returncode,
    )
