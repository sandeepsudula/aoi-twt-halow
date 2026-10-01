# Testbed procedure (phase 1)

Hardware: MM6108-EKH01 gateway (RPi 4 + MM6108-A1, OpenWrt) and MM6108-EKH05 nodes (STM32U585 + MM6108).

## 1. Bring-up
1. Gateway: SSH in (default 10.42.0.1), configure the HaLow AP (channel, bandwidth, SSID, security).
2. Node: flash firmware from STM32CubeIDE with the gateway/node IPs set in `configs.c`; confirm association.
3. Send periodic UDP status updates (fixed payload, e.g. 200 B) from node to gateway; log at the gateway
   with receive timestamps.

## 2. Measure the parameters in `aoitwt/params.py`
Measure node current with a power analyzer or shunt + scope (e.g. Joulescope / Otii / Nordic PPK2) on the node's supply:

| Parameter | How |
|---|---|
| `p_sleep` | node idle between TWT SPs, steady state |
| `p_rx`, `t_wakeup`, `t_guard` | current trace around SP start |
| `p_tx`, `t_tx` | burst during update transmission; check vs payload size and MCS |
| `t_ack`, `t_ctrl_tx` | from trace + gateway packet capture |
| unscheduled wake cost | trigger a GPIO event, measure energy until back to sleep |

Repeat each measurement ≥ 10×, report mean and spread; record MCS, bandwidth, distance, TX power.

## 3. TWT on hardware
- Check whether individual TWT can be requested from the node firmware and which parameters
  (wake interval, SP duration, renegotiation) are exposed.
- Measure real end-to-end AoI: put a sequence number + generation timestamp in each update,
  sync clocks (PTP/NTP or GPIO-triggered timestamping), compute AoI at the gateway.

## 4. Output
`testbed/measurements/*.csv` + a short note, then update `params.py` and re-run `experiments/`.
