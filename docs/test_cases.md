# Test cases

All tests run in Mininet with the Ryu controller started first (see the [README](../README.md)). Commands are typed at the `mininet>` prompt. Raw data for tests 6 to 11 is in `results/runs/`.

| # | Test | Command | Expected | Observed |
|---|---|---|---|---|
| 1 | Connectivity | automatic `pingall` at startup | 0% dropped (12/12) | PASS |
| 2 | Telemetry collection | `h1 cat /tmp/sdn_telemetry.json` | h2, h3, h4 status "up", loss 0% | PASS |
| 3 | Flow statistics | watch the Ryu terminal | `[FLOW]` lines for s1 and s2 every 2 s | PASS |
| 4 | Host failure alert | `py print(h4.cmd('pgrep -af udp_agent'))`, then `py h4.cmd('kill <h4 agent PID>')` | `ALERT: host h4 is DOWN` within about 3-5 s | PASS |
| 5 | Host recovery | `py h4.cmd('python3 /home/<user>/sdn-monitor/agents/udp_agent.py 10.0.0.1 h4 h4-eth0 > /tmp/h4_agent.log 2>&1 &')` | `RECOVERED: host h4 is healthy again` | PASS |
| 6 | No-attack baseline | idle for about 50 s | No congestion or host alerts | PASS |
| 7 | UDP flood 12 Mbps, mitigation OFF | `MITIGATION=0`, then the flood commands in the README | Alerts only on `s1 port 3`, no MITIGATION line, congestion lasts the whole flood | PASS: congestion 14.0 s, avg ping 50.3 ms |
| 8 | UDP flood 12 Mbps, mitigation ON | same, `MITIGATION=1` | Source confirmed by telemetry, drop rule on s1, congestion clears at the next poll | PASS: congestion 2.0 s, avg ping 12.3 ms |
| 9 | UDP flood 30 Mbps, mitigation OFF | as test 7 with `-b 30M` | As test 7 | PASS: congestion 14.0 s, avg ping 45.0 ms |
| 10 | UDP flood 30 Mbps, mitigation ON | as test 8 with `-b 30M` | As test 8 | PASS: congestion 2.0 s, avg ping 14.5 ms |
| 11 | Link failure and recovery | `link s1 s2 down`, wait, `link s1 s2 up`, wait about 20 s | Port-status alert, h3 and h4 DOWN, h2 unaffected, then RECOVERED for h3 and h4 | PASS: DOWN after 5.0 s, RECOVERED 8.7 s after link up |

Notes:

- Mininet replaces a bare host name (h4) typed inside a command with its IP address, so commands that contain host names as arguments are run through `py hX.cmd('...')`.
- Tests 1 to 5 were first run on the early version of the controller and the link-failure run (test 11) exercised host DOWN and RECOVERED again on the final code.
