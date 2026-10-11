import csv, json, logging, os, time
from ryu.app import simple_switch_13
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.lib import hub

LINK_CAPACITY_BPS = 10000000     # 10 Mbps (s1-s2 link)
UTIL_THRESHOLD = 80.0            # % utilization that triggers an alert
LOSS_THRESHOLD = 20.0            # % telemetry loss that triggers an alert
POLL_INTERVAL = 2                # seconds
MIN_ATTACK_BPS = 2000000         # a flow must exceed 2 Mbps to be blocked
BLOCK_SECONDS = 20               # how long a drop rule lives
TELEMETRY_FILE = "/tmp/sdn_telemetry.json"
MITIGATION = os.environ.get("MITIGATION", "1") == "1"
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
EVENT_LOG = os.path.join(RESULTS_DIR, "events_%s.csv" % ("on" if MITIGATION else "off"))


class NetworkMonitor(simple_switch_13.SimpleSwitch13):
    def __init__(self, *args, **kwargs):
        super(NetworkMonitor, self).__init__(*args, **kwargs)
        self.logger.setLevel(logging.WARNING)
        self.datapaths = {}
        self.prev_ports = {}     # (dpid, port) -> (time, tx_bytes)
        self.prev_flows = {}     # (dpid, src, dst) -> (time, bytes)
        self.congested = {}      # (dpid, port) -> start time
        self.blocked = {}        # (dpid, src, dst) -> time installed
        self.alerted = set()
        if not os.path.isdir(RESULTS_DIR):
            os.makedirs(RESULTS_DIR)
        self._log("controller_start", "mitigation=%s" % MITIGATION)
        print("=== Controller started, mitigation %s ===" % ("ON" if MITIGATION else "OFF"), flush=True)
        hub.spawn(self._monitor)

    def _log(self, event, detail=""):
        with open(EVENT_LOG, "a") as f:
            csv.writer(f).writerow([round(time.time(), 3), event, detail])

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
        else:
            self.datapaths.pop(dp.id, None)

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
        for st in sorted(ev.msg.body, key=lambda s: s.port_no):
            if st.port_no >= 0xffffff00:
                continue
            key = (dpid, st.port_no)
            prev = self.prev_ports.get(key)
            self.prev_ports[key] = (now, st.tx_bytes)
            if prev is None:
                continue
            bps = max(0, st.tx_bytes - prev[1]) * 8 / (now - prev[0])
            util = bps / LINK_CAPACITY_BPS * 100
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

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply(self, ev):
        dp, now, body = ev.msg.datapath, time.time(), ev.msg.body
        print("[FLOW] s%d: %d flow entries, %d packets matched"
              % (dp.id, len(body), sum(f.packet_count for f in body)), flush=True)
        best = None
        for f in body:
            if f.priority != 1:
                continue                      # skip table-miss and our drop rules
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
        congested_here = any(k[0] == dp.id for k in self.congested)
        if MITIGATION and congested_here and best and best[0] > MIN_ATTACK_BPS:
            self._block(dp, best)

    def _block(self, dp, best):
        bps, src, dst = best
        key = (dp.id, src, dst)
        if time.time() - self.blocked.get(key, 0) < BLOCK_SECONDS:
            return
        parser = dp.ofproto_parser
        match = parser.OFPMatch(eth_src=src, eth_dst=dst)
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=100, match=match,
                                      instructions=[], hard_timeout=BLOCK_SECONDS))
        self.blocked[key] = time.time()
        print("*** MITIGATION: s%d dropping %s -> %s (%.1f Mbps) for %d s"
              % (dp.id, src, dst, bps / 1e6, BLOCK_SECONDS), flush=True)
        self._log("mitigation_installed", "s%d %s->%s %.1fMbps" % (dp.id, src, dst, bps / 1e6))

    def _check_telemetry(self):
        try:
            with open(TELEMETRY_FILE) as f:
                data = json.load(f)
        except (IOError, ValueError):
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
