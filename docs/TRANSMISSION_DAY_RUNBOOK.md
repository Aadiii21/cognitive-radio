# Transmission runbook: Pluto → RTL-SDR (OTA, or conducted through an attenuator)

## Closed-loop channel-switching demo (added 26 Nov, run 28 Nov)

Shows channel switching on real radios: every round the Pluto sends a probe on each of three channels (865.7, 866.5, 867.3 MHz), the RTL-SDR measures Es/N0 on each, the unchanged `CalibratedCognitiveController` picks the channel and modulation, and the Pluto sends a data burst there. Channel quality follows a scripted schedule of Pluto TX attenuation in five phases (A–C: a different channel best; D: all mediocre; E: all poor). Sensing, decisions, retuning, transmission and reception are real; the "interference" is emulated by TX power.

**Done on 28 Nov:** 5 sessions at 1.5 m (two with `--margin-db 2`) and a 3-minute band scan. Results: Part 3 report, Section 5.9; `results/analysis/closed_loop_summary.json`.

**You need:** Pluto with antenna on TX, RTL-SDR with antenna, laptop, tape measure. A 15-round session takes about 2.5 minutes (about 2.3 s per burst, one progress line per burst).

```bash
source ~/miniforge3/bin/activate cognitive-radio
cd ~/projects/final/cognitive-radio

# 0. software check, no hardware (optional): see what a session looks like
python scripts/run_channel_switching_demo.py --simulate

# 1. passive band scan, receive only (Pluto TX LO must be OFF): 3 minutes
iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 1
python scripts/scan_band.py --minutes 3 2>&1 | tee results/hardware/band_scan.log

# 2. antennas on, measure the separation D (metres), TX LO on
iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 0

# 3. dry run: every check, nothing transmitted
python scripts/run_channel_switching_demo.py --dry-run --rf-path ota --antenna-separation-m D

# 4. one session (type TRANSMIT exactly, once); repeat this line for more sessions,
#    and add --margin-db 2 for a session with a safety margin
python scripts/run_channel_switching_demo.py --enable-rf --rf-path ota --antenna-separation-m D \
    2>&1 | tee -a results/hardware/closed_loop_demo.log

# 5. TX LO off, then summarise (and audit, while the raw captures are present)
iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 1
python scripts/summarize_closed_loop.py
python scripts/verify_closed_loop_captures.py
```

Run each block separately and wait for it to finish; pasting everything at once runs step 4 only once. Do not press Ctrl-C while bursts are still printing. Keep the antennas and people still during a session. Expected: three switches (start of phases B, C and D), 16-QAM on the good channel, QPSK in phase D, BPSK in phase E.

**If the levels don't separate the channels** (for example every channel above 20 dB, or no frames found), adjust the schedule. Save as `my_schedule.json` and add `--schedule my_schedule.json`:

```json
[
  {"name": "A: channel 0 best", "attenuation_db": [0, 10, 20]},
  {"name": "B: channel 1 best", "attenuation_db": [20, 0, 10]},
  {"name": "C: channel 2 best", "attenuation_db": [10, 20, 0]},
  {"name": "D: all mediocre",   "attenuation_db": [10, 15, 20]},
  {"name": "E: all poor",       "attenuation_db": [15, 20, 20]}
]
```
Raise all numbers by 5–10 dB if every channel is very strong; lower them if probes at 20 dB find no frame.

**Raw captures:** each session's `captures/` folder holds about 60 MB of `.cu8` files. They are not committed to git (`.gitignore`); keep a separate backup (the 28 Nov sessions are in `closed_loop_full_backup_20261128.zip`).

## OTA (the project's RF path from 23 Nov)

Antenna on the Pluto **TX** port and on the RTL-SDR; no cable between them. Measure the antenna separation and pass it every run; it is saved in each result.

