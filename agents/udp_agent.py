# usage: udp_agent.py <server_ip> <host_name> <iface> [interval_s]
import socket, sys, time, json

server_ip, name, iface = sys.argv[1], sys.argv[2], sys.argv[3]
interval = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
PORT = 5005

def read_bytes(iface):
    with open("/proc/net/dev") as f:
        for line in f:
            if line.strip().startswith(iface + ":"):
                fields = line.split(":")[1].split()
                return int(fields[0]), int(fields[8])   # rx, tx
    return 0, 0

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
seq = 0
while True:
    rx, tx = read_bytes(iface)
    msg = {"host": name, "seq": seq, "ts": time.time(), "rx_bytes": rx, "tx_bytes": tx}
    s.sendto(json.dumps(msg).encode(), (server_ip, PORT))
    seq += 1
    time.sleep(interval)
