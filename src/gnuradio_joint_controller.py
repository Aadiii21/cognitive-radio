

from gnuradio import gr
import pmt
import numpy as np

from src.gnuradio_adapter import GNUradioAdapter


class JointCognitiveController(gr.sync_block):

    def __init__(self):
        gr.sync_block.__init__(
            self,
            name="Joint Cognitive Controller",
            in_sig=[
                np.float32,
                np.float32,
                np.float32,
            ],
            out_sig=None,
        )

        self.adapter = GNUradioAdapter()

        # 32,000 samples/sec / 3,200 = 10 decisions/sec
        self.decision_interval = 3200
        self.sample_counter = 0

        # Handoff delay in decision intervals
        self.handoff_delay_steps = (
            self.adapter.controller.switch_delay_steps
        )
        self.handoff_remaining = 0

        # Message outputs
        self.message_port_register_out(pmt.intern("channel"))
        self.message_port_register_out(pmt.intern("modulation"))
        self.message_port_register_out(pmt.intern("enable"))

        # Previous published state
        self.current_channel = None
        self.current_modulation = None
        self.current_enabled = None

    def work(self, input_items, output_items):

        snr_channels = input_items

        for snr_values in zip(*snr_channels):

            self.sample_counter += 1

            if self.sample_counter < self.decision_interval:
                continue

            self.sample_counter = 0

            # Obtain cost-aware controller decision
            command = self.adapter.process(snr_values)

            # Apply actual handoff interruption
            if command.action == "switch_channel":
                self.handoff_remaining = max(
                    0, self.handoff_delay_steps - 1
                )
                effective_enabled = False

            elif self.handoff_remaining > 0:
                effective_enabled = False
                self.handoff_remaining -= 1

            else:
                effective_enabled = command.enabled

            # Do not transmit if the selected channel is unusable
            effective_enabled = (
                effective_enabled and command.enabled
            )

            state = (
                command.channel,
                command.modulation_index,
                effective_enabled,
            )

            previous = (
                self.current_channel,
                self.current_modulation,
                self.current_enabled,
            )

            if state != previous:
                print(
                    f"[JOINT] "
                    f"SNR={tuple(round(float(x), 2) for x in snr_values)} "
                    f"| Channel={command.channel} "
                    f"| Modulation={command.modulation} "
                    f"| Enabled={effective_enabled} "
                    f"| Action={command.action} "
                    f"| HandoffRemaining={self.handoff_remaining}",
                    flush=True,
                )

            # Publish channel selection immediately
            if command.channel != self.current_channel:
                self.message_port_pub(
                    pmt.intern("channel"),
                    pmt.cons(
                        pmt.PMT_NIL,
                        pmt.from_long(command.channel),
                    ),
                )
                self.current_channel = command.channel

            # Publish modulation selection
            if command.modulation_index != self.current_modulation:
                self.message_port_pub(
                    pmt.intern("modulation"),
                    pmt.cons(
                        pmt.PMT_NIL,
                        pmt.from_long(command.modulation_index),
                    ),
                )
                self.current_modulation = command.modulation_index

            # Publish effective transmission state
            if effective_enabled != self.current_enabled:
                self.message_port_pub(
                    pmt.intern("enable"),
                    pmt.from_bool(effective_enabled),
                )
                self.current_enabled = effective_enabled

        return len(input_items[0])
