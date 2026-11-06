from gnuradio import gr, blocks
import time

tb = gr.top_block()

source = blocks.vector_source_c(
    [1+1j] * 1000000,
    repeat=True
)

throttle = blocks.throttle(
    gr.sizeof_gr_complex,
    32000,
    True
)

selector = blocks.selector(
    gr.sizeof_gr_complex, 0, 0
)

sink = blocks.vector_sink_c()

tb.connect(source, throttle, selector, sink)

tb.start()
time.sleep(1)

enabled_count = len(sink.data())
print("Samples while enabled:", enabled_count)

selector.set_enabled(False)
time.sleep(1)

disabled_count = len(sink.data())
print("Samples after disabling:", disabled_count)
print("New samples:", disabled_count - enabled_count)

tb.stop()
tb.wait()
