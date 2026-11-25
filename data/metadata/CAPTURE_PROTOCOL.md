# SDR Capture Protocol

## Objective
Collect labelled IQ captures for signal detection and modulation
classification using the Pluto SDR and RTL-SDR.

## Planned signal conditions
- BPSK: target SNR 5, 10, 15 dB
- QPSK: target SNR 5, 10, 15 dB
- 16-QAM: target SNR 5, 10, 15 dB
- Noise-only: 3 captures
- Repetitions: 3 per modulation/SNR condition

## Capture requirements
1. Record raw IQ samples without modifying the original capture.
2. Record centre frequency and sample rate.
3. Record TX and RX gain settings.
4. Record timestamp and capture duration.
5. Record target SNR and independently measured SNR.
6. Preserve modulation labels.
7. Never treat target SNR as measured SNR.
8. Use identical receiver settings within comparable experiments.
9. Do not overwrite existing captures.
10. Record failed captures and reasons in the manifest.

## RF safety
Confirm permitted frequency, power and operating conditions
before transmitting. Use an appropriate attenuated conducted
or shielded setup where possible. Never connect Pluto TX
directly to an SDR receiver.

## Dataset structure
- data/raw/: original IQ captures
- data/processed/: derived or resampled data
- data/metadata/: manifests and capture protocol
- results/features/dataset/: extracted feature tables
