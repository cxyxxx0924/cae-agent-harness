import math, sys, os
from collections import defaultdict

_W = os.environ.get("WORKDIR", r".")
SRC = _W + r"\out\lines_pts.txt"
OUT = _W + r"\out\v_lines.png"

lines = defaultdict(dict)   # tag -> {id: (L, sp, ep, pts)}
order = defaultdict(list)
for raw in open(SRC, encoding="utf-8"):
    raw = raw.strip()
    if not raw:
        continue
    head, _, tail = raw.partition("|")
    f = head.split()
    tag, lid, L = f[0], int(f[1]), f[2]
    sp = (float(f[3]), float(f[4]))
    ep = (float(f[5]), float(f[6]))
    pts = []
    for seg in tail.strip().split(";"):
        if seg.strip():
            a, b = seg.split()
            pts.append((float(a), float(b)))
    lines[tag][lid] = (L, sp, ep, pts)
    order[tag].append(lid)

# ---- 连通分组 (端点距离 < 5mm) ----
def group_ids(tag, tol=5.0):
    ids = order[tag]
    ends = {i: (lines[tag][i][1], lines[tag][i][2]) for i in ids}
    visited, groups = set(), []
    for i in ids:
        if i in visited:
            continue
        grp, queue = [], [i]
        visited.add(i)
        while queue:
            cur = queue.pop(0)
            grp.append(cur)
            for o in ids:
                if o in visited:
                    continue
                d = min(math.dist(p, q) for p in ends[cur] for q in ends[o])
                if d < tol:
                    visited.add(o)
                    queue.append(o)
        groups.append(sorted(grp))
    return groups

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
for _f in ("Microsoft YaHei", "SimHei", "SimSun"):
    try:
        font_manager.findfont(_f, fallback_to_default=False)
        plt.rcParams["font.sans-serif"] = [_f]
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False

COLORS = ["#d62728", "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd",
          "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f"]

fig, ax = plt.subplots(figsize=(16, 9), dpi=110)
ax.set_facecolor("white")

# 背景: BELT (灰)
for lid in order.get("BELT", []):
    L, sp, ep, pts = lines["BELT"][lid]
    if len(pts) >= 2:
        xs = [p[0] for p in pts]; zs = [p[1] for p in pts]
        ax.plot(xs, zs, "-", color="#cccccc", lw=1.2, zorder=1)
# 背景: CAV (浅蓝虚线)
for lid in order.get("CAV", []):
    L, sp, ep, pts = lines["CAV"][lid]
    if len(pts) >= 2:
        xs = [p[0] for p in pts]; zs = [p[1] for p in pts]
        ax.plot(xs, zs, "--", color="#9ecae1", lw=1.4, zorder=2)

seam_groups = group_ids("SEAM")
for gi, g in enumerate(seam_groups):
    col = COLORS[gi % len(COLORS)]
    for lid in g:
        L, sp, ep, pts = lines["SEAM"][lid]
        if len(pts) >= 2:
            xs = [p[0] for p in pts]; zs = [p[1] for p in pts]
            ax.plot(xs, zs, "-", color=col, lw=2.4, zorder=3)
    # 组标签放质心
    cx = sum(lines["SEAM"][i][1][0] for i in g) / len(g)
    cz = sum(lines["SEAM"][i][1][1] for i in g) / len(g)
    ax.text(cx, cz, f"G{gi}({len(g)})", color=col, fontsize=11, fontweight="bold",
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=col, alpha=0.9), zorder=5)

# 端点度数异常标记
ends_all = []
for lid in order.get("SEAM", []):
    ends_all.append(lines["SEAM"][lid][1])
    ends_all.append(lines["SEAM"][lid][2])
cnt = defaultdict(int)
for p in ends_all:
    cnt[p] += 1
bad = [p for p, c in cnt.items() if c != 2]
if bad:
    ax.scatter([p[0] for p in bad], [p[1] for p in bad], s=45, c="black", marker="x", zorder=6,
               label=f"非2度端点 ({len(bad)})")

ax.set_xlabel("X (mm)  →右为+X")
ax.set_ylabel("Z (mm)  ↑上为+Z")
ax.set_title("cab1 线框: 缝线 comp3/56线 (彩色=G分组)  气腔 comp2 (浅蓝虚线)  布带 comp1 (灰)")
ax.set_aspect("equal")
ax.grid(alpha=0.25)
ax.legend(loc="upper right")
plt.tight_layout()
plt.savefig(OUT)
print("saved", OUT)
print("seam groups:", [(gi, len(g)) for gi, g in enumerate(seam_groups)])
for gi, g in enumerate(seam_groups):
    print(f"  G{gi} n={len(g)} ids={g}")
