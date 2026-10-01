# Joint TX-power + TWT controller, sim-to-real (extension)

**Idea.** One controller per gateway picks, for each HaLow node, the **TX power** and the **TWT wake
interval** together. Lower power saves energy per transmission but costs retries and freshness; longer
sleep saves energy but ages the data. The controller is trained in simulation and then run on the real
OpenWrt gateway against MM6108 nodes.

## What exists now (`control/`)

| File | What it does |
|---|---|
| `env.py` | Link (log-distance + AR(1) shadowing, node mobility) → SNR → MCS + PER → energy and AoI per decision epoch. Context = SNR bucket (what the gateway sees in `iw station dump`) + calm/active flag. |
| `agent.py` | Tabular ε-greedy learner (γ = 0 → contextual bandit), exports a JSON Q-table. |
| `train.py` | Trains, compares with fixed baselines and an oracle, writes `results/c1_*`. |
| `deploy/gateway_agent.py` | Standard-library loop for the gateway: reads `iw station dump`, builds the same context, sends UDP `{"tx_power_dbm", "twt_interval_s"}` commands to nodes (`--dry-run` to only log). |

First result (published MM6108 / 802.11ah parameters, docs/parameters.md; 10 simulated days per policy):
against the best fixed (power, interval) pair the learned controller lowers mean AoI during active periods from
~12.0 s to ~6.4 s and average power from ~0.86 to ~0.71 mW; an SNR-aware oracle is still 14 % better
(`results/c1_summary.csv`). It sleeps longer when calm, so overall average AoI is higher (10.2 vs 8.2 s).

## Roadmap

1. **Calibrate** `env.py` with the measurement study: path-loss exponent and shadowing σ from
   `measure/analyze.py`, per-state power and PA cost vs TX power from `measure/parse_power.py`,
   SNR thresholds per MCS from the measured PER vs signal.
2. **ns-3 + ns3-ai backend.** Replace the analytic link with ns-3 (802.11ah module or sub-GHz-parameterized
   Wi-Fi) through ns3-ai, keeping the same interface:
   - observation per node: `[snr_db_last_epoch, active_flag, aoi_last_epoch, energy_last_epoch]`
   - action per node: `[tx_power_index, twt_interval_index]`
   - reward: `-(w·AoI/aoi_ref) - λ·P/p_ref`
   With a richer state (battery, queue, neighbours) move from the bandit to a DRL agent (e.g. PPO).
3. **Node firmware** (EKH05): UDP handler that applies TX power, renegotiates the TWT agreement, and reports
   `active` plus a sequence number/timestamp for AoI measurement.
4. **Sim-to-real.** Run `gateway_agent.py` with the trained table; measure real AoI and energy; quantify the
   sim-to-real gap and fine-tune online (the agent supports continued updates).

## Honest limitations of the current prototype
- Expected-value outcomes, no contention between nodes, no interference — single-node control only.
- Link and power numbers are published data-sheet / model values (docs/parameters.md), not testbed
  measurements; shadowing and several timings are assumptions.
- The node-side command handler does not exist yet; deployment is `--dry-run` until it does.
