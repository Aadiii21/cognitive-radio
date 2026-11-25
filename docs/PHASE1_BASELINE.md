# Phase 1: Hardware and Receiver Baseline

Date: 2026-11-21

## 1. Hardware
- RTL-SDR detected and RX capture tested.
- ADALM-Pluto detected through libiio.
- Pluto IIO interface and TX sink constructor tested.
- Pluto waveform preparation implemented.
- No Pluto RF transmission performed.
- Antenna frequency suitability and permitted transmission
  conditions remain to be verified.

## 2. Waveform Generation
- BPSK, QPSK and 16QAM generation implemented.
- Root-raised-cosine filtering.
- 2.4 MSPS baseband sample rate.
- Prepared complex float32 waveforms.
- TX preparation remains separate from actual RF transmission.

## 3. RTL-SDR Receiver Validation
- IQ capture automation implemented.
- IQ integrity and saturation checks implemented.
- Feature extraction implemented.
- RX validation manifest maintained separately.
- Two ambient validation captures recorded.
- Ambient signals are not labelled as known modulation classes.

## 4. Synthetic Receiver Validation

### Reference SNR
- 180 trials.
- BPSK, QPSK and 16QAM.
- Target SNR: 5, 10 and 15 dB.
- Maximum absolute error: 0.0299 dB.
- Result: PASS.

File:
results/reference_snr_validation_20261121_123318.csv

### Timing Synchronization
- 180 trials.
- Random timing delay, complex gain and phase.
- Zero timing detection errors.
- Maximum absolute SNR error: 0.0307 dB.
- Result: PASS.

File:
results/timing_sync_validation_20261121_123822.csv

### CFO Synchronization
- 180 trials.
- CFO range: -2000 to +2000 Hz.
- Coarse timing/CFO acquisition and block-correlation
  fine CFO estimation.
- Zero timing detection errors.
- CFO MAE below 0.004 Hz.
- Maximum absolute SNR error: 0.0313 dB.
- Result: PASS.

File:
results/cfo_sync_validation_20261121_124202.csv

## 5. Known Limitations
- SRO has not been validated.
- Multipath synchronization has not been validated.
- Synthetic synchronization results do not establish
  real hardware synchronization performance.
- Controlled Pluto-to-RTL-SDR RF transmission and capture
  have not been completed.
- Existing sensor SNR estimators require bandwidth-aware
  validation before being used as authoritative labels.

## 6. Existing System
- Existing channel model and cognitive controller retained.
- Existing noise calibration and calibrated controller retained.
- Existing experiment results and capture manifests retained.
- No architectural redesign included in this baseline.

## 7. Phase 1 Decision
Receiver preparation and synthetic reference synchronization
validation are complete.

Proceed to system architecture review and redesign.
Hardware RF validation remains a separate future milestone.
