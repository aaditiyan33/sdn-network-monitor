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
