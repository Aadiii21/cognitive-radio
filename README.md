# Cost-Aware Cognitive Radio Framework

A software-based cognitive radio research project investigating joint
channel switching and adaptive modulation under time-varying channel
conditions, with explicit consideration of switching cost and packet
reliability.

## Project objective

The framework investigates when a radio should:

- Remain on its current channel and adapt its modulation.
- Switch to another channel with better conditions.
- Jointly select a channel and modulation while accounting for handoff cost.

The intended objective is to improve useful delivered throughput while
maintaining packet reliability and accounting for switching downtime.

## Current implementation

### Python simulation

- Three-channel time-varying SNR model.
- Baseline and cost-aware cognitive controllers.
- Adaptive modulation policies.
- Multi-seed and paired-seed experiments.
- Switching dwell-time experiments.
- Simulation metrics and result analysis.

### GNU Radio receiver experiments

- BPSK, QPSK and 16-QAM packet receiver.
- Equal-average-power constellation normalization.
- Timing recovery and carrier recovery.
- Pilot-assisted gain correction.
- Synchronization and payload decoding.
- Packet-level SER, BER and PDR evaluation.

### Calibration and estimation

- Coarse and refined equal-power modulation calibration.
- Logistic packet-success models.
- Leave-one-seed-out cross-validation.
- Matched clean/noisy path channel SNR calibration.
- Synthetic three-channel SNR estimator validation.
- Calibrated cognitive controller.

## Modulation configuration

| Modulation | Nominal rate |
|---|---:|
| BPSK | 1 bit/symbol |
| QPSK | 2 bits/symbol |
| 16-QAM | 4 bits/symbol |

All three constellations were normalized to equal average symbol power
before the comparative receiver calibration.

## Repository structure

```text
.
├── src/                 # Python channel models, controllers and simulations
├── gnuradio/            # GNU Radio flowgraphs and receiver experiments
├── tests/               # Python unit tests
├── results/             # Calibration datasets and experiment outputs
├── config/              # Project configuration
├── plots/               # Generated plots
└── README.md

## Experimental results

The project contains results from:

- Multi-seed controller comparisons.
- Switching dwell-time sweeps.
- Equal-power modulation calibration.
- Refined packet-success calibration.
- Logistic packet-success model fitting and validation.
- Channel noise-to-SNR calibration.
- Three-channel SNR estimator testing.

The corresponding datasets and experiment logs are retained in `results/`.

## Environment

Developed on Arch Linux using GNU Radio 3.10.12 and Python.

The project uses separate Python environments for simulation and GNU Radio components. Use the interpreter associated with the relevant environment.

## Running tests

From the project root:

```bash
python -m pytest tests/
```

## Current limitations

- No physical RTL-SDR or ADALM-Pluto hardware has been used.
- Results are from software simulation and GNU Radio simulated channels.
- Noise voltage is not equivalent to SNR in dB.
- Logistic packet-success models are calibrated over measured transition ranges. Predictions outside those ranges are boundary approximations.
- The three-channel SNR estimator has been validated using a synthetic pilot-plus-noise test.
- Complete end-to-end packet-level comparison of all four control strategies remains unfinished.

## Current project status

Completed:
- Python channel simulation and cost-aware controller.
- Paired-seed simulation analysis.
- Generalized GNU Radio packet receiver.
- Equal-power modulation calibration.
- Refined packet-success calibration.
- Logistic model fitting and leave-one-seed-out validation.
- Channel noise-to-SNR calibration.
- Three-channel synthetic SNR estimator validation.
- Calibrated controller and 100-step smoke test.

Next milestone:

Implement an end-to-end packet experiment comparing fixed BPSK, adaptive modulation, channel switching, and joint control using identical channel traces and paired receiver seeds.

## Reproducibility

Experiment scripts and their corresponding CSV datasets are retained in the repository. Abstract Python simulation results must be distinguished from GNU Radio packet-level receiver results.
