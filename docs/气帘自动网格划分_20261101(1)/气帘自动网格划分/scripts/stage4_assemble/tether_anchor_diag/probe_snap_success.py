# -*- coding: utf-8 -*-
"""probe_snap_success.py — 验证"吸附只成功一部分"假设

假设: 拉带第一排有 N 个节点, 但只有其中一部分(能在 3mm 内找到布带节点)被吸附到 Z=0,
      其余仍留在 Z=-1。相邻单元一半在 Z=0 一半在 Z=-1 -> "只爬到一半"的三角形/齿状。
      如果是这样, 那么:
        · 被吸附节点的邻接单元 质量应该明显好于 未被吸附的
        · 未被吸附的第一排节点数应该占多数
"""
import math, collections, sys
sys.path.insert(0, ".")
from rebuild_anchor_band import read_k, quad_metrics

K = "E:/work/AI_CAB/onekey/cab2_curtain_airbag_v3.k"
nodes, els = read_k(K)

belt_n, teth_n = set(), set()
teth_adj = collections.defaultdict(set)
teth_elem = []
for eid, pid, ns in els:
    if pid == 2:
        belt_n.update(ns)
    elif pid == 5:
        teth_n.update(ns); teth_elem.append((eid, ns))
        for i, x in enumerate(ns):
            for y in ns[i + 1:]:
                teth_adj[x].add(y); teth_adj[y].add(x)
shared = belt_n & teth_n

# 拉带节点按 Z 分组
zgrp = collections.Counter(round(nodes[n][2], 2) for n in teth_n)
print("拉带节点 Z 分布:", dict(zgrp))
print(f"共节点(吸附成功) {len(shared)}")

# "第一排候选" = Z=-1 且平面位置在最近布带节点 4mm 内的拉带节点 = 本该被吸附却没吸的
CELL = 4.0
grid = collections.defaultdict(list)
for b in belt_n:
    grid[(int(nodes[b][0] // CELL), int(nodes[b][1] // CELL))].append(b)

missed, dists = [], []
for n in teth_n - shared:
    x, y, z = nodes[n]
    best = 1e9
    gx, gy = int(x // CELL), int(y // CELL)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for b in grid.get((gx + dx, gy + dy), ()):
                best = min(best, math.hypot(nodes[b][0] - x, nodes[b][1] - y))
    if best <= 4.0:
        missed.append(n); dists.append(best)
dists.sort()
print(f"\n『本该吸附但没吸上』的拉带节点: {len(missed)} 个  (平面距布带节点 ≤4mm)")
if dists:
    q = lambda p: dists[min(len(dists) - 1, int(p * (len(dists) - 1)))]
    print(f"   这些节点的最近布带距离: p10={q(.1):.2f} p50={q(.5):.2f} p90={q(.9):.2f}")

# 三组对比: 已吸附 / 漏吸附 / 深处
def grp_of(cond):
    return [(eid, ns) for eid, ns in teth_elem if any(cond(n) for n in ns)]

g_ok = grp_of(lambda n: n in shared)
g_miss = grp_of(lambda n: n in missed)
g_deep = [(eid, ns) for eid, ns in teth_elem
          if not any(n in shared or n in missed for n in ns)]

print(f"\n{'组':<22}{'单元':>6}{'翘曲p50':>9}{'翘曲p95':>9}{'翘曲max':>9}{'>15°':>7}")
print("-" * 62)
for tag, g in (("① 已吸附(共节点)", g_ok), ("② 漏吸附(仍在Z=-1)", g_miss), ("③ 拉带深处", g_deep)):
    if not g:
        continue
    w = sorted(quad_metrics(ns, nodes)[2] for _, ns in g)
    n = len(w)
    q = lambda p: w[min(n - 1, int(p * (n - 1)))]
    print(f"{tag:<22}{n:>6}{q(.5):>9.2f}{q(.95):>9.2f}{w[-1]:>9.2f}{sum(1 for x in w if x>15):>7}")

# 已吸附 vs 漏吸附 的节点数比例
print(f"\n结论: 第一排候选 {len(shared) + len(missed)} 个, "
      f"吸附成功 {len(shared)}, 漏掉 {len(missed)} "
      f"({100.0*len(missed)/max(1,len(shared)+len(missed)):.0f}%)")
