"""Summarize and plot a HaLow link dataset collected with measure/collect.py.

  python -m measure.analyze data/links.csv --out results/measure

Writes  <out>_summary.csv  (mean/std per scenario and distance) and
        <out>_links.png    (signal, loss, RTT, throughput vs distance per scenario).
"""
from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

METRICS = [("signal_dbm", "Signal (dBm)"), ("loss_pct", "Packet loss (%)"),
           ("rtt_avg_ms", "Mean RTT (ms)"), ("tput_mbps", "Throughput (Mb/s)")]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def summarize(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for r in rows:
        groups[(r["scenario"], _f(r["distance_m"]))].append(r)
    out = []
    for (sc, d), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        row = {"scenario": sc, "distance_m": d, "n": len(rs)}
        for m, _ in METRICS:
            v = np.array([_f(r.get(m)) for r in rs])
            v = v[~np.isnan(v)]
            row[f"{m}_mean"] = float(v.mean()) if len(v) else np.nan
            row[f"{m}_std"] = float(v.std()) if len(v) else np.nan
        out.append(row)
    return out


def plot(summary: list[dict], path: str) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    scen = sorted({r["scenario"] for r in summary})
    for ax, (m, label) in zip(axes.flat, METRICS):
        for sc in scen:
            rr = [r for r in summary if r["scenario"] == sc]
            ax.errorbar([r["distance_m"] for r in rr], [r[f"{m}_mean"] for r in rr],
                        yerr=[r[f"{m}_std"] for r in rr], marker="o", capsize=3, label=sc)
        ax.set_xlabel("Distance (m)")
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.3)
    axes.flat[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=90)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--out", default="results/measure")
    a = ap.parse_args(argv)
    with open(a.csv) as f:
        rows = list(csv.DictReader(f))
    s = summarize(rows)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out + "_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(s[0].keys()))
        w.writeheader()
        w.writerows(s)
    plot(s, a.out + "_links.png")
    print(f"{len(rows)} rows -> {len(s)} groups; wrote {a.out}_summary.csv and {a.out}_links.png")


if __name__ == "__main__":
    main()
