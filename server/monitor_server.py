import socket, json, time, threading, os

PORT = 5005
OUT = "/tmp/sdn_telemetry.json"
TIMEOUT = 3          # seconds without telemetry => host down
hosts, lock = {}, threading.Lock()

def writer():
    while True:
        time.sleep(1)
        now = time.time()
        with lock:
            snap = {}
            for name, h in hosts.items():
                total = h["received"] + h["lost"]
                snap[name] = {
                    "status": "up" if now - h["last_seen"] < TIMEOUT else "down",
                    "received": h["received"], "lost": h["lost"],
                    "loss_pct": round(100.0 * h["lost"] / total, 1) if total else 0.0,
                    "tx_bps": h["tx_bps"], "last_seen": h["last_seen"]}
        with open(OUT + ".tmp", "w") as f:
            json.dump(snap, f)
        os.replace(OUT + ".tmp", OUT)

threading.Thread(target=writer, daemon=True).start()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", PORT))
print("Monitoring server listening on UDP", PORT, flush=True)

while True:
    data, addr = sock.recvfrom(2048)
    try:
        m = json.loads(data.decode())
        name, seq = m["host"], m["seq"]
    except (ValueError, KeyError):
        continue                                   # ignore malformed packets
    with lock:
        h = hosts.setdefault(name, {"last_seq": seq - 1, "received": 0, "lost": 0,
                                    "last_seen": 0, "tx_bps": 0.0,
                                    "prev_tx": m["tx_bytes"], "prev_ts": m["ts"]})
        if seq < h["last_seq"]:                    # agent restarted
            h["last_seq"] = seq - 1
        if seq > h["last_seq"] + 1:
            h["lost"] += seq - h["last_seq"] - 1
        dt = m["ts"] - h["prev_ts"]
        if dt > 0:
            h["tx_bps"] = round((m["tx_bytes"] - h["prev_tx"]) * 8 / dt)
        h["prev_tx"], h["prev_ts"] = m["tx_bytes"], m["ts"]
        h["last_seq"], h["last_seen"] = seq, time.time()
        h["received"] += 1