```bash
# start of session: TX LO on (if it was powered down)
iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 0

# tone, then frames (D = antenna separation in metres)
python scripts/run_hardware_experiment.py --enable-rf --tone --freq 866000000 \
  --rf-path ota --antenna-separation-m D --rx-gain 28
python scripts/run_hardware_experiment.py --enable-rf --freq 866000000 \
  --rf-path ota --antenna-separation-m D --rx-gain 28 --attenuation 10 \
  --waveform results/baseband/multimod_v2/qpsk_framed_seed42.json

# end of session: TX LO off
iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 1
```

- RX gain 28 dB (gain 0/49.6 clipped on FM; gain 40 lowered Es/N0 on 23 Nov).
- Es/N0 depends on separation, antenna orientation and people moving nearby, so keep the setup fixed during a sweep and plot BER against the **measured** Es/N0, not the attenuation.
- The 23 Nov runs (13:50–14:01) were OTA but recorded as conducted. Annotate them once:
  ```bash
  python scripts/annotate_rf_path.py --from 20261123_135000 --to 20261123_140100 \
    --actual ota --note "antennas on Pluto and RTL-SDR; no cable, no attenuator"
  ```

The sections below describe the conducted path, kept for anyone with an attenuator.

## Conducted path

**Status before this runbook: no physical link has been validated.** Every
result so far is synthetic IQ. Stop at any step whose "go" condition fails,
and keep its log and result JSON.

## 0. Hard requirements (no RF without all of these)

| # | Requirement |
|---|---|
| R1 | SMA 50 Ω attenuator(s) **≥ 30 dB total**, rated **≥ 1 W**, plus SMA cable(s). Never Pluto TX → RTL-SDR directly |
| R2 | Pluto **TX** port → attenuator → RTL-SDR input. Pluto RX port unconnected. No antennas |
| R3 | The runner refuses to transmit without `--rf-path conducted --attenuator-db <≥30>`. Enter the real value |
| R4 | Centre frequency 866 MHz: the runner refuses any occupied band outside 865–868 MHz |
| R5 | Operator types `TRANSMIT` at the prompt; `docs/PHYSICAL_EXPERIMENT_CHECKLIST.md` reviewed |

Expected level at the RTL-SDR with the defaults: about +7 − 30 (Pluto setting) − 20 (amplitude 0.1) − 30 (pad) ≈ **−73 dBm**. Worst case if the Pluto setting failed: about −23 dBm.

## 1. Setup (no RF)

```bash
source ~/miniforge3/bin/activate cognitive-radio
cd ~/Downloads/cognitive-radio-modified-files
python -m pytest -q tests        # expect all to pass on your machine
python -c "import adi, iio; print('pyadi-iio', adi.__version__)"
```
**Go:** all tests pass and the import prints a version.

TX uses **pyadi-iio** by default (owner decision: Python controls the hardware; GNU Radio is for synthetic data). If the import fails, install it into this conda env with `pip install pyadi-iio` (which also needs the `pylibiio` bindings for your libiio 0.26) and re-run the import check. Send the output if it still fails. A failure only in `tests/test_pluto_tx_adapter.py` concerns the legacy GNU Radio backend and does not block pyadi transmission.

## 2. RTL-SDR gain check (no RF, about 2 min)

Use an antenna on the RTL-SDR for this step only, and a local FM station (e.g. 98.3 MHz):
```bash
for g in 0 28 49.6; do rtl_sdr -f 98300000 -s 2048000 -g $g -n 2048000 /tmp/fm_g$g.cu8; done
python -c "
import numpy as np
for g in ['0','28','49.6']:
    r=np.fromfile(f'/tmp/fm_g{g}.cu8',np.uint8); x=(r[0::2]-127.5)+1j*(r[1::2]-127.5)
    print(g,'raw',r.min(),r.max(),'rms',round(float(np.sqrt(np.mean(abs(x-x.mean())**2))),2))"
```
**Decide `G` (RX gain for every later step):**
- If manual 28 dB shows RMS clearly above about 2 (similar to `-g 0`), set `G=28`.
- If manual gains stay below about 1 RMS while `-g 0` is much larger, manual gain is not working on this dongle: set `G=0` (automatic gain).

