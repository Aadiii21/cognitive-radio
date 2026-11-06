from gnuradio import gr, blocks
import pmt
import time

tb = gr.top_block()

source = blocks.vector_source_c([1+1j] * 1000000, repeat=True)
throttle = blocks.throttle(gr.sizeof_gr_complex, 32000, True)
selector = blocks.selector(gr.sizeof_gr_complex, 0, 0)
sink = blocks.vector_sink_c()

tb.connect(source, throttle, selector, sink)

tb.start()
time.sleep(1)

enabled_count = len(sink.data())
print("Samples enabled:", enabled_count)

# Send direct PMT Boolean FALSE
selector.post(pmt.intern("en"), pmt.PMT_F)

time.sleep(1)

disabled_count = len(sink.data())
print("Samples after disable:", disabled_count)
print("New samples:", disabled_count - enabled_count)

# Re-enable
selector.post(pmt.intern("en"), pmt.PMT_T)

time.sleep(1)

reenabled_count = len(sink.data())
print("Samples after re-enable:", reenabled_count)
print("New samples:", reenabled_count - disabled_count)

tb.stop()
tb.wait()
