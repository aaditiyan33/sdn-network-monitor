import json, logging, time
from ryu.app import simple_switch_13
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.lib import hub

LINK_CAPACITY_BPS = 10000000     # 10 Mbps (s1-s2 link)
UTIL_THRESHOLD = 80.0            # % utilization that triggers an alert
LOSS_THRESHOLD = 20.0            # % telemetry loss that triggers an alert
POLL_INTERVAL = 2                # seconds
TELEMETRY_FILE = "/tmp/sdn_telemetry.json"

class NetworkMonitor(simple_switch_13.SimpleSwitch13):
    def __init__(self, *args, **kwargs):
        super(NetworkMonitor, self).__init__(*args, **kwargs)
        self.logger.setLevel(logging.WARNING)      # hide per-packet logs
        self.datapaths, self.prev_ports = {}, {}
        self.alerted = set()
        hub.spawn(self._monitor)

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
            bps = (st.tx_bytes - prev[1]) * 8 / (now - prev[0])
            util = bps / LINK_CAPACITY_BPS * 100
            if util >= 0.5:
                print("[PORT] s%d port %d: %.2f Mbps (%.1f%% of link)"
                      % (dpid, st.port_no, bps / 1e6, util), flush=True)
            if util > UTIL_THRESHOLD:
                print("*** ALERT: high utilization on s%d port %d (%.1f%%)"
                      % (dpid, st.port_no, util), flush=True)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply(self, ev):
        body = ev.msg.body
        pkts = sum(f.packet_count for f in body)
        print("[FLOW] s%d: %d flow entries, %d packets matched"
              % (ev.msg.datapath.id, len(body), pkts), flush=True)

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
            elif not bad and host in self.alerted:
                self.alerted.discard(host)
                print("--- RECOVERED: host %s is healthy again" % host, flush=True)
