# -*- coding: utf-8 -*-
"""Generic partition renderer. Reads lines_pts.txt + a classify json
(line_comp: {id: CLASS}), auto-detects X-Y vs X-Z plane, draws colored lines.
Usage: python render_partition.py <classify_json> <out_png>
If classify_json omitted, draws all lines gray (base map).
"""
import os, sys, json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CLS_JSON = sys.argv[1] if len(sys.argv) > 1 else None
PNG = sys.argv[2] if len(sys.argv) > 2 else "out/render.png"
# derive workdir/out from the classify json path: <workdir>/out/<json>
if CLS_JSON:
    OUT = os.path.dirname(os.path.abspath(CLS_JSON))
else:
    OUT = "out"

lines = {}
for ln in open(OUT + "/lines_pts.txt", encoding="utf-8"):
    if not ln.startswith("L "):
        continue
    h, _, t = ln.strip().partition("|")
    f = h.split()
    lid = int(f[1])
    pts = []
    for s in t.strip().split(";"):
        s = s.strip()
        if not s:
            continue
        c = s.split()
        if len(c) >= 3:
            pts.append((float(c[0]), float(c[1]), float(c[2])))
    if len(pts) >= 2:
        lines[lid] = pts

# plane
zs = [p[2] for p in lines.values() for p in p]
ys = [p[1] for p in lines.values() for p in p]
use_z = (max(zs) - min(zs)) > 1.0 and (max(ys) - min(ys)) < 1.0
def xy(p):
    return (p[0], p[2]) if use_z else (p[0], p[1])
print("plane:", "X-Z" if use_z else "X-Y", "lines:", len(lines))

comp = {}
if CLS_JSON:
    g = json.load(open(CLS_JSON, encoding="utf-8"))
    lc = {int(k): v for k, v in g["line_comp"].items()}
else:
    lc = {}
COL = {"BELT": "#d62728", "CAVITY": "#1f77b4", "SEAM": "#2ca02c",
       "TETHER": "#ff7f0e", "lines0": "#999999"}

fig, ax = plt.subplots(figsize=(16, 7))
if not CLS_JSON:
    for lid, pts in lines.items():
        pp = [xy(p) for p in pts]
        ax.plot([a for a, b in pp], [b for a, b in pp], color="#444444", lw=0.6)
else:
    # draw lines0 / unclassified first (gray), then the 4 classes
    for lid, pts in lines.items():
        c = lc.get(lid, "lines0")
        if c in ("lines0",):
            pp = [xy(p) for p in pts]
            ax.plot([a for a, b in pp], [b for a, b in pp], color=COL["lines0"], lw=0.5, alpha=0.7)
    for c in ("BELT", "CAVITY", "SEAM", "TETHER"):
        for lid, pts in lines.items():
            if lc.get(lid) != c:
                continue
            pp = [xy(p) for p in pts]
            ax.plot([a for a, b in pp], [b for a, b in pp], color=COL[c], lw=1.0 if c != "SEAM" else 1.3)
    from collections import Counter
    cc = Counter(lc.get(l) for l in lines)
    ax.set_title("BELT=%d CAVITY=%d SEAM=%d TETHER=%d lines0=%d" % (
        cc.get("BELT",0), cc.get("CAVITY",0), cc.get("SEAM",0), cc.get("TETHER",0), cc.get("lines0",0)))

ax.set_aspect("equal")
ax.grid(True, ls=":", alpha=0.3)
fig.tight_layout()
fig.savefig(PNG, dpi=130)
print("saved", PNG)
