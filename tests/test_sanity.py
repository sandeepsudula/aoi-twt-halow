import numpy as np

from aoitwt.params import SimConfig
from aoitwt.sim import (budget_optimal_interval, gen_switch_times, simulate_twt,
                        tune_slow_interval, twt_wake)

CFG = SimConfig(horizon=6 * 3600.0)


def test_fixed_aoi_matches_analytic():
    # Periodic generate-at-will updates: mean AoI = T/2 + delivery delay.
    T = 10.0
    _, _, d = twt_wake(CFG.radio)
    rng = np.random.default_rng(1)
    res = simulate_twt({"kind": "fixed", "T": T}, CFG, np.array([]), rng)
    assert abs(res.mean_aoi - (T / 2 + d)) < 0.05


def test_budget_optimal_meets_budget():
    for p in [0.2e-3, 0.5e-3, 1e-3]:
        T = budget_optimal_interval(CFG.radio, p)
        res = simulate_twt({"kind": "fixed", "T": T}, CFG, np.array([]),
                           np.random.default_rng(0), compute_aoi=False)
        assert res.avg_power <= p * 1.01


def test_adaptive_tuned_meets_budget():
    sws = [gen_switch_times(CFG, np.random.default_rng(s)) for s in range(3)]
    p_budget = 0.5e-3
    pol = tune_slow_interval({"kind": "adaptive", "T_fast": 1.0, "k_calm": 3,
                              "event_wake": True}, CFG, sws, p_budget)
    assert pol is not None
    pw = np.mean([simulate_twt(pol, CFG, sw, np.random.default_rng(i),
                               compute_aoi=False).avg_power
                  for i, sw in enumerate(sws)])
    assert pw <= p_budget * 1.001
