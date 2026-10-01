"""Discrete-event prototype of AoI-aware Target Wake Time for 802.11ah stations.

Scope of this prototype (deliberately simple, to be replaced by ns-3):
  * Uplink status updates only, generate-at-will (the station samples its
    sensor at the moment it wakes, so the update is as fresh as possible).
  * Individual TWT: the AP staggers service periods (SPs), so a TWT station
    finds the channel free during its SP (no contention). Legacy power save
    stations contend after the beacon they wake for.
  * No PHY errors / retransmissions yet.

Policies
  fixed     : one TWT wake interval T for the whole run.
  adaptive  : two intervals (T_slow, T_fast). The station switches to T_fast
              (renegotiating its TWT agreement) when it observes the 'active'
              state at a wake, and back to T_slow after k_calm calm wakes.
  adaptive + event_wake : as adaptive, but local always-on sensing lets the
              station leave sleep immediately when the environment becomes
              active, contend for the channel outside its SP, report, and
              renegotiate to T_fast in the same wake.
  legacy    : 802.11 power save. Wakes for a beacon every listen interval,
              and wakes on beacon boundaries with period T to send uplink
              data, contending with every other station that chose the same
              beacon.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass

import numpy as np

from .params import Radio, SimConfig


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------
def gen_switch_times(cfg: SimConfig, rng: np.random.Generator) -> np.ndarray:
    """Sorted times at which the calm/active state flips. Starts calm."""
    env, out, t, active = cfg.env, [], 0.0, False
    while True:
        t += rng.exponential(env.mean_active if active else env.mean_calm)
        if t >= cfg.horizon:
            return np.asarray(out)
        out.append(t)
        active = not active


def state_on_grid(switch: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """1 where active, 0 where calm."""
    return (np.searchsorted(switch, grid, side="right") % 2).astype(np.int8)


# --------------------------------------------------------------------------
# Energy / timing of one wake
# --------------------------------------------------------------------------
def twt_wake(r: Radio):
    """(energy J, awake s, delivery delay s) of one TWT SP with one update."""
    awake = r.t_wakeup + r.t_guard + r.t_tx + r.t_ack
    e = r.p_rx * (r.t_wakeup + r.t_guard + r.t_ack) + r.p_tx * r.t_tx
    return e, awake, r.t_wakeup + r.t_guard + r.t_tx


def renegotiation(r: Radio):
    """Extra (energy, awake) to tear down / set up a TWT agreement in a wake."""
    return r.p_tx * r.t_ctrl_tx + r.p_rx * r.t_ack, r.t_ctrl_tx + r.t_ack


def unscheduled_wake(r: Radio):
    """Contended access outside any SP (channel assumed mostly idle)."""
    awake = r.t_wakeup + r.t_backoff + r.t_tx + r.t_ack
    e = r.p_rx * (r.t_wakeup + r.t_backoff + r.t_ack) + r.p_tx * r.t_tx
    return e, awake, r.t_wakeup + r.t_backoff + r.t_tx


def legacy_uplink(r: Radio, n_contenders: np.ndarray):
    """Vectorised over the number of stations sharing the same beacon."""
    wait = r.t_beacon + r.t_backoff + (n_contenders - 1) / 2.0 * (r.t_tx + r.t_ack)
    awake = r.t_wakeup + wait + r.t_tx + r.t_ack
    e = r.p_rx * (r.t_wakeup + wait + r.t_ack) + r.p_tx * r.t_tx
    return e, awake, r.t_wakeup + wait + r.t_tx


def budget_optimal_interval(r: Radio, p_budget: float) -> float:
    """Smallest fixed TWT interval whose average power fits p_budget."""
    e, awake, _ = twt_wake(r)
    if p_budget <= r.p_sleep:
        raise ValueError("budget below sleep power")
    return (e - r.p_sleep * awake) / (p_budget - r.p_sleep)


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
@dataclass
class Result:
    avg_power: float              # W
    n_wakes: int
    n_reneg: int
    mean_aoi: float = np.nan      # s, time average
    mean_aoi_active: float = np.nan   # s, average over active periods only
    weighted_aoi: float = np.nan  # s, state-weighted average
    det_latency: np.ndarray | None = None  # s, per active episode


def _finish(cfg, switch, e_tot, awake_tot, n_wakes, n_reneg, gen, dlv, compute_aoi):
    e_tot += cfg.radio.p_sleep * max(cfg.horizon - awake_tot, 0.0)
    res = Result(e_tot / cfg.horizon, n_wakes, n_reneg)
    if compute_aoi:
        _aoi(res, cfg, switch, np.asarray(gen), np.asarray(dlv))
    return res


def _aoi(res: Result, cfg: SimConfig, switch, gen, dlv):
    # Prepend a virtual update generated and delivered at t=0, sort by
    # delivery time and keep the freshest generation time delivered so far.
    gen = np.concatenate(([0.0], gen))
    dlv = np.concatenate(([0.0], dlv))
    order = np.argsort(dlv, kind="stable")
    dlv, gen = dlv[order], np.maximum.accumulate(gen[order])
    grid = np.arange(0.0, cfg.horizon, cfg.aoi_dt)
    idx = np.searchsorted(dlv, grid, side="right") - 1
    age = grid - gen[idx]
    st = state_on_grid(switch, grid)
    w = np.where(st == 1, cfg.env.w_active, cfg.env.w_calm)
    res.mean_aoi = float(age.mean())
    res.mean_aoi_active = float(age[st == 1].mean()) if st.any() else np.nan
    res.weighted_aoi = float((w * age).sum() / w.sum())
    starts = switch[0::2]
    k = np.searchsorted(gen, starts, side="left")   # first update sampled after onset
    ok = k < len(gen)
    lat = np.full(len(starts), np.nan)
    lat[ok] = dlv[k[ok]] - starts[ok]
    res.det_latency = lat


# --------------------------------------------------------------------------
# TWT station
# --------------------------------------------------------------------------
def simulate_twt(policy: dict, cfg: SimConfig, switch: np.ndarray,
                 rng: np.random.Generator, compute_aoi: bool = True) -> Result:
    r = cfg.radio
    e_w, a_w, d_w = twt_wake(r)
    H = cfg.horizon

    if policy["kind"] == "fixed":
        T = policy["T"]
        wakes = np.arange(rng.uniform(0, T), H, T)
        n = len(wakes)
        return _finish(cfg, switch, n * e_w, n * a_w, n, 0,
                       wakes, wakes + d_w, compute_aoi)

    if policy["kind"] != "adaptive":
        raise ValueError(policy["kind"])

    T_slow, T_fast = policy["T_slow"], policy["T_fast"]
    k_calm = policy.get("k_calm", 3)
    event_wake = policy.get("event_wake", False)
    e_r, a_r = renegotiation(r)
    e_u, a_u, d_u = unscheduled_wake(r)

    sw = switch.tolist()
    starts = sw[0::2]
    i_start = 0
    t = rng.uniform(0, T_slow)
    fast, calm_run = False, 0
    e_tot = a_tot = 0.0
    n_w = n_r = 0
    gen, dlv = [], []

    last = 0.0  # time of the previous wake
    while t < H:
        if event_wake:
            # drop onsets that happened while the station was already awake/fast
            while i_start < len(starts) and starts[i_start] <= last:
                i_start += 1
            if not fast and i_start < len(starts) and starts[i_start] < t:
                # local sensing caught an onset while asleep: wake now,
                # contend, report, and renegotiate to T_fast in one go
                a = starts[i_start]
                i_start += 1
                e_tot += e_u + e_r
                a_tot += a_u + a_r
                n_w += 1
                n_r += 1
                gen.append(a)
                dlv.append(a + d_u)
                fast, calm_run = True, 0
                last, t = a, a + T_fast
                continue
        last = t
        active = bisect.bisect_right(sw, t) % 2 == 1
        e_tot += e_w
        a_tot += a_w
        n_w += 1
        gen.append(t)
        dlv.append(t + d_w)
        if not fast:
            if active:
                fast, calm_run = True, 0
                e_tot += e_r
                a_tot += a_r
                n_r += 1
                t += T_fast
            else:
                t += T_slow
        else:
            calm_run = 0 if active else calm_run + 1
            if calm_run >= k_calm:
                fast = False
                e_tot += e_r
                a_tot += a_r
                n_r += 1
                t += T_slow
            else:
                t += T_fast

    return _finish(cfg, switch, e_tot, a_tot, n_w, n_r, gen, dlv, compute_aoi)


def tune_slow_interval(policy: dict, cfg: SimConfig, switches: list,
                       p_budget: float, seed: int = 0, iters: int = 18) -> dict:
    """Bisection on T_slow so the adaptive policy's mean power meets p_budget
    (averaged over the given environment realisations). Returns the policy
    with T_slow filled in, or None if even a very long T_slow cannot fit."""
    def power(T_slow):
        p = dict(policy, T_slow=T_slow)
        vals = [simulate_twt(p, cfg, sw, np.random.default_rng(seed + i),
                             compute_aoi=False).avg_power
                for i, sw in enumerate(switches)]
        return float(np.mean(vals))

    lo, hi = policy["T_fast"], 3600.0
    if power(hi) > p_budget:
        return None
    if power(lo) <= p_budget:
        return dict(policy, T_slow=lo)
    for _ in range(iters):
        mid = np.sqrt(lo * hi)
        if power(mid) > p_budget:
            lo = mid
        else:
            hi = mid
    return dict(policy, T_slow=hi)


# --------------------------------------------------------------------------
# Legacy power save, N stations sharing one AP
# --------------------------------------------------------------------------
def simulate_legacy(n_sta: int, T: float, cfg: SimConfig, switches: list,
                    rng: np.random.Generator, listen_interval: float = 10.0,
                    synchronized: bool = False, compute_aoi: bool = True):
    r = cfg.radio
    bi = r.beacon_interval
    m = max(1, int(round(T / bi)))
    n_beacons = int(cfg.horizon / bi)
    phases = np.zeros(n_sta, int) if synchronized else rng.integers(0, m, n_sta)
    idx = [np.arange(p, n_beacons, m) for p in phases]
    counts = np.bincount(np.concatenate(idx), minlength=n_beacons)

    e_listen = r.p_rx * (r.t_wakeup + r.t_beacon)
    a_listen = r.t_wakeup + r.t_beacon
    n_listen = int(cfg.horizon / listen_interval)

    out = []
    for s in range(n_sta):
        k = idx[s]
        e, a, d = legacy_uplink(r, counts[k].astype(float))
        t0 = k * bi
        res = _finish(cfg, switches[s], float(e.sum()) + n_listen * e_listen,
                      float(a.sum()) + n_listen * a_listen, len(k) + n_listen, 0,
                      t0, t0 + d, compute_aoi)
        out.append(res)
    return out


def simulate_twt_many(n_sta: int, T: float, cfg: SimConfig, switches: list,
                      rng: np.random.Generator, compute_aoi: bool = True):
    """N TWT stations with staggered SPs (no contention). Checks the schedule fits."""
    _, a_w, _ = twt_wake(cfg.radio)
    if n_sta * a_w > T:
        raise ValueError(f"{n_sta} SPs of {a_w*1e3:.1f} ms do not fit in T={T}s")
    return [simulate_twt({"kind": "fixed", "T": T}, cfg, switches[s], rng, compute_aoi)
            for s in range(n_sta)]
