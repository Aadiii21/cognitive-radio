from gnuradio import gr, blocks
from src.gnuradio_controller import SNRModulationController

tb = gr.top_block()

snr_values = [23.0, 11.0, 5.0, -3.0]

source = blocks.vector_source_f(snr_values, False)
controller = SNRModulationController()
debug = blocks.message_debug()

tb.connect(source, controller)
tb.msg_connect(
    (controller, "modulation"),
    (debug, "store")
)

tb.start()
tb.wait()

print("\nController test completed.")
print("Expected messages: 2, 1, 0")
print("Actual message count:", debug.num_messages())

for i in range(debug.num_messages()):
    print("Message", i, ":", debug.get_message(i))
