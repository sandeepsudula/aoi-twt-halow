# HaLow measurement study (do this first)

**Goal.** Characterize the MM6108 HaLow link and per-node energy in realistic settings, and produce the
measured parameters that AoI-aware TWT work and the joint power + TWT controller need.

## Scenarios

| ID | Setting | Variable | Points |
|---|---|---|---|
| S1 indoor | node and gateway in one building | distance, number of walls (0–4) | 5–10 positions |
| S2 outdoor LoS | open field / campus | distance 10 m → max range | step until loss > 50 % |
| S3 outdoor NLoS | behind buildings / trees | distance | 5+ positions |
| S4 dense | 1 gateway, N nodes (as many EKH05 as available, plus traffic generators) | N, reporting rate | N = 1, 2, 4, max |
| S5 energy | fixed position | TWT wake interval, payload, MCS / TX power | 5 × 3 × 3 |

Record for every point: bandwidth (1/2/4 MHz), channel, TX power, MCS if fixed, antenna, heights, weather (outdoor).

## Metrics and tools

| Metric | Tool |
|---|---|
| Signal, bitrate, retries, failures | `iw dev <iface> station dump` on the gateway (`measure/collect.py`) |
| RTT, loss | `ping` with ~200 B payload (`measure/collect.py`) |
| Throughput | `iperf3` TCP and fixed-rate UDP (`--iperf`, `--udp-mbps`) |
| Per-state power, wake timing | power analyzer on the node supply → `measure/parse_power.py` |
| End-to-end AoI | sequence number + generation timestamp in each update, clocks synced (docs/testbed.md) |

## Procedure

1. Bring-up (docs/testbed.md). Confirm the HaLow interface name with `iw dev` on the gateway.
2. For each position: `python -m measure.collect --scenario S1-2walls --distance-m 15 --walls 2 --target <node-ip> --gateway 10.42.0.1 --iface <iface> --iperf --repeats 5 --out data/links.csv`
3. Energy (S5): record a current trace per configuration, then
   `python -m measure.parse_power trace.csv --voltage 3.3 --json data/energy_<cfg>.json`.
4. `python -m measure.analyze data/links.csv --out results/measure` for the summary table and plots.
5. Copy the measured power/timing values into `aoitwt/params.py`, replacing the placeholders, and re-run
   `python -m experiments.run_all` and `python -m control.train`.

## Deliverables
- `data/links.csv`, `data/energy_*.json` (raw), `results/measure_summary.csv`, `results/measure_links.png`
- Fitted path-loss model (exponent, shadowing σ) for the controller's link model (`control/env.py`)
- A short measurement report → workshop paper or the measurement section of the main paper

## Open items to check on the hardware
- Does the EKH05 firmware expose TWT setup/teardown and TX power to the application?
- Which station statistics does the MM6108 driver report in `iw station dump`?
