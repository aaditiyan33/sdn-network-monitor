# Test cases (D1)

| # | Test | Command (at `mininet>`) | Expected | Observed |
|---|---|---|---|---|
| 1 | Connectivity | automatic `pingall` at startup | 0% dropped (12/12) | PASS |
| 2 | Telemetry collection | `h1 cat /tmp/sdn_telemetry.json` | h2, h3, h4 status "up", loss 0% | PASS |
| 3 | Flow statistics | watch Ryu terminal | `[FLOW]` lines for s1 and s2 every 2 s | PASS |
| 4 | Link congestion alert | `h3 iperf -s -u &` then `h2 iperf -c 10.0.0.3 -u -b 12M -t 15` | `ALERT: high utilization` on s1 port 3 and s2 port 1 at about 100% during the flood; alerts stop afterwards | PASS |
| 5 | Host failure alert | `py h4.cmd('kill <h4 agent PID>')` (find PID with `py print(h4.cmd('pgrep -af udp_agent'))`) | `ALERT: host h4 is DOWN` within about 3-5 s | PASS |
| 6 | Host recovery | `py h4.cmd('python3 /home/<user>/sdn-monitor/agents/udp_agent.py 10.0.0.1 h4 h4-eth0 > /tmp/h4_agent.log 2>&1 &')` | `RECOVERED: host h4 is healthy again` | PASS |

Note: Mininet replaces a bare host name (h4) typed inside a command with its IP address, so commands that contain host names as arguments are run through `py hX.cmd('...')`.
