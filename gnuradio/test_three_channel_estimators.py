#!/usr/bin/python3

import numpy as np

from gnuradio import gr, blocks


class ThreeChannelEstimatorTest(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "Three Channel SNR Estimator Test")

        self.sample_count = 200_000
        self.alpha = 0.001

        self.noise_levels = [0.10, 0.25, 0.50]
        self.expected_snr = [
            20 * np.log10((1 / np.sqrt(2)) / sigma)
            for sigma in self.noise_levels
        ]

        self.sources = []
        self.sinks = []

        rng = np.random.default_rng(42)

        pilot = np.cos(
            2 * np.pi * 1000 *
            np.arange(self.sample_count) / 100_000
        ).astype(np.float32)

        for channel, sigma in enumerate(self.noise_levels):

            noise = rng.normal(
                0.0, sigma, self.sample_count
            ).astype(np.float32)

            received = (pilot + noise).astype(np.float32)
            inverted_pilot = (-pilot).astype(np.float32)

            received_source = blocks.vector_source_f(
                received.tolist(), False
            )
            pilot_source = blocks.vector_source_f(
                pilot.tolist(), False
            )
            inverted_source = blocks.vector_source_f(
                inverted_pilot.tolist(), False
            )

            received_sink = blocks.vector_sink_f()
            pilot_sink = blocks.vector_sink_f()
            noise_sink = blocks.vector_sink_f()
            snr_sink = blocks.vector_sink_f()

            received_add = blocks.add_ff(1)
            pilot_rms = blocks.rms_ff(self.alpha)
            noise_rms = blocks.rms_ff(self.alpha)

            ratio = blocks.divide_ff(1)
            snr_db = blocks.nlog10_ff(20, 1, 0)

            self.connect(received_source, (received_add, 0))
            self.connect(inverted_source, (received_add, 1))

            # Pilot reference RMS
            self.connect(pilot_source, pilot_rms)

            # received_add already isolates the noise residual
            self.connect(received_add, noise_rms)

            # SNR = 20 log10(RMS pilot / RMS noise)
            self.connect(pilot_rms, (ratio, 0))
            self.connect(noise_rms, (ratio, 1))
            self.connect(ratio, snr_db)

            self.connect(received_source, received_sink)
            self.connect(pilot_rms, pilot_sink)
            self.connect(noise_rms, noise_sink)
            self.connect(snr_db, snr_sink)

            self.sources.append({
                "received": received_source,
                "pilot": pilot_source,
                "inverted": inverted_source,
            })

            self.sinks.append({
                "received": received_sink,
                "pilot": pilot_sink,
                "noise": noise_sink,
                "snr": snr_sink,
            })


def main():

    tb = ThreeChannelEstimatorTest()

    print("Running three independent SNR estimators...")
    tb.run()

    print("\n===== THREE-CHANNEL SNR RESULTS =====")

    for channel, sinks in enumerate(tb.sinks):

        snr_values = np.asarray(sinks["snr"].data())
        noise_values = np.asarray(sinks["noise"].data())
        pilot_values = np.asarray(sinks["pilot"].data())

        # Ignore initial RMS filter settling
        start = len(snr_values) // 2

        measured_snr = float(np.mean(snr_values[start:]))
        measured_noise = float(np.mean(noise_values[start:]))
        measured_pilot = float(np.mean(pilot_values[start:]))

        expected = tb.expected_snr[channel]

        print(f"\nChannel {channel}")
        print(f"  Expected SNR : {expected:.2f} dB")
        print(f"  Measured SNR : {measured_snr:.2f} dB")
        print(f"  Pilot RMS    : {measured_pilot:.4f}")
        print(f"  Noise RMS    : {measured_noise:.4f}")
        print(f"  Error        : {abs(measured_snr - expected):.2f} dB")

        assert abs(measured_snr - expected) < 1.0, (
            f"Channel {channel} SNR validation failed"
        )

    print("\nTHREE-CHANNEL ESTIMATOR TEST PASSED")


if __name__ == "__main__":
    main()
