import csv, json, logging, os, time

from ryu.app import simple_switch_13
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.lib import hub

# Port numbering follows topology/topo.py:
#   s1: port1=h1, port2=h2, port3=s2      s2: port1=h3, port2=h4, port3=s1
BOTTLENECK_PORTS = {(1, 3), (2, 3)}   # the 10 Mbps s1-s2 link, both ends
BOTTLENECK_BPS = 10000000             # 10 Mbps
HOST_PORT_BPS = 100000000             # 100 Mbps host links
UTIL_THRESHOLD = 80.0                 # % utilization that triggers an alert
LOSS_THRESHOLD = 20.0                 # % telemetry loss that triggers an alert
POLL_INTERVAL = 2                     # seconds
MIN_ATTACK_BPS = 2000000              # flow AND host telemetry must exceed 2 Mbps
BLOCK_SECONDS = 20                    # how long a drop rule lives
STALE_SECONDS = 5                     # telemetry older than this is "stale"
TELEMETRY_FILE = "/tmp/sdn_telemetry.json"
MAC_TO_HOST = {
    "00:00:00:00:00:01": "h1",
    "00:00:00:00:00:02": "h2",
    "00:00:00:00:00:03": "h3",
    "00:00:00:00:00:04": "h4",
}
MITIGATION = os.environ.get("MITIGATION", "1") == "1"
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
TAG = "on" if MITIGATION else "off"
EVENT_LOG = os.path.join(RESULTS_DIR, "events_%s.csv" % TAG)
UTIL_LOG = os.path.join(RESULTS_DIR, "util_%s.csv" % TAG)


def capacity_bps(dpid, port):
    return BOTTLENECK_BPS if (dpid, port) in BOTTLENECK_PORTS else HOST_PORT_BPS


