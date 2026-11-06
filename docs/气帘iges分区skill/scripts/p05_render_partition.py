"""Final v8 render: 4 per-class panels + overview with ID-free structure check."""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

BASE = os.environ.get("WORKDIR", os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out")

pts = {}
for ln in open(os.path.join(OUT, "lines_pts.txt"), encoding="utf-8"):
    if not ln.startswith("L "):
        continue
    head, _, tail = ln.strip().partition("|")
    lid = int(head.split()[1])
    pl = [(float(s.split()[0]), float(s.split()[1])) for s in tail.strip().split(";") if s.strip()]
    pts[lid] = pl

cls = json.load(open(os.path.join(OUT, "classify_final.json"), encoding="utf-8"))["line_comp"]
CLS = {int(k): v for k, v in cls.items()}
COL = {"BELT": "red", "CAVITY": "blue", "SEAM": "green", "TETHER": "orange"}

counts = {}
for c in CLS.values():
    counts[c] = counts.get(c, 0) + 1

# ---- 4 panels ----
fig, axes = plt.subplots(2, 2, figsize=(22, 14))
for ax, c in zip(axes.ravel(), ("BELT", "CAVITY", "SEAM", "TETHER")):
    segs = []
    for lid, pl in pts.items():
        if CLS.get(lid) != c:
            continue
        for i in range(len(pl)-1):
            segs.append((pl[i], pl[i+1]))
    ax.add_collection(LineCollection(segs, colors=COL[c], linewidths=1.3))
    ax.autoscale()
    ax.set_aspect("equal"); ax.grid(True, alpha=0.3)
    ax.set_title(f"{c}: {counts[c]} lines")
fig.suptitle("four-partition (bridge-scan corrected)", fontsize=14)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "v_partition.png"), dpi=105)

# ---- overview ----
fig, ax = plt.subplots(figsize=(26, 9))
for c, col in COL.items():
    segs = []
    for lid, pl in pts.items():
        if CLS.get(lid) != c:
            continue
        for i in range(len(pl)-1):
            segs.append((pl[i], pl[i+1]))
    ax.add_collection(LineCollection(segs, colors=col, linewidths=1.4, label=f"{c} ({counts[c]})"))
ax.autoscale(); ax.set_aspect("equal"); ax.grid(True, alpha=0.3)
ax.legend(loc="upper right", fontsize=11)
ax.set_title("overview: BELT=red CAVITY=blue SEAM=green TETHER=orange", fontsize=13)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "v_partition_all.png"), dpi=105)
print("saved v_partition.png + v_partition_all.png")
print("counts:", counts, "total", sum(counts.values()))
