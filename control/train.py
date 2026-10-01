"""Train the joint power + TWT controller and compare with baselines.

  python -m control.train      # writes results/c1_*.png, results/c1_summary.csv,
                               # results/control_qtable.json

Baselines (same environment, same random seeds for evaluation):
  max-power   : highest TX power, fixed interval that best balances the reward
  min-power   : lowest TX power, same idea
  best-fixed  : best single (power, interval) pair found by exhaustive search
  oracle      : picks the best action every epoch knowing the true SNR (upper bound)
"""
from __future__ import annotations

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from control.agent import QAgent  # noqa: E402
from control.env import EnvConfig, JointControlEnv  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")


def train(episodes=60, epochs_per_episode=1440, seed=0, cfg=None):
    env = JointControlEnv(cfg, seed=seed)
    agent = QAgent(env.n_states, env.n_actions, seed=seed)
    curve = []
    for ep in range(episodes):
        s = env.reset()
        tot = 0.0
        for _ in range(epochs_per_episode):
            a = agent.act(s)
            s2, r, _ = env.step(a)
            agent.update(s, a, r, s2)
            s, tot = s2, tot + r
        curve.append(tot / epochs_per_episode)
    return env, agent, np.array(curve)


def evaluate(policy, cfg=None, seeds=range(100, 110), epochs=1440):
    """policy(env, s) -> action index. Returns mean metrics over seeds."""
    R, A, WA, P, Q, AA = [], [], [], [], [], []
    for sd in seeds:
        env = JointControlEnv(cfg, seed=sd)
        s = env.reset()
        for _ in range(epochs):
            a = policy(env, s)
            s, r, info = env.step(a)
            R.append(r); A.append(info["aoi"]); WA.append(info["w_aoi"])
            P.append(info["p_avg"]); Q.append(info["q"])
            if info["active"]:
                AA.append(info["aoi"])
    return {"reward": np.mean(R), "aoi_s": np.mean(A), "aoi_active_s": np.mean(AA) if AA else np.nan,
            "w_aoi": np.mean(WA), "power_mw": np.mean(P) * 1e3, "delivery": np.mean(Q)}


def best_fixed(cfg=None, power_filter=None):
    env = JointControlEnv(cfg, seed=999)
    cand = [i for i, (p, _) in enumerate(env.actions) if power_filter is None or power_filter(p)]
    scores = {i: evaluate(lambda e, s, i=i: i, cfg, seeds=range(900, 905), epochs=1440)["reward"]
              for i in cand}
    return max(scores, key=scores.get)


def main():
    os.makedirs(OUT, exist_ok=True)
    cfg = EnvConfig()
    env, agent, curve = train(cfg=cfg)
    agent.to_json(os.path.join(OUT, "control_qtable.json"), env.actions,
                  meta={"snr_bins_db": list(cfg.snr_bins_db), "epoch_s": cfg.epoch_s,
                        "state": "snr_bucket*2 + active", "note": "published data-sheet parameters (docs/parameters.md), not testbed measurements"})

    pmax, pmin = max(cfg.power_levels_dbm), min(cfg.power_levels_dbm)
    i_max = best_fixed(cfg, lambda p: p == pmax)
    i_min = best_fixed(cfg, lambda p: p == pmin)
    i_fix = best_fixed(cfg)
    policies = {
        f"max-power {env.actions[i_max]}": lambda e, s: i_max,
        f"min-power {env.actions[i_min]}": lambda e, s: i_min,
        f"best-fixed {env.actions[i_fix]}": lambda e, s: i_fix,
        "learned (Q)": lambda e, s: agent.act(s, greedy=True),
        "oracle": lambda e, s: e.oracle_action(),
    }
    rows = []
    for name, pol in policies.items():
        m = evaluate(pol, cfg)
        rows.append({"policy": name, **m})
        print(name, {k: round(v, 4) for k, v in m.items()})
    with open(os.path.join(OUT, "c1_summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    fig, ax = plt.subplots(figsize=(5.5, 4))
    ax.plot(curve)
    ax.set_xlabel("Training episode (1 day each)")
    ax.set_ylabel("Mean reward per epoch")
    ax.set_title("Joint power + TWT controller: learning curve")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "c1_learning_curve.png"), dpi=90)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    names = [r["policy"] for r in rows]
    for ax, (key, label, sign) in zip(axes, [("aoi_active_s", "Mean AoI, active periods (s)", 1),
                                             ("power_mw", "Average power (mW)", 1),
                                             ("reward", "Cost = -reward (lower is better)", -1)]):
        ax.barh(names, [sign * r[key] for r in rows])
        ax.set_xscale("log")
        ax.set_xlabel(label)
        ax.grid(True, axis="x", which="both", alpha=0.3)
    for ax in axes[1:]:
        ax.set_yticklabels([])
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "c1_policy_comparison.png"), dpi=90)


if __name__ == "__main__":
    main()
