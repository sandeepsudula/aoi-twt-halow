# Model parameters and their sources

The simulators use **published values**, not measurements from this testbed. They describe the
MM6108 radio module and the STM32U585 MCU that the EKH05 node is built on. Every value marked
*assumption* has no published source. The measurement study (`measure/`) is designed to replace
all of them with numbers measured on the real hardware.

All power values assume a 3.3 V supply.

## Radio and MCU power (`aoitwt/params.py`, `control/env.py`)

| Parameter | Value | Derivation | Source |
|---|---|---|---|
| Sleep floor `p_sleep` | ≈ 35 µW | MCU Stop 2, full SRAM 8.95 µA + radio deep sleep ≈ 1.3 µA (VBAT) + ≈ 0.3 µA (FEM) | [U585-DS], [MM6108-DS] |
| Listen `p_rx` | ≈ 137 mW | VBAT 37 mA + VDD_FEM 4.5 mA (figure given for an 8 MHz channel) | [MM6108-DS] |
| Transmit `p_tx` (MCS0, ≈ 20–22 dBm) | ≈ 743 mW | VBAT 78 mA + VDD_FEM 147 mA (8 MHz channel) | [MM6108-DS] |
| Radio core while transmitting | ≈ 257 mW | VBAT 78 mA | [MM6108-DS] |
| PA efficiency | ≈ 0.21 | 0.1 W RF out / 0.485 W FEM supply; FEM bias at low output neglected | derived from [MM6108-DS], *assumption* |
| Max TX power | 20 dBm | 1–2 MHz MCS0 output 20–22 dBm at VDD_FEM = 3.3 V | [MM6108-DS] |

## PHY (`control/env.py`)

| Parameter | Value | Source |
|---|---|---|
| 1 MHz rates, MCS10/0–7 | 0.15 / 0.3, 0.6, 0.9, 1.2, 1.8, 2.4, 2.7, 3.0 Mb/s (8 µs GI, 1 SS) | [11ah-MCS] |
| MCS0 sensitivity, 1 MHz | −105 dBm at 10 % PER | [MM6108-DS] |
| Per-MCS sensitivity steps | +0, 3, 5, 8, 12, 16, 17, 18 dB (MCS0–7) | 802.11 minimum-sensitivity table [11ac-sens] |
| MCS10 vs MCS0 | 3 dB more sensitive | [Range-ext] |
| Noise floor, 1 MHz | −109 dBm (−174 dBm/Hz + 60 dB + 5 dB station NF) | NF from [Range-ext] |
| Path loss, outdoor | PL = 23.3 + 36.7 log10(d) dB (TGah pico/hot-zone, 900 MHz) | [Range-ext] |
| Shadowing σ, correlation | 6 dB, ρ = 0.9 per epoch | *assumption* |

Cross-check: the MM6108 data sheet gives −77 dBm for MCS7 at 8 MHz, which implies about −86 dBm at
1 MHz (9 dB less noise bandwidth); the derived table gives −87 dBm.

## Timing (`aoitwt/params.py`)

| Parameter | Value | Basis |
|---|---|---|
| `t_tx` | 6 ms | 200 B at MCS0 1 MHz (0.3 Mb/s) = 5.3 ms + ≈ 0.6 ms S1G 1 MHz preamble [11ah-MCS] |
| `t_wakeup`, `t_guard`, `t_ack`, `t_ctrl_tx`, `t_backoff` | 2, 2, 1, 2, 1 ms | *assumption* |

## Known gaps
- Receive and transmit currents in [MM6108-DS] are specified for an 8 MHz channel; 1 MHz operation
  likely draws somewhat less in receive. The model therefore likely **overestimates** awake energy.
- Board-level losses on the EKH05 (regulators, LEDs, camera, debug circuitry) are not included in
  the sleep floor and can dominate it on an evaluation board.

## Sources
- **[MM6108-DS]** Morse Micro, *MM6108-MF08651-US module data sheet* — https://www.morsemicro.com/resources/datasheets/modules/MM6108-MF08651-US_Data_Sheet.pdf
- **[U585-DS]** STMicroelectronics, *STM32U585xx data sheet (DS13086)* — https://www.st.com/resource/en/datasheet/stm32u585ai.pdf
- **[11ah-MCS]** IEEE 802.11ah MCS table (1 MHz) — https://en.wikipedia.org/wiki/IEEE_802.11ah
- **[11ac-sens]** 802.11ac minimum receiver sensitivity per MCS (MathWorks reference) — https://www.mathworks.com/help/wlan/ug/802-11ac-receiver-minimum-input-sensitivity-test.html
- **[Range-ext]** *Range Extension in IEEE 802.11ah Systems Through Relaying* (TGah path-loss models, noise figures, MCS10) — https://arxiv.org/pdf/1812.06731
