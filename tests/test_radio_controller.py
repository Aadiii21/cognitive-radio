import unittest

from src.run_radio_controller import run_experiment


class TestRadioController(unittest.TestCase):

    def test_time_accounting(self):
        result = run_experiment(
            steps=500,
            seed=2026,
            switch_delay_steps=2,
        )

        self.assertEqual(
            result.transmission_steps + result.unavailable_steps,
            result.elapsed_steps,
        )

    def test_packet_accounting(self):
        result = run_experiment(
            steps=500,
            seed=2026,
            switch_delay_steps=2,
        )

        self.assertEqual(
            result.attempted_packets,
            result.transmission_steps,
        )

        self.assertLessEqual(
            result.successful_packets,
            result.attempted_packets,
        )

    def test_switching_cost(self):
        result = run_experiment(
            steps=500,
            seed=2026,
            switch_delay_steps=2,
        )

        self.assertEqual(
            result.unavailable_steps,
            result.channel_switches * 2,
        )

    def test_no_switching_has_full_availability(self):
        result = run_experiment(
            steps=500,
            seed=2026,
            volatility=0.5,
            burst_probability=0.03,
            switch_delay_steps=2,
        )

        self.assertEqual(result.channel_switches, 0)
        self.assertEqual(result.availability, 1.0)

    def test_zero_switching_delay(self):
        result = run_experiment(
            steps=500,
            seed=2026,
            switch_delay_steps=0,
        )

        self.assertEqual(result.unavailable_steps, 0)
        self.assertEqual(result.availability, 1.0)


if __name__ == "__main__":
    unittest.main()
