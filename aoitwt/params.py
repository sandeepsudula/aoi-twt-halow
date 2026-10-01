"""Model parameters.

Radio power values are taken from published datasheets (see docs/parameters.md
for the full table and sources). They describe the MM6108 radio module and the
STM32U585 MCU used on the EKH05 node, NOT measurements of this testbed.
Values marked [ASSUMPTION] have no published source and are estimates.
All of them are to be replaced by measurements from the measurement study
(measure/parse_power.py) before results are reported as hardware results.

Sources
  [MM6108-DS]  Morse Micro, MM6108-MF08651-US module data sheet (3.3 V, 25 C)
  [U585-DS]    STMicroelectronics, STM32U585xx data sheet DS13086
  [11ah-MCS]   IEEE 802.11ah S1G MCS table, 1 MHz, 1 SS, 8 us GI
"""
from dataclasses import dataclass, field, replace

V_SUPPLY = 3.3  # V


@dataclass(frozen=True)
class Radio:
    # Sleep floor = MCU Stop 2 with full SRAM (8.95 uA) [U585-DS]
    #             + radio deep sleep, wake on timer (~1.3 uA VBAT + ~0.3 uA FEM) [MM6108-DS]
    p_sleep: float = V_SUPPLY * (8.95e-6 + 1.3e-6 + 0.3e-6)   # ~35 uW
    # Listen: VBAT 37 mA + VDD_FEM 4.5 mA (datasheet figure is for an 8 MHz channel) [MM6108-DS]
    p_rx: float = V_SUPPLY * (37e-3 + 4.5e-3)                  # ~137 mW
    # Transmit MCS0: VBAT 78 mA + VDD_FEM 147 mA (8 MHz channel; ~20-22 dBm output) [MM6108-DS]
    p_tx: float = V_SUPPLY * (78e-3 + 147e-3)                  # ~743 mW
    t_wakeup: float = 2e-3     # s, sleep->awake transition (at p_rx)        [ASSUMPTION]
    t_guard: float = 2e-3      # s, early wake before TWT SP start           [ASSUMPTION]
    # 200 B at MCS0 1 MHz = 0.3 Mb/s [11ah-MCS] -> 5.3 ms + ~0.6 ms S1G 1 MHz preamble
    t_tx: float = 6e-3         # s
    t_ack: float = 1e-3        # s, SIFS + (NDP) ACK reception               [ASSUMPTION]
    t_ctrl_tx: float = 2e-3    # s, TWT setup/teardown frame (renegotiation)  [ASSUMPTION]
    t_beacon: float = 3e-3     # s, beacon reception (legacy PS), ~100 B at MCS0
    beacon_interval: float = 0.1024  # s
    t_backoff: float = 1e-3    # s, mean backoff with no competing station  [ASSUMPTION]


@dataclass(frozen=True)
class Environment:
    """Two-state (calm/active) continuous-time Markov process per sensor.

    'active' models the periods in which fresh data actually matters
    (an anomaly, an alarm, a moving object...).
    """
    mean_calm: float = 30 * 60.0   # s
    mean_active: float = 2 * 60.0  # s
    w_calm: float = 1.0            # AoI weight while calm
    w_active: float = 10.0         # AoI weight while active


@dataclass(frozen=True)
class SimConfig:
    horizon: float = 24 * 3600.0   # s
    aoi_dt: float = 0.05           # s, grid for AoI integration
    radio: Radio = field(default_factory=Radio)
    env: Environment = field(default_factory=Environment)


def with_radio(cfg: SimConfig, **kw) -> SimConfig:
    return replace(cfg, radio=replace(cfg.radio, **kw))
