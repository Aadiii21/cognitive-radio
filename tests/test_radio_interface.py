import unittest

from src.radio import (
    RadioInterface,
    ChannelMeasurement,
    PacketResult,
    SimulatedRadio,
)


class TestSimulatedRadio(unittest.TestCase):

    def setUp(self):
        self.radio = SimulatedRadio(seed=2026)

    def tearDown(self):
        if not self.radio.closed:
            self.radio.close()

    def test_interface_implementation(self):
        self.assertIsInstance(self.radio, RadioInterface)

    def test_channel_measurements(self):
        measurements = self.radio.measure_channels()

        self.assertEqual(len(measurements), 3)
        self.assertTrue(
            all(isinstance(m, ChannelMeasurement) for m in measurements)
        )

        self.assertEqual(
            [m.channel_index for m in measurements],
            [0, 1, 2],
        )

        self.assertTrue(
            all(m.source == "simulation" for m in measurements)
        )

    def test_channel_selection(self):
        self.radio.measure_channels()
        self.radio.set_channel(2)

        self.assertEqual(self.radio.current_channel, 2)

    def test_modulation_selection(self):
        self.radio.set_modulation("16-QAM")

        self.assertEqual(self.radio.current_modulation, "16-QAM")

    def test_packet_transmission(self):
        self.radio.measure_channels()
        self.radio.set_channel(0)
        self.radio.set_modulation("QPSK")

        result = self.radio.transmit_packet(b"test-packet")

        self.assertIsInstance(result, PacketResult)
        self.assertEqual(result.packet_bytes, 11)
        self.assertIn(result.channel_index, range(3))
        self.assertIn(result.modulation, self.radio.MODULATIONS)
        self.assertTrue(0 <= result.success_probability <= 1)

        if result.success:
            self.assertEqual(result.delivered_bytes, 11)
        else:
            self.assertEqual(result.delivered_bytes, 0)

    def test_transmission_requires_measurement(self):
        with self.assertRaises(RuntimeError):
            self.radio.transmit_packet(b"test")

    def test_invalid_channel(self):
        with self.assertRaises(ValueError):
            self.radio.set_channel(10)

    def test_invalid_modulation(self):
        with self.assertRaises(ValueError):
            self.radio.set_modulation("256-QAM")

    def test_closed_radio(self):
        self.radio.close()

        with self.assertRaises(RuntimeError):
            self.radio.measure_channels()


if __name__ == "__main__":
    unittest.main()
