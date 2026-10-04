import socket, sys, time, json
server_ip, name = sys.argv[1], sys.argv[2]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for seq in range(5):
    msg = json.dumps({"host": name, "seq": seq, "ts": time.time()})
    s.sendto(msg.encode(), (server_ip, 5005))
    time.sleep(0.2)
