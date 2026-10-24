"""Builds summary.csv and the report graphs from results/runs/.
Run from the repo root:  python3 results/plot_results.py
"""
import os, re
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RUNS = os.path.join("results", "runs")
OUT = "results"
CONDS = [("12m", "12 Mbps flood"), ("30m", "30 Mbps flood")]
COL = {"off": "#c0504d", "on": "#4f81bd"}


def events(name):
    df = pd.read_csv(os.path.join(RUNS, "events_%s.csv" % name),
                     header=None, names=["t", "event", "detail"])
    return df


def ping_avg_max(name):
    txt = open(os.path.join(RUNS, "ping_%s.txt" % name)).read()
    m = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", txt)
    return float(m.group(2)), float(m.group(3))


def congestion_s(ev):
    row = ev[ev.event == "congestion_cleared"].iloc[0]
    return float(re.search(r"after ([\d.]+)s", row.detail).group(1))


# ---------- summary table ----------
rows = []
for c, label in CONDS:
    for m in ("off", "on"):
        name = "%s_%s" % (c, m)
        ev = events(name)
        avg, mx = ping_avg_max(name)
        start = ev[ev.event == "congestion_start"].iloc[0].t
        mit = ev[ev.event == "mitigation_installed"]
        rows.append({
            "condition": label, "mitigation": m,
            "congestion_s": congestion_s(ev),
            "ping_avg_ms": avg, "ping_max_ms": mx,
            "mitigation_delay_ms": round((mit.iloc[0].t - start) * 1000) if len(mit) else "",
        })
summary = pd.DataFrame(rows)
summary.to_csv(os.path.join(OUT, "summary.csv"), index=False)
print(summary.to_string(index=False))

# ---------- link-failure timings ----------
lf = events("link_failure")
t_down = lf[lf.event == "port_down"].iloc[0].t
t_hostdown = lf[lf.event == "host_down"].iloc[0].t
t_rec = lf[lf.event == "host_recovered"].iloc[0].t
t_up = lf[(lf.event == "port_up") & (lf.t < t_rec)].iloc[-1].t
detect, recover = t_hostdown - t_down, t_rec - t_up
print("\nLink failure: detection %.1f s, recovery %.1f s" % (detect, recover))
with open(os.path.join(OUT, "link_failure_summary.csv"), "w") as f:
    f.write("metric,seconds\ndetection_time,%.2f\nrecovery_time,%.2f\n" % (detect, recover))

# ---------- Figure 1: comparison bars ----------
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
for ax, col, title in ((axes[0], "congestion_s", "Congestion duration on s1-s2 link (s)"),
                       (axes[1], "ping_avg_ms", "Avg ping h1-h3 during flood (ms)")):
    p = summary.pivot(index="condition", columns="mitigation", values=col)[["off", "on"]]
    p.columns = ["Static (mitigation off)", "SDN mitigation on"]
    p.plot(kind="bar", ax=ax, rot=0, color=[COL["off"], COL["on"]], width=0.7)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("")
    for cont in ax.containers:
        ax.bar_label(cont, fmt="%.1f", fontsize=9)
    ax.set_ylim(0, p.values.max() * 1.4)
    ax.legend(fontsize=8)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "comparison.png"), dpi=150)
plt.close()

# ---------- Figure 2: utilization timelines ----------
fig, axes = plt.subplots(2, 2, figsize=(11, 6), sharey=True)
for i, (c, label) in enumerate(CONDS):
    for j, m in enumerate(("off", "on")):
        ax = axes[i][j]
        name = "%s_%s" % (c, m)
        u = pd.read_csv(os.path.join(RUNS, "util_%s.csv" % name))
        u = u[(u.switch == 1) & (u.port == 3)]
        ev = events(name)
        t0 = ev[ev.event == "congestion_start"].iloc[0].t
        ax.plot(u.time - t0, u.util_pct, color=COL[m], lw=1.8)
        ax.axhline(80, color="grey", ls="--", lw=1)
        ax.axvline(0, color="orange", ls=":", lw=1.5, label="congestion detected")
        mit = ev[ev.event == "mitigation_installed"]
        if len(mit):
            ax.axvline(mit.iloc[0].t - t0, color="green", ls="-", lw=1.5, label="drop rule installed")
        cl = ev[ev.event == "congestion_cleared"].iloc[0].t - t0
        ax.axvspan(0, cl, color=COL[m], alpha=0.12)
        ax.set_xlim(-10, 30)
        ax.set_title("%s, mitigation %s (congested %.0f s)" % (label, m.upper(), cl), fontsize=10)
        ax.set_xlabel("seconds from detection")
        if j == 0:
            ax.set_ylabel("s1 port 3 utilization (%)")
        ax.legend(fontsize=7, loc="upper right")
plt.suptitle("Utilization of the monitored 10 Mbps link (dashed line = 80% threshold)", fontsize=11)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "utilization_timeline.png"), dpi=150)
plt.close()

# ---------- Figure 3: link-failure timeline ----------
fig, ax = plt.subplots(figsize=(10, 2.8))
marks = [(0, "link s1-s2 down\n(port-status event)", "#c0504d"),
         (t_hostdown - t_down, "h3, h4 flagged DOWN\n(telemetry timeout)", "#e69f00"),
         (t_up - t_down, "link s1-s2 up", "#4f81bd"),
         (t_rec - t_down, "h3, h4 RECOVERED\n(clean-packet window)", "#2e8b57")]
for k, (x, txt, colr) in enumerate(marks):
    ax.axvline(x, color=colr, lw=2)
    ax.text(x + 0.3, 0.8 - 0.35 * (k % 2), txt, color=colr, fontsize=8, va="top")
ax.axvspan(0, t_up - t_down, color="#c0504d", alpha=0.08)
ax.set_xlim(-1, t_rec - t_down + 8)
ax.set_ylim(0, 1)
ax.set_yticks([])
ax.set_xlabel("seconds after link failure")
ax.set_title("Link failure: detected in %.1f s, recovered %.1f s after the link returned"
             % (detect, recover), fontsize=10)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "link_failure_timeline.png"), dpi=150)
plt.close()
print("\nWrote summary.csv, link_failure_summary.csv and 3 PNGs in results/")
