import os, time, subprocess
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import SingleSwitchTopo

os.chdir(os.path.dirname(os.path.abspath(__file__)))
net = Mininet(topo=SingleSwitchTopo(3), controller=None, switch=OVSSwitch)
net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
net.start()
net.waitConnected()
h1, h2, h3 = net.get('h1', 'h2', 'h3')

loss = net.pingAll()
h1.cmd('python3 udp_server.py > server.log 2>&1 &')
time.sleep(1)
h2.cmd('python3 udp_agent.py %s h2' % h1.IP())
h3.cmd('python3 udp_agent.py %s h3' % h1.IP())
time.sleep(5)

received = len(open('server.log').read().strip().splitlines())
flows = subprocess.run(['ovs-ofctl', '-O', 'OpenFlow13', 'dump-flows', 's1'],
                       capture_output=True, text=True).stdout
net.stop()

print("\n===== RESULTS =====")
print("Ping (controller forwarding):", "PASS" if loss == 0 else "FAIL (%s%% loss)" % loss)
print("UDP telemetry received      :", "PASS" if received == 10 else "FAIL (%d/10)" % received)
print("Flow rules installed by Ryu :", "PASS" if "actions" in flows else "FAIL")
print(flows)
