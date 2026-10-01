"""Tabular epsilon-greedy agent for the joint power/TWT controller.

With gamma=0 (default) this is a contextual bandit, which matches the current
environment (actions do not change the next context). Set gamma>0 once the
state includes action-dependent parts (battery, queue). The learned table is
small and exportable to JSON so the gateway can run it without ML libraries.
"""
from __future__ import annotations

import json

import numpy as np


class QAgent:
    def __init__(self, n_states, n_actions, alpha=0.1, gamma=0.0, eps=0.2,
                 eps_min=0.02, eps_decay=0.9995, seed=0):
        self.Q = np.zeros((n_states, n_actions))
        self.N = np.zeros((n_states, n_actions), dtype=int)
        self.alpha, self.gamma = alpha, gamma
        self.eps, self.eps_min, self.eps_decay = eps, eps_min, eps_decay
        self.rng = np.random.default_rng(seed)

    def act(self, s, greedy=False):
        if not greedy and self.rng.random() < self.eps:
            return int(self.rng.integers(self.Q.shape[1]))
        q = self.Q[s]
        return int(self.rng.choice(np.flatnonzero(q == q.max())))

    def update(self, s, a, r, s2):
        self.N[s, a] += 1
        target = r + self.gamma * self.Q[s2].max()
        lr = max(self.alpha, 1.0 / self.N[s, a])     # fast start, then constant
        self.Q[s, a] += lr * (target - self.Q[s, a])
        self.eps = max(self.eps_min, self.eps * self.eps_decay)

    def to_json(self, path, actions, meta=None):
        with open(path, "w") as f:
            json.dump({"Q": self.Q.round(6).tolist(), "actions": [list(a) for a in actions],
                       "meta": meta or {}}, f)

    @staticmethod
    def greedy_from_json(path):
        with open(path) as f:
            d = json.load(f)
        Q = np.array(d["Q"])
        return Q.argmax(axis=1), d["actions"], d.get("meta", {})
