"""Model parameters.

All radio power/timing numbers below are PLACEHOLDERS chosen to be in a
plausible range for a sub-GHz 802.11ah station (1 MHz channel, MCS0-ish).
They must be replaced with values measured on the MM6108 testbed
(see docs/testbed.md) before any result is reported.
"""
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Radio:
    p_sleep: float = 0.05e-3   # W, deep sleep (MCU + radio)          [PLACEHOLDER]
    p_rx: float = 60e-3        # W, receive / listen / idle-awake      [PLACEHOLDER]
    p_tx: float = 250e-3       # W, transmit                           [PLACEHOLDER]
    t_wakeup: float = 2e-3     # s, sleep->awake transition (at p_rx)  [PLACEHOLDER]
    t_guard: float = 2e-3      # s, early wake before TWT SP start
    t_tx: float = 6e-3         # s, one status update (~200 B @ ~300 kb/s)
    t_ack: float = 1e-3        # s, ACK reception
    t_ctrl_tx: float = 2e-3    # s, TWT setup/teardown frame (renegotiation)
    t_beacon: float = 3e-3     # s, beacon reception (legacy PS)
    beacon_interval: float = 0.1024  # s
    t_backoff: float = 1e-3    # s, mean backoff with no competing station


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
