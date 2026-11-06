from gnuradio import gr
import pmt
import numpy as np


class SNRModulationController(gr.sync_block):

    def __init__(self):
        gr.sync_block.__init__(
            self,
            name="SNR Modulation Controller",
            in_sig=[np.float32],
            out_sig=None
        )

        self.message_port_register_out(pmt.intern("modulation"))
        self.message_port_register_out(pmt.intern("enable"))

        self.current_index = None
        self.current_enabled = None

    def work(self, input_items, output_items):
        snr_values = input_items[0]

        for value in snr_values:
            snr_db = float(value)

            if snr_db >= 15:
                index = 2       # 16-QAM
            elif snr_db >= 8:
                index = 1       # QPSK
            elif snr_db >= 0:
                index = 0       # BPSK
            else:
                index = None    # Transmission disabled

            enabled = index is not None

            if enabled and index != self.current_index:
                self.message_port_pub(
                    pmt.intern("modulation"),
                    pmt.cons(pmt.PMT_NIL, pmt.from_long(index))
                )
                self.current_index = index

            if enabled != self.current_enabled:
                self.message_port_pub(
                    pmt.intern("enable"),
                    pmt.from_bool(enabled)
                )
                self.current_enabled = enabled

        return len(snr_values)
