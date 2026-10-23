# Measurement runs (Oct 22, 2026)

| Condition | Mitigation | Congestion (s) | Ping avg (ms) | Ping max (ms) |
|---|---|---|---|---|
| 12 Mbps flood | OFF | 14.0 | 28.57 | 104.89 |
| 12 Mbps flood | ON | 2.0 | 12.42 | 93.23 |
| 30 Mbps flood | OFF | 14.0 | 42.62 | 104.45 |
| 30 Mbps flood | ON | 2.0 | 16.80 | 109.74 |

Notes:
- Baseline iperf loss was 0% because the 10 Mbps link held the sender to about 9.8 Mbps.
- With mitigation, iperf shows "did not receive ack" because the flood is dropped at the switches.
- Link-failure test not run yet.

## Link-failure scenario (Oct 23, 2026)

Commands: `link s1 s2 down`, then `link s1 s2 up` (mitigation ON).

| Step | Observation |
|---|---|
| Link down | ping h1 to h3: 3 sent, 0 received (100% loss) |
| Detection | Ryu: ALERT host h4 DOWN, ALERT host h3 DOWN (h2 unaffected, same switch as server) |
| Link up | telemetry resumed, hosts reported "up" at once |
| Recovery alert | RECOVERED h4, then h3, about 2 min after link up |
| Loss after outage | h4 40.2%, h3 41.5% at link up, falling to 15.7% and 16.2% |

Why recovery was slow: the server's loss % is cumulative since start, so the controller only
reports RECOVERED once loss falls below the 20% threshold. Possible improvement: a sliding window
of recent packets.