Remove the antenna before step 4.

## 3. Dry runs (no RF)

```bash
python scripts/run_hardware_experiment.py --tone --freq 866000000
python scripts/run_hardware_experiment.py --freq 866000000
python scripts/run_multimod_experiment.py --modulations BPSK QPSK 16QAM --output-dir results/baseband/multimod_v2
```
**Go:** both dry runs print `DRY RUN`, and the tone sits at 866.100 MHz.

**Use `multimod_v2`, not `multimod`:** the earlier `multimod/` BPSK/QPSK files predate the `map_bits` fix and are invalid.

## 4. First RF: CW tone (pyadi-iio, cyclic buffer)

Wire R1/R2. Then:
```bash
python scripts/run_hardware_experiment.py --enable-rf --tone --freq 866000000 \
  --rf-path conducted --attenuator-db 30 --rx-gain G \
  2>&1 | tee results/hardware/day_01_tone_pyadi.log
```
The order is: TX on → Pluto readback → capture (TX on) → TX off → capture (TX off). The two captures are compared at the tone bin.

| Result | Meaning | Next |
|---|---|---|
| `tone_detected`, clipping < 1 % | RF chain works (pyadi, cyclic) | Step 5 |
| `tone_detected`, clipping ≥ 1 % | Too strong | Repeat with `--attenuation 45` (Pluto) or a lower `G` |
| `tone_not_detected` | TX not on air, or RX deaf | Check wiring, attenuator and the step-2 gain decision; repeat once. Fallback (if pyadi cannot be installed): `--tx-backend gnuradio --tx-mode stream`, then `--tx-mode cyclic` |
| Still not detected | — | Send the logs and the `.cu8`/`.json` capture pairs; no frame tests |
| `failed_at_readback` | Pluto did not take the requested LO/gain/rate | Send the log |

Record the **implied CFO** (Hz and ppm). Frames need |CFO| < 100 kHz.

## 5. BPSK frame loopback (bpsk_frame_v2)

```bash
python scripts/run_hardware_experiment.py --enable-rf --freq 866000000 \
  --rf-path conducted --attenuator-db 30 --rx-gain G \
  2>&1 | tee results/hardware/day_03_bpsk_v2_run1.log
```
**Go:** `frames_detected` with preamble errors 0. Then **repeat once** (`..._run2.log`) and check the BER and SNR are consistent.

If no frame is detected but the tone was detected: check the CFO in the log against the tone's implied CFO, and the clipping. Do not lower the detection threshold; send the capture.

## 6. Multimodulation loopback

For each modulation in BPSK, QPSK and 16QAM (`{mod}` = `bpsk`, `qpsk`, `16qam`):
```bash
python scripts/run_hardware_experiment.py --enable-rf --freq 866000000 \
  --rf-path conducted --attenuator-db 30 --rx-gain G \
  --waveform results/baseband/multimod_v2/{mod}_framed_seed42.json \
  2>&1 | tee results/hardware/day_04_{mod}.log
```
16-QAM needs about 17 dB SNR for BER ≤ 10⁻³ (synthetic curve). The expected conducted SNR is well above that; if not, reduce `--attenuation` in 5 dB steps while watching clipping.

## 7. After the session

```bash
iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 1    # TX LO off
```
Keep everything in `results/hardware/` (captures, sidecars, result JSONs, logs). Each result records `rf_path`, `tx_mode`, the Pluto readback and the actual RTL-SDR rate.

## Reference: synthetic receiver performance (not hardware)

`scripts/ber_curves.py` → `results/analysis/ber_vs_snr_multimod_synthetic.csv`. Es/N0 thresholds for BER ≤ 10⁻³: BPSK 6.80 dB, QPSK 9.93 dB, 16-QAM 16.67 dB (theory about 6.8 / 9.8 / 16.5). `CognitiveRadioController.from_ber_curve(csv)` loads them. They map to the receiver's data-aided SNR, not to the RTL-SDR sensing power ratio, which needs its own calibration from step 6 captures.
