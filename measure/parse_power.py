"""Estimate radio power-state parameters from a current trace (measurement study).

Input: a CSV exported from a power analyzer (Joulescope, Otii, Nordic PPK2, or a
shunt + scope) measured on the node's supply, with columns

    time_s, current_a [, voltage_v]

(`current_ma` is also accepted). Supply voltage defaults to --voltage if the
file has no voltage column.

The parser finds wake bursts by thresholding power above the sleep floor, then
splits each burst into a high-power (transmit) part and the rest (wake-up,
listen, ACK). It reports the numbers that `aoitwt/params.py` needs, so the
prototype can be re-run with measured instead of placeholder values:

  python -m measure.parse_power trace.csv --voltage 3.3 --json measured_params.json
"""
from __future__ import annotations

import argparse
import csv
import json

import numpy as np


def load_trace(path: str, voltage: float):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("empty trace")
    t = np.array([float(r["time_s"]) for r in rows])
    if "current_a" in rows[0]:
        i = np.array([float(r["current_a"]) for r in rows])
    elif "current_ma" in rows[0]:
        i = np.array([float(r["current_ma"]) for r in rows]) / 1e3
    else:
        raise ValueError("need a current_a or current_ma column")
    v = (np.array([float(r["voltage_v"]) for r in rows]) if "voltage_v" in rows[0]
         else np.full_like(i, voltage))
    return t, i * v


def find_bursts(t: np.ndarray, p: np.ndarray, k_sleep: float = 5.0, min_gap_s: float = 1e-3):
    """Return (start_idx, end_idx) pairs where power exceeds k_sleep x sleep floor."""
    floor = np.percentile(p, 20)
    thr = max(floor * k_sleep, floor + 1e-3)   # at least 1 mW above floor
    on = p > thr
    edges = np.flatnonzero(np.diff(on.astype(np.int8)))
    starts = list(edges[~on[edges]] + 1)
    ends = list(edges[on[edges]] + 1)
    if on[0]:
        starts.insert(0, 0)
    if on[-1]:
        ends.append(len(p))
    bursts = []
    for s, e in zip(starts, ends):
        if bursts and t[s] - t[bursts[-1][1] - 1] < min_gap_s:
            bursts[-1] = (bursts[-1][0], e)          # merge bursts split by a dip
        else:
            bursts.append((s, e))
    return bursts, floor, thr


def estimate_params(t: np.ndarray, p: np.ndarray, k_sleep: float = 5.0) -> dict:
    bursts, floor, thr = find_bursts(t, p, k_sleep)
    if not bursts:
        raise ValueError("no wake bursts found; check the trace or lower --k-sleep")
    dt = float(np.median(np.diff(t)))
    burst_p = np.concatenate([p[s:e] for s, e in bursts])
    peak = float(np.percentile(burst_p, 95))
    lo = float(np.percentile(burst_p, 10))
    tx_thr = lo + 0.5 * (peak - lo)
    tx_p, rx_p, t_tx, t_rest, e_burst, dur = [], [], [], [], [], []
    for s, e in bursts:
        seg = p[s:e]
        tx = seg > tx_thr
        tx_p.append(seg[tx])
        rx_p.append(seg[~tx])
        t_tx.append(tx.sum() * dt)
        t_rest.append((~tx).sum() * dt)
        e_burst.append(float(seg.sum() * dt))
        dur.append((e - s) * dt)
    sleep_mask = np.ones_like(p, dtype=bool)
    for s, e in bursts:
        sleep_mask[s:e] = False
    starts = np.array([t[s] for s, _ in bursts])
    res = {
        "n_bursts": len(bursts),
        "p_sleep": float(np.median(p[sleep_mask])) if sleep_mask.any() else float(floor),
        "p_rx": float(np.median(np.concatenate(rx_p))) if any(len(x) for x in rx_p) else None,
        "p_tx": float(np.median(np.concatenate(tx_p))) if any(len(x) for x in tx_p) else None,
        "t_tx": float(np.mean(t_tx)),
        "t_awake_non_tx": float(np.mean(t_rest)),   # ~ t_wakeup + t_guard + t_ack
        "burst_duration": float(np.mean(dur)),
        "energy_per_burst_j": float(np.mean(e_burst)),
        "wake_interval_s": float(np.median(np.diff(starts))) if len(starts) > 1 else None,
        "avg_power_w": float(np.trapezoid(p, t) / (t[-1] - t[0])) if hasattr(np, "trapezoid")
        else float(np.trapz(p, t) / (t[-1] - t[0])),
    }
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace")
    ap.add_argument("--voltage", type=float, default=3.3)
    ap.add_argument("--k-sleep", type=float, default=5.0)
    ap.add_argument("--json", help="write estimates to this file")
    a = ap.parse_args(argv)
    t, p = load_trace(a.trace, a.voltage)
    res = estimate_params(t, p, a.k_sleep)
    for k, v in res.items():
        print(f"{k:22s} {v}")
    print("\nSuggested aoitwt/params.py Radio(...) values:")
    print(f"  p_sleep={res['p_sleep']:.3e}, p_rx={res['p_rx']:.3e}, p_tx={res['p_tx']:.3e}, "
          f"t_tx={res['t_tx']:.3e}  # split t_awake_non_tx={res['t_awake_non_tx']:.3e} s "
          f"into t_wakeup / t_guard / t_ack using the trace shape")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