class NetworkMonitor(simple_switch_13.SimpleSwitch13):
    def __init__(self, *args, **kwargs):
        super(NetworkMonitor, self).__init__(*args, **kwargs)
        self.logger.setLevel(logging.WARNING)
        self.datapaths = {}
        self.prev_ports = {}    # (dpid, port) -> (time, tx_bytes)
        self.prev_flows = {}    # (dpid, src, dst) -> (time, bytes)
        self.congested = {}     # (dpid, port) -> start time
        self.blocked = {}       # (dpid, src, dst) -> time installed
        self.alerted = set()
        if not os.path.isdir(RESULTS_DIR):
            os.makedirs(RESULTS_DIR)
        self._log("controller_start", "mitigation=%s" % MITIGATION)
        print("=== Controller started, mitigation %s ===" % ("ON" if MITIGATION else "OFF"), flush=True)
        hub.spawn(self._monitor)

    def _log(self, event, detail=""):
        with open(EVENT_LOG, "a") as f:
            csv.writer(f).writerow([round(time.time(), 3), event, detail])

    def _log_util(self, rows):
        new = not os.path.exists(UTIL_LOG)
        with open(UTIL_LOG, "a") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "switch", "port", "util_pct"])
            w.writerows(rows)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
        else:
            self.datapaths.pop(dp.id, None)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def _port_status(self, ev):
        msg = ev.msg
        dp, ofp = msg.datapath, msg.datapath.ofproto
        port = msg.desc.port_no
        if port >= 0xffffff00:
            return
        down = (bool(msg.desc.state & ofp.OFPPS_LINK_DOWN)
                or bool(msg.desc.config & ofp.OFPPC_PORT_DOWN)
                or msg.reason == ofp.OFPPR_DELETE)
        if down:
            print("*** ALERT: link down on s%d port %d (port-status event)" % (dp.id, port), flush=True)
            self._log("port_down", "s%d port %d" % (dp.id, port))
        else:
            print("--- Link up on s%d port %d (port-status event)" % (dp.id, port), flush=True)
            self._log("port_up", "s%d port %d" % (dp.id, port))

    def _monitor(self):
        while True:
            for dp in list(self.datapaths.values()):
                parser, ofp = dp.ofproto_parser, dp.ofproto
                dp.send_msg(parser.OFPPortStatsRequest(dp, 0, ofp.OFPP_ANY))
                dp.send_msg(parser.OFPFlowStatsRequest(dp))
            self._check_telemetry()
            hub.sleep(POLL_INTERVAL)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply(self, ev):
        dpid, now = ev.msg.datapath.id, time.time()
        rows = []
        for st in sorted(ev.msg.body, key=lambda s: s.port_no):
            if st.port_no >= 0xffffff00:
                continue
            key = (dpid, st.port_no)
            prev = self.prev_ports.get(key)
            self.prev_ports[key] = (now, st.tx_bytes)
            if prev is None:
                continue
            bps = max(0, st.tx_bytes - prev[1]) * 8 / (now - prev[0])
            util = bps / capacity_bps(dpid, st.port_no) * 100
            rows.append([round(now, 3), dpid, st.port_no, round(util, 2)])
            if util >= 0.5:
                print("[PORT] s%d port %d: %.2f Mbps (%.1f%% of link)"
                      % (dpid, st.port_no, bps / 1e6, util), flush=True)
            if util > UTIL_THRESHOLD:
                print("*** ALERT: high utilization on s%d port %d (%.1f%%)"
                      % (dpid, st.port_no, util), flush=True)
                if key not in self.congested:
                    self.congested[key] = now
                    self._log("congestion_start", "s%d port %d %.1f%%" % (dpid, st.port_no, util))
            elif key in self.congested:
                dur = now - self.congested.pop(key)
                print("--- Congestion cleared on s%d port %d after %.1f s"
                      % (dpid, st.port_no, dur), flush=True)
                self._log("congestion_cleared", "s%d port %d after %.1fs" % (dpid, st.port_no, dur))
        if rows:
            self._log_util(rows)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply(self, ev):
        dp, now, body = ev.msg.datapath, time.time(), ev.msg.body
        print("[FLOW] s%d: %d flow entries, %d packets matched"
              % (dp.id, len(body), sum(f.packet_count for f in body)), flush=True)
        best = None
        for f in body:
            if f.priority != 1:
                continue                       # skip table-miss and our drop rules
            src, dst = f.match.get('eth_src'), f.match.get('eth_dst')
            if not src or not dst:
                continue
            key = (dp.id, src, dst)
            prev = self.prev_flows.get(key)
            self.prev_flows[key] = (now, f.byte_count)
            if prev is None:
                continue
            bps = max(0, f.byte_count - prev[1]) * 8 / (now - prev[0])
            if best is None or bps > best[0]:
                best = (bps, src, dst)
        ports = sorted(k[1] for k in self.congested if k[0] == dp.id)
        if not (ports and best and best[0] > MIN_ATTACK_BPS):
            return
        verdict, host, tx_bps = self._confirm(best[1])
        name = host or best[1]
        if verdict == "disagree":
            print("--- congestion on s%d port %d, source %s NOT confirmed by telemetry "
                  "(host tx %.1f Mbps), not blocking" % (dp.id, ports[0], name, tx_bps / 1e6), flush=True)
            return
        if verdict == "confirmed":
            print("*** ALERT: congestion on s%d port %d, source %s confirmed by telemetry (%.0f Mbps)"
                  % (dp.id, ports[0], name, tx_bps / 1e6), flush=True)
        else:
            print("*** ALERT: congestion on s%d port %d, source %s UNCONFIRMED "
                  "(telemetry stale or missing), flow %.1f Mbps"
                  % (dp.id, ports[0], name, best[0] / 1e6), flush=True)
        if MITIGATION:
            self._block(dp, best, verdict)

    def _confirm(self, src_mac):
        """Return (verdict, host, tx_bps). verdict: confirmed / unconfirmed / disagree."""
        host = MAC_TO_HOST.get(src_mac)
        data = self._read_telemetry()
        if host is None or data is None or host not in data:
            return "unconfirmed", host, None
        t = data[host]
        if t["status"] == "down" or time.time() - t["last_seen"] > STALE_SECONDS:
            return "unconfirmed", host, None
        if t["tx_bps"] > MIN_ATTACK_BPS:
            return "confirmed", host, t["tx_bps"]
        return "disagree", host, t["tx_bps"]

    def _block(self, dp, best, how):
        bps, src, dst = best
        key = (dp.id, src, dst)
        if time.time() - self.blocked.get(key, 0) < BLOCK_SECONDS:
            return
        parser = dp.ofproto_parser
        match = parser.OFPMatch(eth_src=src, eth_dst=dst)
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=100, match=match,
                                      instructions=[], hard_timeout=BLOCK_SECONDS))
        self.blocked[key] = time.time()
        print("*** MITIGATION: s%d dropping %s -> %s (%.1f Mbps) for %d s [%s]"
              % (dp.id, src, dst, bps / 1e6, BLOCK_SECONDS, how), flush=True)
        self._log("mitigation_installed", "s%d %s->%s %.1fMbps %s" % (dp.id, src, dst, bps / 1e6, how))

    def _read_telemetry(self):
        try:
            with open(TELEMETRY_FILE) as f:
                return json.load(f)
        except (IOError, ValueError):
            return None

    def _check_telemetry(self):
        data = self._read_telemetry()
        if data is None:
            return
        for host, t in data.items():
            bad = t["status"] == "down" or t["loss_pct"] > LOSS_THRESHOLD
            if bad and host not in self.alerted:
                self.alerted.add(host)
                print("*** ALERT: host %s is %s (telemetry loss %.1f%%)"
                      % (host, t["status"].upper(), t["loss_pct"]), flush=True)
                self._log("host_down", host)
            elif not bad and host in self.alerted:
                self.alerted.discard(host)
                print("--- RECOVERED: host %s is healthy again" % host, flush=True)
                self._log("host_recovered", host)
