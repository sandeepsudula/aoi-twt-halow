# ns-3 phase notes (phase 2)

Goal: reproduce the prototype's policies with a real MAC (contention, retries, beacons, SP scheduling)
and many stations.

## Options to evaluate (verify each before committing)
1. **A third-party 802.11ah module for ns-3.** Research groups have published 802.11ah (RAW, TIM, TWT-related)
   implementations for ns-3; check which ones still build with a recent ns-3 and whether they include TWT.
2. **Stock ns-3 Wi-Fi as a proxy.** Use the current ns-3 Wi-Fi module's power-save / TWT support (check the
   release notes for what exists in the version you install) with timing and rates set to sub-GHz 1–2 MHz values.
   Easier to maintain, but not 802.11ah-accurate — must be stated as a limitation.

## Scenario to implement first
- 1 AP, N ∈ {10, 50, 200} stations, uplink generate-at-will updates.
- Policies: legacy PS, fixed TWT (budget-optimal), adaptive TWT, adaptive + event wake.
- Environment process per station driven from Python (ns3-ai) so the same traces feed prototype, ns-3 and testbed.
- Metrics: per-station energy (ns-3 energy framework with measured currents), AoI at AP, detection latency.

## Check against the prototype
Single station, no contention: ns-3 AoI and energy should match `aoitwt` within a few percent.
Disagreements beyond that point to a modeling error in one of the two.
