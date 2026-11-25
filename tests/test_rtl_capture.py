import sys
import unittest
from unittest.mock import patch

from src.radio.rtl_capture import CaptureResult, capture_exact
from src.radio.rtl_sdr_sensor import RTLSDRSensor


class TestRTLExactCapture(unittest.TestCase):

    def test_capture_reads_exact_requested_bytes_and_stops_child(self):
        producer = (
            "import signal,sys\n"
            "signal.signal(signal.SIGINT, lambda *_: sys.exit(0))\n"
            "chunk=bytes(range(256))*256\n"
            "while True:\n"
            " sys.stdout.buffer.write(chunk)\n"
            " sys.stdout.buffer.flush()\n"
        )

        capture = capture_exact(
            [sys.executable, "-u", "-c", producer],
            expected_bytes=100_000,
            timeout_s=2.0,
        )

        self.assertEqual(len(capture.data), 100_000)
        self.assertEqual(capture.data[:256], bytes(range(256)))
        self.assertEqual(capture.returncode, 0)

    def test_capture_times_out_when_child_produces_no_data(self):
        with self.assertRaises(TimeoutError):
            capture_exact(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                expected_bytes=16,
                timeout_s=0.1,
            )

    def test_rtl_sensor_reads_exact_count_without_unbounded_sample_option(self):
        sensor = RTLSDRSensor(
            center_frequencies=[98_100_000],
            sample_rate=256_000,
            bandwidth=20_000,
            capture_samples=1024,
        )
        result = CaptureResult(
            data=bytes([128, 128] * 1024),
            stderr="",
            returncode=0,
        )

        with patch(
            "src.radio.rtl_sdr_sensor.capture_exact",
            return_value=result,
        ) as capture:
            iq = sensor._capture_iq(98_100_000)

        command = capture.call_args.args[0]
        self.assertEqual(command[-1], "-")
        self.assertNotIn("-n", command)
        self.assertEqual(capture.call_args.kwargs["expected_bytes"], 2048)
        self.assertEqual(len(iq), 1024)


if __name__ == "__main__":
    unittest.main()
