import numpy as np

from measure.analyze import summarize
from measure.collect import parse_iperf3, parse_ping, parse_station_dump
from measure.parse_power import estimate_params

LINUX_PING = """
50 packets transmitted, 48 received, 4% packet loss, time 9812ms
rtt min/avg/max/mdev = 3.120/5.871/14.002/2.010 ms
"""
MAC_PING = """
--- 10.42.0.50 ping statistics ---
50 packets transmitted, 50 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 2.900/4.100/9.700/1.200 ms
"""
STATION = """Station 0c:bf:74:00:00:01 (on wlan0)
\tinactive time:\t120 ms
\trx packets:\t1520
\ttx packets:\t980
\ttx retries:\t37
\ttx failed:\t2
\tsignal:  \t-71 dBm
\tsignal avg:\t-70 dBm
\ttx bitrate:\t2.4 MBit/s
\trx bitrate:\t1.8 MBit/s
Station 0c:bf:74:00:00:02 (on wlan0)
\tsignal:  \t-85 dBm
"""


def test_parse_ping_linux_and_mac():
    a = parse_ping(LINUX_PING)
    assert a["loss_pct"] == 4.0 and a["rtt_avg_ms"] == 5.871 and a["rtt_mdev_ms"] == 2.010
    b = parse_ping(MAC_PING)
    assert b["loss_pct"] == 0.0 and b["rtt_max_ms"] == 9.7


def test_parse_station_dump_select_mac():
    a = parse_station_dump(STATION)
    assert a["signal_dbm"] == -71 and a["tx_bitrate_mbps"] == 2.4 and a["tx_retries"] == 37
    b = parse_station_dump(STATION, "0c:bf:74:00:00:02")
    assert b["signal_dbm"] == -85 and b["tx_retries"] is None


def test_parse_iperf3():
    j = '{"end": {"sum_received": {"bits_per_second": 1500000}, "sum_sent": {"retransmits": 4}}}'
    r = parse_iperf3(j)
    assert abs(r["tput_mbps"] - 1.5) < 1e-9 and r["retransmits"] == 4
    assert parse_iperf3("not json")["tput_mbps"] is None


def test_power_parser_recovers_synthetic_trace():
    # sleep 50 uW, every 2 s: 5 ms listen @60 mW then 6 ms tx @250 mW
    dt = 1e-4
    t = np.arange(0, 20, dt)
    p = np.full_like(t, 50e-6)
    for s in np.arange(0.5, 20, 2.0):
        i0 = int(s / dt)
        p[i0:i0 + 50] = 60e-3
        p[i0 + 50:i0 + 110] = 250e-3
    r = estimate_params(t, p)
    assert r["n_bursts"] == 10
    assert abs(r["p_tx"] - 0.25) < 1e-3 and abs(r["p_rx"] - 0.06) < 1e-3
    assert abs(r["t_tx"] - 6e-3) < 2e-4 and abs(r["wake_interval_s"] - 2.0) < 1e-3
    assert abs(r["p_sleep"] - 50e-6) < 1e-6


def test_summarize_groups_by_scenario_distance():
    rows = [{"scenario": "indoor", "distance_m": "10", "loss_pct": "0", "signal_dbm": "-60"},
            {"scenario": "indoor", "distance_m": "10", "loss_pct": "2", "signal_dbm": "-62"},
            {"scenario": "outdoor", "distance_m": "200", "loss_pct": "", "signal_dbm": "-80"}]
    s = summarize(rows)
    assert len(s) == 2 and s[0]["loss_pct_mean"] == 1.0 and s[0]["signal_dbm_mean"] == -61.0
    assert np.isnan(s[1]["loss_pct_mean"])
