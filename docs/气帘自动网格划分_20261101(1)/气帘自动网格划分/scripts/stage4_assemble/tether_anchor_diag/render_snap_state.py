# -*- coding: utf-8 -*-
"""render_snap_state.py — 可视化"吸附斑驳"：哪些拉带节点被抬到 Z=0, 哪些漏了

左: 俯视。灰=布带片, 蓝=仍在 Z=-1 的拉带片, 红=含共节点的拉带片(斜跨), 
    橙实心=吸附成功的节点, 紫空心=本该吸附却还在 Z=-1 的节点
右: 侧视 X-Z。直观看 Z=0 上只有零星几个点, 大片还在 Z=-1
"""
import math, collections, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
for _f in ("Microsoft YaHei", "SimHei"):
    try:
        matplotlib.font_manager.findfont(_f, fallback_to_default=False)
        plt.rcParams["font.sans-serif"] = [_f]; break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False
sys.path.insert(0, ".")
from rebuild_anchor_band import read_k

K = sys.argv[1] if len(sys.argv) > 1 else "E:/work/AI_CAB/onekey/cab2_curtain_airbag_v3.k"
OUT = sys.argv[2] if len(sys.argv) > 2 else "snap_state.png"

nodes, els = read_k(K)
belt_n, teth_n, teth_elem = set(), set(), []
for eid, pid, ns in els:
    if pid == 2:
        belt_n.update(ns)
    elif pid == 5:
        teth_n.update(ns); teth_elem.append((eid, ns))
shared = belt_n & teth_n

CELL = 4.0
grid = collections.defaultdict(list)
for b in belt_n:
    grid[(int(nodes[b][0] // CELL), int(nodes[b][1] // CELL))].append(b)
missed = []
for n in teth_n - shared:
    x, y, z = nodes[n]
    gx, gy = int(x // CELL), int(y // CELL)
    best = 1e9
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for b in grid.get((gx + dx, gy + dy), ()):
                best = min(best, math.hypot(nodes[b][0] - x, nodes[b][1] - y))
    if best <= 4.0:
        missed.append(n)
ms = set(missed)

fig, ax = plt.subplots(1, 2, figsize=(16, 7.2), gridspec_kw={"width_ratios": [1, 1.02]})

# ---------- 左: 俯视 ----------
polys, cols = [], []
for eid, pid, ns in els:
    if pid not in (2, 5) or len(ns) < 3:
        continue
    polys.append([(nodes[n][0], nodes[n][1]) for n in ns])
    if pid == 2:
        cols.append("#dfe3e8")
    elif any(n in shared for n in ns):
        cols.append("#e5383b")
    else:
        cols.append("#9ecae1")
ax[0].add_collection(PolyCollection(polys, facecolors=cols, edgecolors="#8a9099", linewidths=0.15))
sp = [(nodes[n][0], nodes[n][1]) for n in shared]
mp = [(nodes[n][0], nodes[n][1]) for n in missed]
ax[0].scatter([p[0] for p in mp], [p[1] for p in mp], s=16, facecolors="none",
              edgecolors="#6a1b9a", linewidths=0.9, zorder=5, label=f"漏吸附 {len(mp)}")
ax[0].scatter([p[0] for p in sp], [p[1] for p in sp], s=16, c="#f4a261",
              edgecolors="#7f4f24", linewidths=0.7, zorder=6, label=f"已吸附 {len(sp)}")
ax[0].set_aspect("equal")
ax[0].set_xlim(-420, 1820); ax[0].set_ylim(-200, 520)
ax[0].set_title("俯视 X-Y：拉带第一排节点吸附状态", fontsize=11)
ax[0].set_xlabel("X"); ax[0].set_ylabel("Y")
ax[0].legend(loc="upper left", fontsize=9, framealpha=.9)
ax[0].text(1180, 470,
           f"吸附成功 {len(sp)} / 候选 {len(sp)+len(mp)} = "
           f"{100*len(sp)/max(1,len(sp)+len(mp)):.0f}%",
           fontsize=11, color="#b71c1c", weight="bold")

# ---------- 右: 侧视 ----------
a1 = ax[1]
ZEX = 26.0
polys2, cols2 = [], []
for eid, pid, ns in els:
    if pid not in (2, 5) or len(ns) < 3:
        continue
    if pid == 5 and nodes[ns[0]][1] > 300:      # 只看 Y>300 的拉带, 避免重叠成糊
        pass
    polys2.append([(nodes[n][0], nodes[n][2] * ZEX) for n in ns])
    cols2.append("#dfe3e8" if pid == 2 else ("#e5383b" if any(n in shared for n in ns) else "#9ecae1"))
a1.add_collection(PolyCollection(polys2, facecolors=cols2, edgecolors="#8a9099", linewidths=0.2))
a1.axhline(0, color="#555", lw=1.0, ls="--")
a1.axhline(-1.0 * ZEX, color="#555", lw=1.0, ls="--")
a1.text(-400, 1.4, "布带 Z=0", fontsize=9, color="#333")
a1.text(-400, -1.0 * ZEX - 3.2, "拉带 Z=-1", fontsize=9, color="#333")
a1.set_xlim(-420, 1820); a1.set_ylim(-1.55 * ZEX, 0.35 * ZEX)
a1.set_title("侧视 X-Z（厚度向放大 %.0f×）：Z=0 上只有零星点，大片仍在 Z=-1" % ZEX, fontsize=11)
a1.set_xlabel("X"); a1.set_ylabel("Z × %.0f" % ZEX)

plt.tight_layout()
plt.savefig(OUT, dpi=150)
print(f"-> {OUT}")
print(f"   已吸附 {len(sp)}  漏吸附 {len(mp)}  比例 {100*len(sp)/max(1,len(sp)+len(mp)):.1f}%")
