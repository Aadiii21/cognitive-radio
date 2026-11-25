"""Simple measurement-driven cognitive-radio policy."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

MODULATION_ORDER = ("BPSK", "QPSK", "16QAM")


@dataclass
class RadioDecision:
    channel_index: int
    modulation: str
    action: str
    snr_db: float


class CognitiveRadioController:
    """Choose the best measured channel and the highest robust modulation.

    Thresholds are explicit policy parameters, not claims about universal
    modem performance. `from_ber_curve()` derives them from measured
    BER-vs-SNR data for a target BER. The SNR passed to `decide()` must use
    the same definition as the curve (the multimod receiver reports a
    data-aided post-matched-filter Es/N0); a sensing power ratio is not that
    and needs its own calibration.

    Actions:
      initial                         first decision, nothing to switch from
      hold                            same channel and modulation
      hold_dwell                      change wanted but the dwell timer is running
      change_modulation / switch_channel / switch_channel_and_modulation
      insufficient_snr                best channel is below the BPSK threshold:
                                      BPSK on the best channel, but do not expect
                                      the target BER (the caller may choose not to send)
    """

    def __init__(self, bpsk_min_db=4.0, qpsk_min_db=10.0, qam16_min_db=18.0,
                 min_dwell_steps=2, hysteresis_db=1.0):
        if not (bpsk_min_db < qpsk_min_db < qam16_min_db):
            raise ValueError("SNR thresholds must be strictly increasing")
        if hysteresis_db < 0:
            raise ValueError("hysteresis_db must be >= 0")
        self.thresholds = (float(bpsk_min_db), float(qpsk_min_db), float(qam16_min_db))
        self.min_dwell_steps = max(0, int(min_dwell_steps))
        self.hysteresis_db = float(hysteresis_db)
        self.current_channel: int | None = None
        self.current_modulation: str | None = None
        self._dwell = 0

    # --------------------------------------------------------------- policy
    def _modulation_for(self, snr, current):
        """Highest modulation whose threshold the SNR meets. Moving UP to a
        higher order needs threshold + hysteresis; staying needs the threshold."""
        _, qpsk, qam16 = self.thresholds
        h = self.hysteresis_db
        cur = MODULATION_ORDER.index(current) if current in MODULATION_ORDER else -1

        def ok(level, threshold):
            return snr >= threshold + (h if level > cur else 0.0)

        if ok(2, qam16):
            return "16QAM"
        if ok(1, qpsk):
            return "QPSK"
        return "BPSK"

    def decide(self, snr_by_channel):
        values = [float(v) for v in snr_by_channel]
        if not values:
            raise ValueError("At least one channel measurement is required")
        bpsk_min = self.thresholds[0]
        best = max(range(len(values)), key=values.__getitem__)

        # First decision: nothing to switch from.
        if self.current_channel is None:
            mod = self._modulation_for(values[best], None)
            self.current_channel, self.current_modulation = best, mod
            action = "insufficient_snr" if values[best] < bpsk_min else "initial"
            return RadioDecision(best, mod, action, values[best])

        # The channel list may have shrunk: the current channel no longer exists.
        current_exists = self.current_channel < len(values)
        if not current_exists:
            self._dwell = 0

        # Channel: switch only if the best beats the current by the hysteresis.
        if current_exists and values[best] < values[self.current_channel] + self.hysteresis_db:
            target = self.current_channel
        else:
            target = best
        mod = self._modulation_for(values[target], self.current_modulation
                                   if target == self.current_channel else None)

        # Dwell holds a change, unless the current channel is no longer usable.
        current_unusable = current_exists and values[self.current_channel] < bpsk_min
        wants_change = target != self.current_channel or mod != self.current_modulation
        if self._dwell > 0 and current_exists and not current_unusable and wants_change:
            self._dwell -= 1
            ch = self.current_channel
            # A modulation DOWNgrade on the held channel is applied at once:
            # holding a too-high order costs errors.
            held = self._modulation_for(values[ch], self.current_modulation)
            if MODULATION_ORDER.index(held) < MODULATION_ORDER.index(self.current_modulation):
                self.current_modulation = held
                return RadioDecision(ch, held, "change_modulation", values[ch])
            return RadioDecision(ch, self.current_modulation, "hold_dwell", values[ch])
        if self._dwell > 0:
            self._dwell -= 1

        channel_changed = target != self.current_channel
        modulation_changed = mod != self.current_modulation
        if values[target] < bpsk_min:
            action = "insufficient_snr"
        elif channel_changed and modulation_changed:
            action = "switch_channel_and_modulation"
        elif channel_changed:
            action = "switch_channel"
        elif modulation_changed:
            action = "change_modulation"
        else:
            action = "hold"
        if channel_changed or modulation_changed:
            self._dwell = self.min_dwell_steps
        self.current_channel, self.current_modulation = target, mod
        return RadioDecision(target, mod, action, values[target])

    # ------------------------------------------------------ calibration
    @staticmethod
    def thresholds_from_ber_curve(rows, target_ber=1e-3):
        """Minimum SNR per modulation at which BER <= target, by linear
        interpolation of log10(BER) between measured points.

        rows: iterable of dicts with keys modulation, snr_db, ber.
        Raises if a modulation never reaches the target in the data.
        """
        import math

        by_mod = {}
        for r in rows:
            by_mod.setdefault(r["modulation"], []).append((float(r["snr_db"]), float(r["ber"])))
        out = {}
        for mod in MODULATION_ORDER:
            pts = sorted(by_mod.get(mod, []))
            if not pts:
                raise ValueError(f"no BER data for {mod}")
            found = None
            for (s0, b0), (s1, b1) in zip(pts, pts[1:]):
                if b0 > target_ber >= b1:
                    lb0 = math.log10(max(b0, 1e-12))
                    lb1 = math.log10(max(b1, 1e-12))
                    lt = math.log10(target_ber)
                    found = s0 + (lt - lb0) / (lb1 - lb0) * (s1 - s0) if lb1 != lb0 else s1
                    break
            if found is None:
                if pts[0][1] <= target_ber:
                    found = pts[0][0]   # already met at the lowest measured SNR (upper bound)
                else:
                    raise ValueError(f"{mod} never reaches BER {target_ber} in the data")
            out[mod] = found
        return out

    @classmethod
    def from_ber_curve(cls, csv_path, target_ber=1e-3, **kwargs):
        with open(Path(csv_path), newline="") as fh:
            rows = list(csv.DictReader(fh))
        t = cls.thresholds_from_ber_curve(rows, target_ber)
        return cls(bpsk_min_db=t["BPSK"], qpsk_min_db=t["QPSK"], qam16_min_db=t["16QAM"], **kwargs)
