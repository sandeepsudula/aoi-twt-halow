# Research plan

**Question.** Under a fixed per-station energy budget, how should 802.11ah stations choose and adapt
their TWT schedules to keep the AP's view of the world fresh — especially when freshness matters most?

**Claimed contributions (target).**
1. An AoI-under-energy-budget formulation of TWT scheduling for 802.11ah, with state-weighted AoI.
2. Event-driven TWT adaptation (interval switching + unscheduled event wake) and its cost model
   (renegotiation, contention outside the SP).
3. Validation on a real MM6108 HaLow testbed, including how far simulation and hardware disagree.

## Milestones

| # | Milestone | Output | Target |
|---|---|---|---|
| M0 | Prototype simulator + first trends | this repo, `results/` | done |
| M1 | Testbed baseline: gateway + 2 nodes talking; measure power per state, wake/transition times, TWT support in MM6108 firmware | `testbed/` measurements, updated `params.py` | +3 weeks |
| M2 | Re-run prototype with measured parameters; add PHY errors/retries and SP-capacity limits | updated results | +1 week |
| M3 | ns-3 scenario with 802.11ah (see ns3.md): fixed vs adaptive TWT, N stations, contention | `ns3/` | +5 weeks |
| M4 | Policy design: beyond two intervals — threshold / index policy on predicted AoI cost; compare with an RL agent (ns3-ai) | results + short write-up | +4 weeks |
| M5 | Hardware validation of best 2–3 policies (energy + AoI measured end to end) | testbed results | +4 weeks |
| M6 | Workshop / conference paper draft | paper | +3 weeks |

## Open questions to settle early
- Does the MM6108 firmware on the EKH05 node expose individual TWT setup / renegotiation? What is the minimum wake interval and SP length?
- What does an unscheduled wake actually cost on the hardware (wake-up time, association state, contention)?
- Which ns-3 802.11ah implementation is usable with a current ns-3, or is an 802.11ax TWT model with sub-GHz PHY parameters a better proxy?
- Which AoI weighting is defensible? Consider tying weights to a real application metric (e.g. cost of late detection).

## Prototype findings to follow up
- The best `T_fast` in every budget was the largest one tried (`T_opt/2`) — widen the search and optimize `k_calm` too.
- The ~10 ms event-wake latency assumes an idle channel and ideal sensing; quantify with contention and sensing delay.
