"""Gateway-side controller loop for sim-to-real deployment.

Runs on the OpenWrt HaLow gateway (or a host next to it). Every epoch it:
  1. reads each node's signal from `iw dev <iface> station dump`,
  2. builds the same discrete context the simulator used
     (SNR bucket = signal - noise floor, plus the node's last reported
     calm/active flag),
  3. looks up the greedy action in the Q-table trained in simulation
     (results/control_qtable.json), and
  4. sends the node a small UDP JSON command:
        {"cmd": "set", "tx_power_dbm": 15.0, "twt_interval_s": 5.0, "epoch": 42}

The NODE side is not part of this repo yet: the EKH05 firmware needs a UDP
handler that applies the TX power and renegotiates the TWT agreement, and that
reports {"active": true/false} back (here read from --state-file or a UDP
port). Until then use --dry-run to log decisions only.

  python3 gateway_agent.py --qtable control_qtable.json --iface wlan0 \
      --node 0c:bf:74:00:00:01=10.42.0.50 --dry-run

Only standard-library Python, so it can run on the gateway's Python.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import time
from bisect import bisect_left


def read_station_signals(iface: str) -> dict:
    out = subprocess.run(["iw", "dev", iface, "station", "dump"],
                         capture_output=True, text=True).stdout
    sig = {}
    for block in re.split(r"(?m)^Station\s+", out):
        if not block.strip():
            continue
        mac = block.split()[0].lower()
        m = re.search(r"signal:\s*(-?\d+)", block)
        if m:
            sig[mac] = int(m.group(1))
    return sig


def load_qtable(path: str):
    with open(path) as f:
        d = json.load(f)
    greedy = [max(range(len(row)), key=row.__getitem__) for row in d["Q"]]
    return greedy, d["actions"], d.get("meta", {})


def context(signal_dbm: float, noise_floor_dbm: float, bins, active: bool) -> int:
    snr = signal_dbm - noise_floor_dbm
    return bisect_left(bins, snr) * 2 + int(active)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qtable", required=True)
    ap.add_argument("--iface", default="wlan0")
    ap.add_argument("--node", action="append", required=True, help="MAC=IP, repeatable")
    ap.add_argument("--port", type=int, default=5005, help="node UDP command port")
    ap.add_argument("--noise-floor-dbm", type=float, default=-109.0)
    ap.add_argument("--state-file", help="JSON {mac: true/false} with each node's active flag")
    ap.add_argument("--epoch-s", type=float, help="override the epoch length from the Q-table")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)

    greedy, actions, meta = load_qtable(a.qtable)
    bins = meta.get("snr_bins_db", [0, 5, 10, 15, 20, 30])
    epoch_s = a.epoch_s or meta.get("epoch_s", 60)
    nodes = dict(n.lower().split("=", 1) for n in a.node)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    k = 0
    while True:
        sig = read_station_signals(a.iface)
        state = {}
        if a.state_file:
            try:
                with open(a.state_file) as f:
                    state = {m.lower(): bool(v) for m, v in json.load(f).items()}
            except (OSError, ValueError):
                state = {}
        for mac, ip in nodes.items():
            if mac not in sig:
                print(f"[{k}] {mac}: not associated")
                continue
            s = context(sig[mac], a.noise_floor_dbm, bins, state.get(mac, False))
            p_dbm, T = actions[greedy[s]]
            msg = {"cmd": "set", "tx_power_dbm": p_dbm, "twt_interval_s": T, "epoch": k}
            print(f"[{k}] {mac} signal={sig[mac]} dBm ctx={s} -> {msg}")
            if not a.dry_run:
                sock.sendto(json.dumps(msg).encode(), (ip, a.port))
        k += 1
        if a.once:
            break
        time.sleep(epoch_s)


if __name__ == "__main__":
    main()
