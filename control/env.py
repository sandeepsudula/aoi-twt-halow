"""Link + energy + AoI environment for joint TX-power / TWT-interval control.

Decision epochs of `epoch_s` seconds. In each epoch the controller picks
(TX power level, TWT wake interval) for a node. Within the epoch the node wakes
every T seconds, samples its sensor and sends one update with up to `retries`
retransmissions. Outcomes are computed in expectation (fast, smooth reward):

  link    : log-distance path loss + AR(1) shadowing, node distance does a
            slow random walk -> SNR -> best MCS (rate adaptation) -> PER
  energy  : sleep + per-wake listen + expected (re)transmissions at a TX
            power whose supply cost grows with output power (PA efficiency)
  AoI     : periodic attempts with success prob q per wake ->
            mean AoI ~= T*(1/q - 1/2) + delivery delay
  context : calm/active environment state (same CTMC as aoitwt), AoI in
            active epochs weighted w_active

Reward = -(w * AoI / aoi_ref) - lam * (P_avg / p_ref)

Link and power numbers come from published sources (docs/parameters.md):
MM6108 module data sheet (power, TX power, MCS0 sensitivity), the 802.11ah
MCS table (rates), 802.11 per-MCS sensitivity steps, and the TGah pico/hot-zone
path-loss model. Shadowing and a few timings are [ASSUMPTION]s. Replace them
with the measurement study's values (measure/analyze.py, measure/parse_power.py)
before reporting hardware results.

The controller only sees what the gateway can see: the SNR bucket from the
last epoch (`iw station dump` signal minus noise floor) and the last reported
calm/active state. That makes the problem a contextual bandit for this first
version; queue/battery state can be added later to make it a full MDP.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# 802.11ah 1 MHz, 1 spatial stream, 8 us GI rates (Mb/s) [802.11ah MCS table].
# SNR thresholds (dB, at 10 % PER) = sensitivity - noise floor (-109 dBm), with
# sensitivity = MM6108 MCS0 1 MHz -105 dBm [MM6108 data sheet] plus the 802.11
# per-MCS minimum-sensitivity steps (0,3,5,8,12,16,17,18 dB); MCS10 is 3 dB
# below MCS0 (2x repetition).
MCS_TABLE = [  # (name, rate_mbps, snr_threshold_db)
    ("MCS10", 0.15, 1.0),
    ("MCS0", 0.30, 4.0),
    ("MCS1", 0.60, 7.0),
    ("MCS2", 0.90, 9.0),
    ("MCS3", 1.20, 12.0),
    ("MCS4", 1.80, 16.0),
    ("MCS5", 2.40, 20.0),
    ("MCS6", 2.70, 21.0),
    ("MCS7", 3.00, 22.0),
]


@dataclass
class LinkModel:
    # TGah pico/hot-zone outdoor model at 900 MHz: PL = 23.3 + 36.7 log10(d) dB
    pl0_db: float = 23.3
    pl_exp: float = 3.67
    shadow_sigma_db: float = 6.0  # shadowing std (dB)                 [ASSUMPTION]
    shadow_rho: float = 0.9      # AR(1) correlation between epochs     [ASSUMPTION]
    # thermal noise -174 dBm/Hz + 60 dB (1 MHz) + 5 dB station noise figure
    noise_floor_dbm: float = -109.0
    d_min: float = 10.0
    d_max: float = 600.0
    d_step: float = 15.0         # random-walk step per epoch (m)

    def path_loss_db(self, d):
        return self.pl0_db + 10 * self.pl_exp * np.log10(np.maximum(d, 1.0))


@dataclass
class PowerModel:
    # same data-sheet values as aoitwt/params.py (3.3 V supply)
    p_sleep: float = 35e-6       # W, MCU Stop 2 + radio deep sleep
    p_rx: float = 0.137          # W, listen (37 + 4.5 mA)
    p_tx_base: float = 0.257     # W, radio core while transmitting (VBAT 78 mA)
    # FEM supply 147 mA x 3.3 V = 0.485 W at ~20 dBm (0.1 W) out -> ~0.21;
    # FEM bias at low output power is neglected                    [ASSUMPTION]
    pa_eff: float = 0.21
    t_wake_listen: float = 5e-3  # s, wake-up + guard + ACK per wake  [ASSUMPTION]
    payload_bytes: int = 200
    preamble_s: float = 0.6e-3


@dataclass
class EnvConfig:
    power_levels_dbm: tuple = (0.0, 5.0, 10.0, 15.0, 20.0)
    intervals_s: tuple = (1.0, 2.0, 5.0, 10.0, 30.0)
    epoch_s: float = 60.0
    retries: int = 3
    mean_calm_epochs: float = 30.0
    mean_active_epochs: float = 2.0
    w_calm: float = 1.0
    w_active: float = 10.0
    lam: float = 1.0
    aoi_ref: float = 10.0        # s
    p_ref: float = 1e-3          # W
    aoi_cap: float = 600.0       # s, AoI is capped (link effectively down)
    snr_bins_db: tuple = (0.0, 5.0, 10.0, 15.0, 20.0, 30.0)  # bucket edges
    link: LinkModel = field(default_factory=LinkModel)
    power: PowerModel = field(default_factory=PowerModel)


class JointControlEnv:
    def __init__(self, cfg: EnvConfig | None = None, seed: int = 0):
        self.cfg = cfg or EnvConfig()
        self.rng = np.random.default_rng(seed)
        c = self.cfg
        self.actions = [(p, t) for p in c.power_levels_dbm for t in c.intervals_s]
        self.n_actions = len(self.actions)
        self.n_snr = len(c.snr_bins_db) + 1
        self.n_states = self.n_snr * 2
        self.reset()

    # ---------------- state ----------------
    def reset(self):
        c = self.cfg
        self.d = self.rng.uniform(c.link.d_min, c.link.d_max)
        self.shadow = self.rng.normal(0, c.link.shadow_sigma_db)
        self.active = False
        self.last_snr = self._snr(c.power_levels_dbm[-1])
        return self.observe()

    def _snr(self, p_dbm):
        L = self.cfg.link
        return p_dbm - L.path_loss_db(self.d) - self.shadow - L.noise_floor_dbm

    def snr_bucket(self, snr_db):
        return int(np.searchsorted(self.cfg.snr_bins_db, snr_db))

    def observe(self):
        """Discrete context the gateway can observe: (SNR bucket at max power, active)."""
        return self.snr_bucket(self.last_snr) * 2 + int(self.active)

    # ---------------- link / energy / AoI ----------------
    @staticmethod
    def best_mcs(snr_db):
        ok = [m for m in MCS_TABLE if snr_db >= m[2]]
        return ok[-1] if ok else MCS_TABLE[0]

    @staticmethod
    def per(snr_db, thr_db, slope=1.2):
        """Packet error rate: logistic curve, 10 % PER at the MCS threshold
        (the data-sheet sensitivity definition)."""
        return float(1.0 / (1.0 + np.exp(slope * (snr_db - thr_db) + np.log(9.0))))

    def outcome(self, p_dbm, T, snr_db=None, active=None):
        """Expected (weighted AoI, mean AoI, avg power W, delivery prob) for an epoch."""
        c, P = self.cfg, self.cfg.power
        snr = self._snr(p_dbm) if snr_db is None else snr_db
        active = self.active if active is None else active
        name, rate, thr = self.best_mcs(snr)
        e = self.per(snr, thr)
        R = c.retries
        q = 1.0 - e ** (R + 1)                       # delivery prob per wake
        attempts = (1 - e ** (R + 1)) / (1 - e) if e < 1 else R + 1
        t_tx = P.payload_bytes * 8 / (rate * 1e6) + P.preamble_s
        p_tx = P.p_tx_base + (10 ** (p_dbm / 10) * 1e-3) / P.pa_eff
        e_wake = P.p_rx * P.t_wake_listen + attempts * (p_tx * t_tx + P.p_rx * 1e-3)
        awake = P.t_wake_listen + attempts * (t_tx + 1e-3)
        p_avg = P.p_sleep + (e_wake - P.p_sleep * awake) / T
        delay = P.t_wake_listen + t_tx * (1 + (attempts - 1))
        q_eff = max(q, 1e-6)
        aoi = min(T * (1.0 / q_eff - 0.5) + delay, c.aoi_cap)
        w = c.w_active if active else c.w_calm
        return w * aoi, aoi, p_avg, q

    def reward_of(self, w_aoi, p_avg):
        c = self.cfg
        return -(w_aoi / c.aoi_ref) - c.lam * (p_avg / c.p_ref)

    # ---------------- step ----------------
    def step(self, a: int):
        p_dbm, T = self.actions[a]
        w_aoi, aoi, p_avg, q = self.outcome(p_dbm, T)
        r = self.reward_of(w_aoi, p_avg)
        info = {"aoi": aoi, "w_aoi": w_aoi, "p_avg": p_avg, "q": q,
                "active": self.active, "snr": self._snr(p_dbm), "d": self.d}
        self._advance()
        return self.observe(), r, info

    def _advance(self):
        c, L = self.cfg, self.cfg.link
        self.last_snr = self._snr(c.power_levels_dbm[-1])
        self.d = float(np.clip(self.d + self.rng.normal(0, L.d_step), L.d_min, L.d_max))
        self.shadow = (L.shadow_rho * self.shadow
                       + np.sqrt(1 - L.shadow_rho ** 2) * self.rng.normal(0, L.shadow_sigma_db))
        if self.active:
            if self.rng.random() < 1.0 / c.mean_active_epochs:
                self.active = False
        elif self.rng.random() < 1.0 / c.mean_calm_epochs:
            self.active = True

    def oracle_action(self):
        """Best action with full knowledge of the current SNR (upper bound)."""
        best, best_r = 0, -np.inf
        for i, (p, T) in enumerate(self.actions):
            w_aoi, _, p_avg, _ = self.outcome(p, T)
            r = self.reward_of(w_aoi, p_avg)
            if r > best_r:
                best, best_r = i, r
        return best
