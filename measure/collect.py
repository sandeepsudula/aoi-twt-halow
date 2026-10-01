"""Collect one measurement point of a HaLow link.

Run from a laptop (or the gateway) that can reach the HaLow node over IP:

  python -m measure.collect --scenario indoor-2walls --distance-m 15 \
      --target 10.42.0.50 --gateway 10.42.0.1 --iface wlan0 --out data/links.csv

For each point it records:
  * latency / loss  : `ping` (count, interval configurable)
  * throughput      : `iperf3 -J` against an iperf3 server on the target (optional)
  * link state      : `iw dev <iface> station dump` on the gateway over SSH
                      (signal, tx/rx bitrate, retries, failures) — standard
                      Linux/OpenWrt output; check the HaLow interface name on
                      your gateway first (`iw dev`).

Every value is appended as one CSV row together with the scenario metadata,
so repeated runs build up a dataset that measure/analyze.py can plot.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Parsers (pure functions, unit-tested in tests/test_measure.py)
# --------------------------------------------------------------------------
_LOSS = re.compile(r"([\d.]+)% packet loss")
_RTT = re.compile(r"=\s*([\d.]+)/([\d.]+)/([\d.]+)(?:/([\d.]+))?\s*ms")


def parse_ping(text: str) -> dict:
    """Parse Linux/macOS/BusyBox ping summary lines."""
    out = {"loss_pct": None, "rtt_min_ms": None, "rtt_avg_ms": None,
           "rtt_max_ms": None, "rtt_mdev_ms": None}
    m = _LOSS.search(text)
    if m:
        out["loss_pct"] = float(m.group(1))
    m = _RTT.search(text)
    if m:
        out["rtt_min_ms"], out["rtt_avg_ms"], out["rtt_max_ms"] = map(float, m.groups()[:3])
        if m.group(4):
            out["rtt_mdev_ms"] = float(m.group(4))
    return out


def parse_iperf3(text: str) -> dict:
    """Parse `iperf3 -J` output (client side)."""
    out = {"tput_mbps": None, "retransmits": None}
    try:
        j = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return out
    end = j.get("end", {})
    s = end.get("sum_received") or end.get("sum") or {}
    if "bits_per_second" in s:
        out["tput_mbps"] = s["bits_per_second"] / 1e6
    snd = end.get("sum_sent", {})
    if "retransmits" in snd:
        out["retransmits"] = snd["retransmits"]
    return out


_IW_FIELDS = {
    "signal": ("signal_dbm", r"signal:\s*(-?\d+)"),
    "signal avg": ("signal_avg_dbm", r"signal avg:\s*(-?\d+)"),
    "tx bitrate": ("tx_bitrate_mbps", r"tx bitrate:\s*([\d.]+)"),
    "rx bitrate": ("rx_bitrate_mbps", r"rx bitrate:\s*([\d.]+)"),
    "tx retries": ("tx_retries", r"tx retries:\s*(\d+)"),
    "tx failed": ("tx_failed", r"tx failed:\s*(\d+)"),
    "tx packets": ("tx_packets", r"tx packets:\s*(\d+)"),
    "rx packets": ("rx_packets", r"rx packets:\s*(\d+)"),
}


def parse_station_dump(text: str, mac: str | None = None) -> dict:
    """Parse `iw dev <if> station dump`; picks the station `mac` (or the first)."""
    blocks = re.split(r"(?m)^Station\s+", text)
    blocks = [b for b in blocks if b.strip()]
    if mac:
        blocks = [b for b in blocks if b.lower().startswith(mac.lower())] or []
    out = {v[0]: None for v in _IW_FIELDS.values()}
    out["station"] = None
    if not blocks:
        return out
    b = blocks[0]
    out["station"] = b.split()[0]
    for _, (key, pat) in _IW_FIELDS.items():
        m = re.search(pat, b)
        if m:
            val = m.group(1)
            out[key] = float(val) if "." in val or key.endswith(("dbm", "mbps")) else int(val)
    return out


# --------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------
def _run(cmd: list[str], timeout: float) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return f"ERROR {e}"


def measure_point(a) -> dict:
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scenario": a.scenario, "distance_m": a.distance_m, "walls": a.walls,
        "n_nodes": a.n_nodes, "target": a.target, "note": a.note,
    }
    ping_txt = _run(["ping", "-c", str(a.ping_count), "-i", str(a.ping_interval),
                     "-s", str(a.payload), a.target], timeout=a.ping_count * a.ping_interval + 30)
    row.update(parse_ping(ping_txt))

    if a.iperf and shutil.which("iperf3"):
        cmd = ["iperf3", "-c", a.target, "-t", str(a.iperf_seconds), "-J"]
        if a.udp_mbps:
            cmd += ["-u", "-b", f"{a.udp_mbps}M"]
        row.update(parse_iperf3(_run(cmd, timeout=a.iperf_seconds + 30)))
    else:
        row.update(parse_iperf3(""))

    if a.gateway:
        ssh = ["ssh", "-o", "ConnectTimeout=5", f"{a.ssh_user}@{a.gateway}",
               f"iw dev {a.iface} station dump"]
        row.update(parse_station_dump(_run(ssh, timeout=20), a.station_mac))
    return row


def append_row(path: str, row: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scenario", required=True, help="e.g. indoor-2walls, outdoor-los, dense-20")
    p.add_argument("--distance-m", type=float, required=True)
    p.add_argument("--walls", type=int, default=0)
    p.add_argument("--n-nodes", type=int, default=1)
    p.add_argument("--target", required=True, help="IP of the HaLow node (or a host behind it)")
    p.add_argument("--gateway", help="gateway IP for iw station dump over SSH (e.g. 10.42.0.1)")
    p.add_argument("--ssh-user", default="root")
    p.add_argument("--iface", default="wlan0", help="HaLow interface on the gateway")
    p.add_argument("--station-mac", help="MAC of the node in the station dump")
    p.add_argument("--ping-count", type=int, default=50)
    p.add_argument("--ping-interval", type=float, default=0.2)
    p.add_argument("--payload", type=int, default=200, help="ping payload bytes")
    p.add_argument("--iperf", action="store_true", help="also run iperf3 (server must run on target)")
    p.add_argument("--iperf-seconds", type=int, default=10)
    p.add_argument("--udp-mbps", type=float, default=0.0, help="UDP rate; 0 = TCP")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--note", default="")
    p.add_argument("--out", default="data/links.csv")
    a = p.parse_args(argv)
    for i in range(a.repeats):
        row = measure_point(a)
        append_row(a.out, row)
        print(f"[{i + 1}/{a.repeats}] loss={row['loss_pct']}% rtt={row['rtt_avg_ms']} ms "
              f"signal={row.get('signal_dbm')} dBm tput={row.get('tput_mbps')} Mb/s")
        time.sleep(1)


if __name__ == "__main__":
    main()
