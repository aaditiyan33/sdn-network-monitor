import os, time
from functools import partial
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run():
    net = Mininet(controller=None, link=TCLink,
                  switch=partial(OVSSwitch, protocols='OpenFlow13'))
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    s1, s2 = net.addSwitch('s1'), net.addSwitch('s2')
    h1, h2, h3, h4 = [net.addHost('h%d' % i) for i in range(1, 5)]
    for h, s in ((h1, s1), (h2, s1), (h3, s2), (h4, s2)):
        net.addLink(h, s, bw=100)
    net.addLink(s1, s2, bw=10)          # 10 Mbps inter-switch link (monitored)
    net.start()
    net.waitConnected()
    net.pingAll()

    h1.cmd('rm -f /tmp/sdn_telemetry.json')
    # h1 runs the monitoring server; h2-h4 run telemetry agents
    h1.cmd('python3 %s/server/monitor_server.py > /tmp/server.log 2>&1 &' % ROOT)
    time.sleep(1)
    for h in (h2, h3, h4):
        h.cmd('python3 %s/agents/udp_agent.py %s %s %s-eth0 > /tmp/%s_agent.log 2>&1 &'
              % (ROOT, h1.IP(), h.name, h.name, h.name))
    print("\nServer on h1 (%s); agents on h2, h3, h4. Type 'exit' to stop.\n" % h1.IP())
    CLI(net)
    net.stop()

if __name__ == '__main__':
    run()
