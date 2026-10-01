import json

import numpy as np

from control.agent import QAgent
from control.deploy.gateway_agent import context, load_qtable
from control.env import EnvConfig, JointControlEnv
from control.train import evaluate, train


def test_outcome_basic_trends():
    env = JointControlEnv(seed=1)
    env.d, env.shadow = 300.0, 0.0
    # max TX power delivers at least as reliably as min power (in between, rate
    # adaptation may step up an MCS and trade a little reliability for airtime)
    assert env.outcome(20.0, 5.0)[3] >= env.outcome(0.0, 5.0)[3]
    # longer interval -> lower average power, higher AoI
    o1, o2 = env.outcome(20.0, 1.0), env.outcome(20.0, 10.0)
    assert o2[2] < o1[2] and o2[1] > o1[1]


def test_aoi_capped_when_link_down():
    env = JointControlEnv(seed=1)
    env.d, env.shadow = 600.0, 30.0
    assert env.outcome(0.0, 30.0)[1] <= env.cfg.aoi_cap


def test_learned_policy_beats_best_fixed_and_is_near_oracle():
    cfg = EnvConfig()
    env, agent, curve = train(cfg=cfg)
    seeds = range(200, 203)
    learned = evaluate(lambda e, s: agent.act(s, greedy=True), cfg, seeds, 800)["reward"]
    oracle = evaluate(lambda e, s: e.oracle_action(), cfg, seeds, 800)["reward"]
    i_max = max(i for i, (p, T) in enumerate(env.actions) if p == 20.0 and T == 5.0)
    fixed = evaluate(lambda e, s: i_max, cfg, seeds, 800)["reward"]
    assert learned > fixed
    assert learned >= oracle * 1.2   # rewards are negative: within 20 % of oracle


def test_qtable_roundtrip_and_gateway_context(tmp_path):
    env = JointControlEnv(seed=0)
    ag = QAgent(env.n_states, env.n_actions)
    ag.Q[3, 7] = 1.0
    p = tmp_path / "q.json"
    ag.to_json(p, env.actions, meta={"snr_bins_db": list(env.cfg.snr_bins_db), "epoch_s": 60})
    greedy, actions, meta = load_qtable(p)
    assert greedy[3] == 7 and len(actions) == env.n_actions
    # gateway context must match the simulator's encoding
    for sig in (-100.0, -95.0, -88.0, -70.0):
        for act in (False, True):
            env.last_snr, env.active = sig - env.cfg.link.noise_floor_dbm, act
            assert context(sig, env.cfg.link.noise_floor_dbm, meta["snr_bins_db"], act) == env.observe()
    json.loads(p.read_text())
