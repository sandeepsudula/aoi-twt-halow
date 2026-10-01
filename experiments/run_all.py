"""First experiments for the AoI-aware TWT prototype.

  python -m experiments.run_all          # writes CSVs + PNGs to results/

E1  State-weighted AoI vs energy budget: budget-optimal fixed TWT vs
    adaptive TWT vs adaptive TWT with event wake (same power budget).
E2  Detection latency (onset of 'active' -> first fresh update delivered)
    at one budget.
E3  Legacy power save vs individual TWT as the number of stations grows
    (fixed 60 s reporting period).
"""
from __future__ import annotations

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from aoitwt.params import SimConfig  # noqa: E402
from aoitwt.sim import (budget_optimal_interval, gen_switch_times,  # noqa: E402
                        simulate_legacy, simulate_twt, simulate_twt_many,
                        tune_slow_interval)

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
CFG = SimConfig()
N_SEEDS = 5
BUDGETS_MW = [0.15, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0]
FAST_FRACTIONS = [1 / 2, 1 / 4, 1 / 8, 1 / 16]


def _switches(n, base=1000):
    return [gen_switch_times(CFG, np.random.default_rng(base + s)) for s in range(n)]


def _evaluate(policy, switches):
    rs = [simulate_twt(policy, CFG, sw, np.random.default_rng(7 + i))
          for i, sw in enumerate(switches)]
    lat = np.concatenate([r.det_latency for r in rs])
    lat = lat[~np.isnan(lat)]
    return dict(
        power_mw=np.mean([r.avg_power for r in rs]) * 1e3,
        weighted_aoi=np.mean([r.weighted_aoi for r in rs]),
        mean_aoi=np.mean([r.mean_aoi for r in rs]),
        aoi_active=np.mean([r.mean_aoi_active for r in rs]),
        lat_mean=lat.mean(), lat_p95=np.percentile(lat, 95),
        reneg_per_h=np.mean([r.n_reneg for r in rs]) / (CFG.horizon / 3600),
    ), lat


def _best_adaptive(p_budget, switches, event_wake):
    T_opt = budget_optimal_interval(CFG.radio, p_budget)
    best = None
    for f in FAST_FRACTIONS:
        pol = tune_slow_interval({"kind": "adaptive", "T_fast": T_opt * f,
                                  "k_calm": 3, "event_wake": event_wake},
                                 CFG, switches, p_budget, seed=7)
        if pol is None:
            continue
        m, lat = _evaluate(pol, switches)
        if best is None or m["weighted_aoi"] < best[1]["weighted_aoi"]:
            best = (pol, m, lat)
    return best


def e1_e2():
    sws = _switches(N_SEEDS)
    rows, lats = [], {}
    for b in BUDGETS_MW:
        p = b * 1e-3
        T = budget_optimal_interval(CFG.radio, p)
        m, lat = _evaluate({"kind": "fixed", "T": T}, sws)
        rows.append(dict(budget_mw=b, policy="fixed", T=T, T_fast="", **m))
        lats[(b, "fixed")] = lat
        for ev, name in [(False, "adaptive"), (True, "adaptive+event")]:
            best = _best_adaptive(p, sws, ev)
            if best is None:
                continue
            pol, m, lat = best
            rows.append(dict(budget_mw=b, policy=name, T=pol["T_slow"],
                             T_fast=pol["T_fast"], **m))
            lats[(b, name)] = lat
        print(f"budget {b} mW done")

    with open(os.path.join(OUT, "e1_aoi_vs_budget.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    for name, mk in [("fixed", "o-"), ("adaptive", "s-"), ("adaptive+event", "^-")]:
        rr = [r for r in rows if r["policy"] == name]
        ax[0].plot([r["power_mw"] for r in rr], [r["weighted_aoi"] for r in rr], mk, label=name)
        ax[1].plot([r["power_mw"] for r in rr], [r["aoi_active"] for r in rr], mk, label=name)
    for a, t in zip(ax, ["State-weighted mean AoI", "Mean AoI during active periods"]):
        a.set_xscale("log"); a.set_yscale("log")
        a.set_xlabel("Average power per station (mW)"); a.set_ylabel("AoI (s)")
        a.set_title(t); a.grid(True, which="both", alpha=0.3); a.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "e1_aoi_vs_budget.png"), dpi=90)

    b = 0.5
    fig, ax = plt.subplots(figsize=(5.5, 4))
    for name in ["fixed", "adaptive", "adaptive+event"]:
        if (b, name) in lats:
            x = np.sort(lats[(b, name)])
            ax.plot(x, np.arange(1, len(x) + 1) / len(x), label=name)
    ax.set_xscale("log"); ax.set_xlabel("Detection latency (s)")
    ax.set_ylabel("CDF"); ax.set_title(f"Onset -> fresh update delivered ({b} mW budget)")
    ax.grid(True, which="both", alpha=0.3); ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "e2_detection_latency_cdf.png"), dpi=90)
    return rows


def e3():
    T = 60.0
    ns = [1, 5, 10, 25, 50, 100, 200]
    rows = []
    for n in ns:
        sws = _switches(n, base=5000)
        for name, fn in [
            ("legacy (random phase)", lambda: simulate_legacy(n, T, CFG, sws, np.random.default_rng(3), synchronized=False, compute_aoi=False)),
            ("legacy (synchronized)", lambda: simulate_legacy(n, T, CFG, sws, np.random.default_rng(3), synchronized=True, compute_aoi=False)),
            ("individual TWT", lambda: simulate_twt_many(n, T, CFG, sws, np.random.default_rng(3), compute_aoi=False)),
        ]:
            rs = fn()
            rows.append(dict(n_sta=n, policy=name,
                             power_mw=np.mean([r.avg_power for r in rs]) * 1e3))
    with open(os.path.join(OUT, "e3_legacy_vs_twt.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    fig, ax = plt.subplots(figsize=(5.5, 4))
    for name, mk in [("legacy (random phase)", "o-"), ("legacy (synchronized)", "s-"), ("individual TWT", "^-")]:
        rr = [r for r in rows if r["policy"] == name]
        ax.plot([r["n_sta"] for r in rr], [r["power_mw"] for r in rr], mk, label=name)
    ax.set_xscale("log"); ax.set_xlabel("Stations per AP")
    ax.set_ylabel("Average power per station (mW)")
    ax.set_title("60 s reporting period"); ax.grid(True, which="both", alpha=0.3); ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "e3_legacy_vs_twt.png"), dpi=90)
    return rows


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    rows = e1_e2()
    for r in rows:
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    for r in e3():
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
