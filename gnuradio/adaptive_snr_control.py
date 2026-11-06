#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Not titled yet
# Author: deamon
# GNU Radio version: 3.10.12.0

from PyQt5 import Qt
from gnuradio import qtgui
from PyQt5 import QtCore
from gnuradio import analog
from gnuradio import blocks
import numpy
from gnuradio import blocks, gr
from gnuradio import digital
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from PyQt5 import Qt
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import sip
sys.path.insert(0, '/home/deamon/projects/cognitive-radio')
from src.gnuradio_controller import SNRModulationController
sys.path.insert(0, '/home/deamon/projects/cognitive-radio')
from src.gnuradio_joint_controller import JointCognitiveController
import threading



class adaptive_snr_control(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "Not titled yet", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("Not titled yet")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except BaseException as exc:
            print(f"Qt GUI: Could not set Icon: {str(exc)}", file=sys.stderr)
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("gnuradio/flowgraphs", "adaptive_snr_control")

        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {str(exc)}", file=sys.stderr)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.samp_rate_0 = samp_rate_0 = 32000
        self.samp_rate = samp_rate = 32000
        self.noise_amp = noise_amp = 0.05
        self.const_qpsk = const_qpsk = digital.constellation_qpsk().base()
        self.const_qpsk.set_npwr(1.0)
        self.const_bpsk = const_bpsk = digital.constellation_bpsk().base()
        self.const_bpsk.set_npwr(1.0)
        self.const_16qam = const_16qam = digital.constellation_16qam().base()
        self.const_16qam.set_npwr(1.0)

        ##################################################
        # Blocks
        ##################################################

        self._noise_amp_range = qtgui.Range(0.05, 1.0, 0.05, 0.05, 200)
        self._noise_amp_win = qtgui.RangeWidget(self._noise_amp_range, self.set_noise_amp, "Channel Noise Amplitude", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._noise_amp_win)
        self.snr_modulation_controller_0 = SNRModulationController()
        self.qtgui_number_sink_0_0_1_3 = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1,
            None # parent
        )
        self.qtgui_number_sink_0_0_1_3.set_update_time(0.10)
        self.qtgui_number_sink_0_0_1_3.set_title("Above 8db")

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        units = ['', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.qtgui_number_sink_0_0_1_3.set_min(i, -1)
            self.qtgui_number_sink_0_0_1_3.set_max(i, 1)
            self.qtgui_number_sink_0_0_1_3.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.qtgui_number_sink_0_0_1_3.set_label(i, "Data {0}".format(i))
            else:
                self.qtgui_number_sink_0_0_1_3.set_label(i, labels[i])
            self.qtgui_number_sink_0_0_1_3.set_unit(i, units[i])
            self.qtgui_number_sink_0_0_1_3.set_factor(i, factor[i])

        self.qtgui_number_sink_0_0_1_3.enable_autoscale(False)
        self._qtgui_number_sink_0_0_1_3_win = sip.wrapinstance(self.qtgui_number_sink_0_0_1_3.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_number_sink_0_0_1_3_win)
        self.qtgui_number_sink_0_0_1_2_0 = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1,
            None # parent
        )
        self.qtgui_number_sink_0_0_1_2_0.set_update_time(0.10)
        self.qtgui_number_sink_0_0_1_2_0.set_title("Above 15db")

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        units = ['', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.qtgui_number_sink_0_0_1_2_0.set_min(i, -1)
            self.qtgui_number_sink_0_0_1_2_0.set_max(i, 1)
            self.qtgui_number_sink_0_0_1_2_0.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.qtgui_number_sink_0_0_1_2_0.set_label(i, "Data {0}".format(i))
            else:
                self.qtgui_number_sink_0_0_1_2_0.set_label(i, labels[i])
            self.qtgui_number_sink_0_0_1_2_0.set_unit(i, units[i])
            self.qtgui_number_sink_0_0_1_2_0.set_factor(i, factor[i])

        self.qtgui_number_sink_0_0_1_2_0.enable_autoscale(False)
        self._qtgui_number_sink_0_0_1_2_0_win = sip.wrapinstance(self.qtgui_number_sink_0_0_1_2_0.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_number_sink_0_0_1_2_0_win)
        self.qtgui_number_sink_0_0_1_2 = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1,
            None # parent
        )
        self.qtgui_number_sink_0_0_1_2.set_update_time(0.10)
        self.qtgui_number_sink_0_0_1_2.set_title("Above 15db")

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        units = ['', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.qtgui_number_sink_0_0_1_2.set_min(i, -1)
            self.qtgui_number_sink_0_0_1_2.set_max(i, 1)
            self.qtgui_number_sink_0_0_1_2.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.qtgui_number_sink_0_0_1_2.set_label(i, "Data {0}".format(i))
            else:
                self.qtgui_number_sink_0_0_1_2.set_label(i, labels[i])
            self.qtgui_number_sink_0_0_1_2.set_unit(i, units[i])
            self.qtgui_number_sink_0_0_1_2.set_factor(i, factor[i])

        self.qtgui_number_sink_0_0_1_2.enable_autoscale(False)
        self._qtgui_number_sink_0_0_1_2_win = sip.wrapinstance(self.qtgui_number_sink_0_0_1_2.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_number_sink_0_0_1_2_win)
        self.qtgui_number_sink_0_0_1_1 = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1,
            None # parent
        )
        self.qtgui_number_sink_0_0_1_1.set_update_time(0.10)
        self.qtgui_number_sink_0_0_1_1.set_title("Above 0 db")

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        units = ['', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.qtgui_number_sink_0_0_1_1.set_min(i, -1)
            self.qtgui_number_sink_0_0_1_1.set_max(i, 1)
            self.qtgui_number_sink_0_0_1_1.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.qtgui_number_sink_0_0_1_1.set_label(i, "Data {0}".format(i))
            else:
                self.qtgui_number_sink_0_0_1_1.set_label(i, labels[i])
            self.qtgui_number_sink_0_0_1_1.set_unit(i, units[i])
            self.qtgui_number_sink_0_0_1_1.set_factor(i, factor[i])

        self.qtgui_number_sink_0_0_1_1.enable_autoscale(False)
        self._qtgui_number_sink_0_0_1_1_win = sip.wrapinstance(self.qtgui_number_sink_0_0_1_1.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_number_sink_0_0_1_1_win)
        self.qtgui_number_sink_0_0_0_0 = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1,
            None # parent
        )
        self.qtgui_number_sink_0_0_0_0.set_update_time(0.10)
        self.qtgui_number_sink_0_0_0_0.set_title("RMS Residual Noise")

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        units = ['', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.qtgui_number_sink_0_0_0_0.set_min(i, -1)
            self.qtgui_number_sink_0_0_0_0.set_max(i, 1)
            self.qtgui_number_sink_0_0_0_0.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.qtgui_number_sink_0_0_0_0.set_label(i, "Data {0}".format(i))
            else:
                self.qtgui_number_sink_0_0_0_0.set_label(i, labels[i])
            self.qtgui_number_sink_0_0_0_0.set_unit(i, units[i])
            self.qtgui_number_sink_0_0_0_0.set_factor(i, factor[i])

        self.qtgui_number_sink_0_0_0_0.enable_autoscale(False)
        self._qtgui_number_sink_0_0_0_0_win = sip.wrapinstance(self.qtgui_number_sink_0_0_0_0.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_number_sink_0_0_0_0_win)
        self.qtgui_number_sink_0_0_0 = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1,
            None # parent
        )
        self.qtgui_number_sink_0_0_0.set_update_time(0.10)
        self.qtgui_number_sink_0_0_0.set_title("RMS Reference Signal")

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        units = ['', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.qtgui_number_sink_0_0_0.set_min(i, -1)
            self.qtgui_number_sink_0_0_0.set_max(i, 1)
            self.qtgui_number_sink_0_0_0.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.qtgui_number_sink_0_0_0.set_label(i, "Data {0}".format(i))
            else:
                self.qtgui_number_sink_0_0_0.set_label(i, labels[i])
            self.qtgui_number_sink_0_0_0.set_unit(i, units[i])
            self.qtgui_number_sink_0_0_0.set_factor(i, factor[i])

        self.qtgui_number_sink_0_0_0.enable_autoscale(False)
        self._qtgui_number_sink_0_0_0_win = sip.wrapinstance(self.qtgui_number_sink_0_0_0.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_number_sink_0_0_0_win)
        self.qtgui_number_sink_0 = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1,
            None # parent
        )
        self.qtgui_number_sink_0.set_update_time(0.10)
        self.qtgui_number_sink_0.set_title("")

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        units = ['', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.qtgui_number_sink_0.set_min(i, -1)
            self.qtgui_number_sink_0.set_max(i, 1)
            self.qtgui_number_sink_0.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.qtgui_number_sink_0.set_label(i, "Data {0}".format(i))
            else:
                self.qtgui_number_sink_0.set_label(i, labels[i])
            self.qtgui_number_sink_0.set_unit(i, units[i])
            self.qtgui_number_sink_0.set_factor(i, factor[i])

        self.qtgui_number_sink_0.enable_autoscale(False)
        self._qtgui_number_sink_0_win = sip.wrapinstance(self.qtgui_number_sink_0.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_number_sink_0_win)
        self.qtgui_const_sink_x_0 = qtgui.const_sink_c(
            1024, #size
            "", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_const_sink_x_0.set_update_time(0.10)
        self.qtgui_const_sink_x_0.set_y_axis((-2), 2)
        self.qtgui_const_sink_x_0.set_x_axis((-2), 2)
        self.qtgui_const_sink_x_0.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, "")
        self.qtgui_const_sink_x_0.enable_autoscale(False)
        self.qtgui_const_sink_x_0.enable_grid(False)
        self.qtgui_const_sink_x_0.enable_axis_labels(True)


        labels = ['', '', '', '', '',
            '', '', '', '', '']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ["blue", "red", "green", "black", "cyan",
            "magenta", "yellow", "dark red", "dark green", "dark blue"]
        styles = [0, 0, 0, 0, 0,
            0, 0, 0, 0, 0]
        markers = [0, 0, 0, 0, 0,
            0, 0, 0, 0, 0]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_const_sink_x_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_const_sink_x_0.set_line_label(i, labels[i])
            self.qtgui_const_sink_x_0.set_line_width(i, widths[i])
            self.qtgui_const_sink_x_0.set_line_color(i, colors[i])
            self.qtgui_const_sink_x_0.set_line_style(i, styles[i])
            self.qtgui_const_sink_x_0.set_line_marker(i, markers[i])
            self.qtgui_const_sink_x_0.set_line_alpha(i, alphas[i])

        self._qtgui_const_sink_x_0_win = sip.wrapinstance(self.qtgui_const_sink_x_0.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_const_sink_x_0_win)
        self.joint_cognitive_controller_0 = JointCognitiveController()
        self.digital_constellation_modulator_2 = digital.generic_mod(
            constellation=const_16qam,
            differential=False,
            samples_per_symbol=2,
            pre_diff_code=True,
            excess_bw=0.35,
            verbose=False,
            log=False,
            truncate=False)
        self.digital_constellation_modulator_1 = digital.generic_mod(
            constellation=const_qpsk,
            differential=False,
            samples_per_symbol=2,
            pre_diff_code=True,
            excess_bw=0.35,
            verbose=False,
            log=False,
            truncate=False)
        self.digital_constellation_modulator_0 = digital.generic_mod(
            constellation=const_bpsk,
            differential=False,
            samples_per_symbol=2,
            pre_diff_code=True,
            excess_bw=0.35,
            verbose=False,
            log=False,
            truncate=False)
        self.blocks_throttle2_1_1 = blocks.throttle( gr.sizeof_float*1, samp_rate, True, 0 if "auto" == "auto" else max( int(float(0.1) * samp_rate) if "auto" == "time" else int(0.1), 1) )
        self.blocks_throttle2_1_0 = blocks.throttle( gr.sizeof_float*1, samp_rate, True, 0 if "auto" == "auto" else max( int(float(0.1) * samp_rate) if "auto" == "time" else int(0.1), 1) )
        self.blocks_throttle2_1 = blocks.throttle( gr.sizeof_float*1, samp_rate, True, 0 if "auto" == "auto" else max( int(float(0.1) * samp_rate) if "auto" == "time" else int(0.1), 1) )
        self.blocks_throttle2_0 = blocks.throttle( gr.sizeof_gr_complex*1, samp_rate, True, 0 if "auto" == "auto" else max( int(float(0.1) * samp_rate) if "auto" == "time" else int(0.1), 1) )
        self.blocks_threshold_ff_2 = blocks.threshold_ff(7.9, 8.1, 1)
        self.blocks_threshold_ff_1 = blocks.threshold_ff(14.9	, 15.1	, 0)
        self.blocks_threshold_ff_0 = blocks.threshold_ff((-0.1), 0.1, 1)
        self.blocks_selector_0_0 = blocks.selector(gr.sizeof_char*1,0,0)
        self.blocks_selector_0_0.set_enabled(True)
        self.blocks_selector_0 = blocks.selector(gr.sizeof_gr_complex*1,0,0)
        self.blocks_selector_0.set_enabled(True)
        self.blocks_rms_xx_0_2 = blocks.rms_ff(0.001)
        self.blocks_rms_xx_0_1_1 = blocks.rms_ff(0.001)
        self.blocks_rms_xx_0_1_0 = blocks.rms_ff(0.001)
        self.blocks_rms_xx_0_1 = blocks.rms_ff(0.001)
        self.blocks_rms_xx_0_0 = blocks.rms_ff(0.001)
        self.blocks_rms_xx_0 = blocks.rms_ff(0.001)
        self.blocks_nlog10_ff_0_1 = blocks.nlog10_ff(20, 1, 0)
        self.blocks_nlog10_ff_0_0 = blocks.nlog10_ff(20, 1, 0)
        self.blocks_nlog10_ff_0 = blocks.nlog10_ff(20, 1, 0)
        self.blocks_multiply_const_xx_0_1 = blocks.multiply_const_ff(-1, 1)
        self.blocks_multiply_const_xx_0_0 = blocks.multiply_const_ff(-1, 1)
        self.blocks_multiply_const_xx_0 = blocks.multiply_const_ff(-1, 1)
        self.blocks_moving_average_xx_0 = blocks.moving_average_ff(1024, (1/1024), 4000, 1)
        self.blocks_message_debug_1 = blocks.message_debug(True, gr.log_levels.info)
        self.blocks_message_debug_0 = blocks.message_debug(True, gr.log_levels.info)
        self.blocks_file_sink_0_0 = blocks.file_sink(gr.sizeof_float*1, '/tmp/snr_samples.dat', False)
        self.blocks_file_sink_0_0.set_unbuffered(True)
        self.blocks_file_sink_0 = blocks.file_sink(gr.sizeof_gr_complex*1, '/tmp/selector_output.cfile', False)
        self.blocks_file_sink_0.set_unbuffered(True)
        self.blocks_divide_xx_0_1 = blocks.divide_ff(1)
        self.blocks_divide_xx_0_0 = blocks.divide_ff(1)
        self.blocks_divide_xx_0 = blocks.divide_ff(1)
        self.blocks_complex_to_mag_squared_0 = blocks.complex_to_mag_squared(1)
        self.blocks_add_xx_0_0_2 = blocks.add_vff(1)
        self.blocks_add_xx_0_0_1 = blocks.add_vff(1)
        self.blocks_add_xx_0_0_0_1 = blocks.add_vff(1)
        self.blocks_add_xx_0_0_0_0 = blocks.add_vff(1)
        self.blocks_add_xx_0_0_0 = blocks.add_vff(1)
        self.blocks_add_xx_0_0 = blocks.add_vff(1)
        self.analog_sig_source_x_0_2 = analog.sig_source_f(samp_rate, analog.GR_COS_WAVE, 1000, 1, 0, 0)
        self.analog_sig_source_x_0_1 = analog.sig_source_f(samp_rate, analog.GR_COS_WAVE, 1000, 1, 0, 0)
        self.analog_sig_source_x_0_0_1 = analog.sig_source_f(samp_rate, analog.GR_COS_WAVE, 1000, 1, 0, 0)
        self.analog_sig_source_x_0_0_0 = analog.sig_source_f(samp_rate, analog.GR_COS_WAVE, 1000, 1, 0, 0)
        self.analog_sig_source_x_0_0 = analog.sig_source_f(samp_rate, analog.GR_COS_WAVE, 1000, 1, 0, 0)
        self.analog_sig_source_x_0 = analog.sig_source_f(samp_rate, analog.GR_COS_WAVE, 1000, 1, 0, 0)
        self.analog_random_source_x_0_1 = blocks.vector_source_b(list(map(int, numpy.random.randint(0, 255, 1000))), True)
        self.analog_random_source_x_0_0 = blocks.vector_source_b(list(map(int, numpy.random.randint(0, 255, 1000))), True)
        self.analog_random_source_x_0 = blocks.vector_source_b(list(map(int, numpy.random.randint(0, 255, 1000))), True)
        self.analog_noise_source_x_0_1 = analog.noise_source_f(analog.GR_GAUSSIAN, noise_amp, 1)
        self.analog_noise_source_x_0_0 = analog.noise_source_f(analog.GR_GAUSSIAN, noise_amp, 2)
        self.analog_noise_source_x_0 = analog.noise_source_f(analog.GR_GAUSSIAN, noise_amp, 0)


        ##################################################
        # Connections
        ##################################################
        self.msg_connect((self.joint_cognitive_controller_0, 'enable'), (self.blocks_selector_0, 'en'))
        self.msg_connect((self.joint_cognitive_controller_0, 'modulation'), (self.blocks_selector_0, 'iindex'))
        self.msg_connect((self.joint_cognitive_controller_0, 'channel'), (self.blocks_selector_0_0, 'iindex'))
        self.msg_connect((self.snr_modulation_controller_0, 'modulation'), (self.blocks_message_debug_0, 'store'))
        self.msg_connect((self.snr_modulation_controller_0, 'modulation'), (self.blocks_message_debug_0, 'print'))
        self.msg_connect((self.snr_modulation_controller_0, 'enable'), (self.blocks_message_debug_1, 'print'))
        self.connect((self.analog_noise_source_x_0, 0), (self.blocks_add_xx_0_0, 1))
        self.connect((self.analog_noise_source_x_0_0, 0), (self.blocks_add_xx_0_0_1, 1))
        self.connect((self.analog_noise_source_x_0_1, 0), (self.blocks_add_xx_0_0_2, 1))
        self.connect((self.analog_random_source_x_0, 0), (self.blocks_selector_0_0, 0))
        self.connect((self.analog_random_source_x_0_0, 0), (self.blocks_selector_0_0, 2))
        self.connect((self.analog_random_source_x_0_1, 0), (self.blocks_selector_0_0, 1))
        self.connect((self.analog_sig_source_x_0, 0), (self.blocks_add_xx_0_0, 0))
        self.connect((self.analog_sig_source_x_0_0, 0), (self.blocks_multiply_const_xx_0, 0))
        self.connect((self.analog_sig_source_x_0_0, 0), (self.blocks_rms_xx_0, 0))
        self.connect((self.analog_sig_source_x_0_0_0, 0), (self.blocks_multiply_const_xx_0_0, 0))
        self.connect((self.analog_sig_source_x_0_0_0, 0), (self.blocks_rms_xx_0_0, 0))
        self.connect((self.analog_sig_source_x_0_0_1, 0), (self.blocks_multiply_const_xx_0_1, 0))
        self.connect((self.analog_sig_source_x_0_0_1, 0), (self.blocks_rms_xx_0_2, 0))
        self.connect((self.analog_sig_source_x_0_1, 0), (self.blocks_add_xx_0_0_1, 0))
        self.connect((self.analog_sig_source_x_0_2, 0), (self.blocks_add_xx_0_0_2, 0))
        self.connect((self.blocks_add_xx_0_0, 0), (self.blocks_add_xx_0_0_0, 0))
        self.connect((self.blocks_add_xx_0_0_0, 0), (self.blocks_rms_xx_0_1, 0))
        self.connect((self.blocks_add_xx_0_0_0_0, 0), (self.blocks_rms_xx_0_1_0, 0))
        self.connect((self.blocks_add_xx_0_0_0_1, 0), (self.blocks_rms_xx_0_1_1, 0))
        self.connect((self.blocks_add_xx_0_0_1, 0), (self.blocks_add_xx_0_0_0_0, 0))
        self.connect((self.blocks_add_xx_0_0_2, 0), (self.blocks_add_xx_0_0_0_1, 0))
        self.connect((self.blocks_complex_to_mag_squared_0, 0), (self.blocks_moving_average_xx_0, 0))
        self.connect((self.blocks_divide_xx_0, 0), (self.blocks_throttle2_1, 0))
        self.connect((self.blocks_divide_xx_0_0, 0), (self.blocks_throttle2_1_0, 0))
        self.connect((self.blocks_divide_xx_0_1, 0), (self.blocks_throttle2_1_1, 0))
        self.connect((self.blocks_moving_average_xx_0, 0), (self.qtgui_number_sink_0, 0))
        self.connect((self.blocks_multiply_const_xx_0, 0), (self.blocks_add_xx_0_0_0, 1))
        self.connect((self.blocks_multiply_const_xx_0_0, 0), (self.blocks_add_xx_0_0_0_0, 1))
        self.connect((self.blocks_multiply_const_xx_0_1, 0), (self.blocks_add_xx_0_0_0_1, 1))
        self.connect((self.blocks_nlog10_ff_0, 0), (self.blocks_file_sink_0_0, 0))
        self.connect((self.blocks_nlog10_ff_0, 0), (self.blocks_threshold_ff_0, 0))
        self.connect((self.blocks_nlog10_ff_0, 0), (self.blocks_threshold_ff_1, 0))
        self.connect((self.blocks_nlog10_ff_0, 0), (self.blocks_threshold_ff_2, 0))
        self.connect((self.blocks_nlog10_ff_0, 0), (self.joint_cognitive_controller_0, 0))
        self.connect((self.blocks_nlog10_ff_0, 0), (self.qtgui_number_sink_0_0_1_2_0, 0))
        self.connect((self.blocks_nlog10_ff_0, 0), (self.snr_modulation_controller_0, 0))
        self.connect((self.blocks_nlog10_ff_0_0, 0), (self.joint_cognitive_controller_0, 2))
        self.connect((self.blocks_nlog10_ff_0_1, 0), (self.joint_cognitive_controller_0, 1))
        self.connect((self.blocks_rms_xx_0, 0), (self.blocks_divide_xx_0, 0))
        self.connect((self.blocks_rms_xx_0, 0), (self.qtgui_number_sink_0_0_0, 0))
        self.connect((self.blocks_rms_xx_0_0, 0), (self.blocks_divide_xx_0_0, 0))
        self.connect((self.blocks_rms_xx_0_1, 0), (self.blocks_divide_xx_0, 1))
        self.connect((self.blocks_rms_xx_0_1, 0), (self.qtgui_number_sink_0_0_0_0, 0))
        self.connect((self.blocks_rms_xx_0_1_0, 0), (self.blocks_divide_xx_0_0, 1))
        self.connect((self.blocks_rms_xx_0_1_1, 0), (self.blocks_divide_xx_0_1, 1))
        self.connect((self.blocks_rms_xx_0_2, 0), (self.blocks_divide_xx_0_1, 0))
        self.connect((self.blocks_selector_0, 0), (self.blocks_throttle2_0, 0))
        self.connect((self.blocks_selector_0_0, 0), (self.digital_constellation_modulator_0, 0))
        self.connect((self.blocks_selector_0_0, 0), (self.digital_constellation_modulator_1, 0))
        self.connect((self.blocks_selector_0_0, 0), (self.digital_constellation_modulator_2, 0))
        self.connect((self.blocks_threshold_ff_0, 0), (self.qtgui_number_sink_0_0_1_1, 0))
        self.connect((self.blocks_threshold_ff_1, 0), (self.qtgui_number_sink_0_0_1_2, 0))
        self.connect((self.blocks_threshold_ff_2, 0), (self.qtgui_number_sink_0_0_1_3, 0))
        self.connect((self.blocks_throttle2_0, 0), (self.blocks_complex_to_mag_squared_0, 0))
        self.connect((self.blocks_throttle2_0, 0), (self.blocks_file_sink_0, 0))
        self.connect((self.blocks_throttle2_0, 0), (self.qtgui_const_sink_x_0, 0))
        self.connect((self.blocks_throttle2_1, 0), (self.blocks_nlog10_ff_0, 0))
        self.connect((self.blocks_throttle2_1_0, 0), (self.blocks_nlog10_ff_0_0, 0))
        self.connect((self.blocks_throttle2_1_1, 0), (self.blocks_nlog10_ff_0_1, 0))
        self.connect((self.digital_constellation_modulator_0, 0), (self.blocks_selector_0, 0))
        self.connect((self.digital_constellation_modulator_1, 0), (self.blocks_selector_0, 1))
        self.connect((self.digital_constellation_modulator_2, 0), (self.blocks_selector_0, 2))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("gnuradio/flowgraphs", "adaptive_snr_control")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()

    def get_samp_rate_0(self):
        return self.samp_rate_0

    def set_samp_rate_0(self, samp_rate_0):
        self.samp_rate_0 = samp_rate_0

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.analog_sig_source_x_0.set_sampling_freq(self.samp_rate)
        self.analog_sig_source_x_0_0.set_sampling_freq(self.samp_rate)
        self.analog_sig_source_x_0_0_0.set_sampling_freq(self.samp_rate)
        self.analog_sig_source_x_0_0_1.set_sampling_freq(self.samp_rate)
        self.analog_sig_source_x_0_1.set_sampling_freq(self.samp_rate)
        self.analog_sig_source_x_0_2.set_sampling_freq(self.samp_rate)
        self.blocks_throttle2_0.set_sample_rate(self.samp_rate)
        self.blocks_throttle2_1.set_sample_rate(self.samp_rate)
        self.blocks_throttle2_1_0.set_sample_rate(self.samp_rate)
        self.blocks_throttle2_1_1.set_sample_rate(self.samp_rate)

    def get_noise_amp(self):
        return self.noise_amp

    def set_noise_amp(self, noise_amp):
        self.noise_amp = noise_amp
        self.analog_noise_source_x_0.set_amplitude(self.noise_amp)
        self.analog_noise_source_x_0_0.set_amplitude(self.noise_amp)
        self.analog_noise_source_x_0_1.set_amplitude(self.noise_amp)

    def get_const_qpsk(self):
        return self.const_qpsk

    def set_const_qpsk(self, const_qpsk):
        self.const_qpsk = const_qpsk

    def get_const_bpsk(self):
        return self.const_bpsk

    def set_const_bpsk(self, const_bpsk):
        self.const_bpsk = const_bpsk

    def get_const_16qam(self):
        return self.const_16qam

    def set_const_16qam(self, const_16qam):
        self.const_16qam = const_16qam




def main(top_block_cls=adaptive_snr_control, options=None):

    qapp = Qt.QApplication(sys.argv)

    tb = top_block_cls()

    tb.start()
    tb.flowgraph_started.set()

    tb.show()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    qapp.exec_()

if __name__ == '__main__':
    main()
