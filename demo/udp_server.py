import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", 5005))
s.settimeout(4)            # stop after 4 s of silence
while True:
    try:
        data, addr = s.recvfrom(1024)
        print(addr[0], data.decode(), flush=True)
    except socket.timeout:
        break
