# Physical Experiment Checklist

> **Status (25 Nov 2026):** this document is a historical record of the pre-transmission checklist; it is kept unchanged below. Final state: the over-the-air Pluto → RTL-SDR link was tested on 23 Nov (BPSK/QPSK/16-QAM BER matches theory), a DL modulation classifier was added (98.5 % on real OTA captures), and the hardware closed loop was removed from scope. Current documents: `MASTER_README.md`, `docs/RESULTS_AND_DISCUSSION.md`, `docs/LIMITATIONS.md` and the reports in `docs/reports/`.

**Date:** November 23, 2026
**Project:** SDR-Based Cognitive Radio System
**Status:** Final pre-experiment checklist
**Target RF path:** Pluto TX → [50-ohm attenuator] → RTL-SDR RX

---

## 1. Required RF Cable and Connectors

| Item | Description |
|------|-------------|
| Pluto SDR TX connector | SMA or similar (confirm ADALM-PLUTO connector type) |
| RTL-SDR RX connector | SMA or similar (confirm RTL2838 connector type) |
| Cable 1 | Low-loss coaxial cable, SMA to SMA, 50 ohm, ≤ 1 m |
| Cable 2 | Low-loss coaxial cable, SMA to U.FL/USB-C, ≤ 1 m |
| Adapters | SMA to U.FL / USB-C adapter (if needed) |

> Verify connector types on both devices before purchasing components.

---

## 2. Required 50-Ohm Attenuation Chain

| Component | Value |
|-----------|-------|
| Primary attenuator | 10 dB fixed attenuator (50 ohm, SMA-SMA) |
| Secondary (if needed) | 30 dB TX attenuation set in Pluto TX adapter |
| Total | 40 dB (10 dB fixed + 30 dB TX) — size from MEASURED Pluto output; more attenuation is the safe starting point |

> NOTE: Verify actual power budget with measured Pluto TX power before final configuration.
> The 10 dB fixed attenuator is required. The 30 dB TX attenuation is already configured.
> Total effective attenuation: 40 dB from Pluto TX output to RTL-SDR input.

---

## 3. TX Output Power Verification

| Item | Status |
|------|--------|
| Pluto TX typical power | ~9.5 dBm (AD9363, uncalibrated) |
| TX attenuation set | 30 dB (IIO hardware) |
| amplitude_scale | 0.1 (see code: src/radio/pluto_tx_adapter.py) |
| Estimated RX input | Unverified (AD9363 power output not yet measured) |
| Safe input range | RTL-SDR: UNVERIFIED — confirm from datasheet/measurement; check capture clipping fraction ≈ 0 |

> UNVERIFIED: Exact TX output power at the AD9363. Verify with external power meter.

---

## 4. RTL-SDR Maximum Input Verification

| Parameter | Value |
|-----------|-------|
| RTL-SDR | RTL2838 (R820T) |
| Safe input range | UNVERIFIED — confirm from datasheet/measurement |
| Receiver gain | 28 dB (current setting) |
| Signal occupied bandwidth | ≈ 0.70 MHz (Rs·(1+β) = 520.8 kBd × 1.35 at 2.083333 MS/s) |
| Max safe input | 0 dBm (conservative) |

> After each capture, check `clipping_fraction` in the result file (raw samples at 0/255). Reduce level if it is not ≈ 0.

---

## 5. Frequency and Sample-Rate Agreement

| Parameter | TX | RX | Consistent? |
|-----------|----|----|-------------|
| Center frequency | `--freq` (e.g. 866 MHz) — required, no default | same | runner enforces whole occupied band inside 865–868 MHz |
| Sample rate | 2,083,333 Hz requested; **actual value read back** from `ad9361-phy` voltage0 (output) `sampling_frequency` while transmitting | 2,083,333 Hz requested; actual value from `rtl_sdr` "Exact sample rate" | receiver uses the two measured rates |

> 865.000 MHz centre is refused: the ~0.70 MHz signal would extend below 865 MHz.
> The runner aborts (TX stopped) if TX LO, TX gain or the read-back rate do not match the request.

---

## 6. Physical Connection Verification

| Step | Check |
|------|-------|
| [ ] Pluto SDR connected to host (USB/network) |
| [ ] RTL-SDR connected to host (USB) |
| [ ] Pluto TX powered via USB |
| [ ] RTL-SDR powered via USB |
| [ ] 50 ohm coax cable between Pluto TX and attenuator |
| [ ] 50 ohm coax cable between attenuator and RTL-SDR RX |
| [ ] All connections secure and routed |
| [ ] No loose cables |

---

## 7. Final Operator Authorization Before TX

| Item | Required |
|------|----------|
| Regulatory authorization | 865-868 MHz SRD band (India) |
| Equipment approval | Confirm pluto and rtl-sdr are approved |
| Frequency category | Licensed/SRD category |
| Occupied bandwidth | ≈ 0.70 MHz nominal — confirm against the limit for the band/category used |
| TX power | Within regulatory limits (verify with power meter) |
| Duty cycle | Within limits (if applicable) |
| ERP | Within limits |
| Operator confirmation | Explicit — read and initial |

> Operator initials: ______________

---

## 8. Safety Rules

- TX disabled by default (default RF_ENABLED = False).
- `--enable-rf` required for transmission.
- Never connect Pluto TX directly to RTL-SDR RX.
- 50 ohm attenuator chain mandatory.
- No antenna radiation without regulatory authorization.
- Keep all measurements and logs.

---

## 9. Checks Enforced by `scripts/run_hardware_experiment.py --enable-rf`

These are automatic and fail closed; they do **not** replace sections 1–8.

1. `--freq` given explicitly; occupied band Rs·(1+β) entirely inside 865–868 MHz.
2. TX library for the selected backend (default pyadi-iio: `adi` + `iio`; or `gnuradio.iio` with `--tx-backend gnuradio`), `rtl_sdr` and `iio_attr` available; Pluto reachable.
3. This checklist file exists and the operator types `TRANSMIT`.
4. Waveform is `bpsk_frame_v2`; sample count matches metadata.
5. After TX start: Pluto readback (TX LO within 1 kHz, TX hardwaregain = −attenuation ± 0.5 dB, band re-checked with read-back rate). Any failure → TX stopped, no capture.
6. TX is stopped and the RF flag cleared on every exit path (errors, Ctrl-C).
7. The saved capture is the RTL-SDR's bytes, with a sidecar (`data_kind: rtl_sdr_rx_capture`).

---

*End of Physical Experiment Checklist.*
