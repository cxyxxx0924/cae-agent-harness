# -*- coding: utf-8 -*-
"""plan_anchors.py — 从布带网格反求每块拉带的"锚固链"

思路
----
拉带贴在布带层上, 缝接位置就是【布带边界线穿过拉带投影的那一段】。
所以锚固链 = 布带自由边界节点中, 落在某块拉带投影内的那些, 按边界顺序排成链。

step1 的布带网格在 v4 里完全不变(step1 只改气腔的 blmesh 无关),
因此可以直接从已交付的 v3.k 上把这条链算出来, 作为 v4 拉带生成的输入。

输出 anchors.json:
  [{"blk": i, "chain": [[x,y],...], "n": k, "span": L}, ...]
"""
import argparse
import collections
import json
import math

NUM = None


def read_k(path):
    import re
    num = re.compile(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')
    nodes, els = {}, []
    sec = None
    for line in open(path, encoding="ascii", errors="ignore"):
        if line.startswith("*"):
            sec = line.strip().upper()
            continue
        if not line.strip() or line.lstrip().startswith("$"):
            continue
        if sec == "*NODE":
            t = line.replace(",", " ").split()
            if len(t) >= 4:
                try:
                    nodes[int(t[0])] = (float(t[1]), float(t[2]), float(t[3]))
                except ValueError:
                    pass
            continue
        if sec.startswith("*ELEMENT_SHELL"):
            t = line.replace(",", " ").split()
            if len(t) >= 5:
                try:
                    pid = int(t[1])
                    ns = [int(x) for x in t[2:6]]
                except ValueError:
                    continue
                els.append((int(t[0]), pid, [n for n in ns if n > 0]))
            continue
        # ANSA 定宽兜底: 数值溢出会挤坏字段, 用正则取数
        if sec == "*ELEMENT_SHELL" and len(line) > 20:
            pass
    return nodes, els


def free_edges(els):
    """返回 {(a,b): count==1 的边}"""
    ec = collections.Counter()
    for ns in els:
        u = list(dict.fromkeys(ns))
        for i in range(len(u)):
            a, b = u[i], u[(i + 1) % len(u)]
            ec[(min(a, b), max(a, b))] += 1
    return [k for k, v in ec.items() if v == 1]


def order_chain(ids, adj):
    """把一串节点按邻接关系排成一条链; 优先从度=1 的端点起走"""
    ids = set(ids)
    if not ids:
        return []
    sub = {n: [m for m in adj.get(n, ()) if m in ids] for n in ids}
    ends = [n for n in ids if len(sub[n]) == 1]
    start = ends[0] if ends else min(ids)
    chain, prev, cur = [start], None, start
    while True:
        nxt = [m for m in sub[cur] if m != prev and m not in chain]
        if not nxt:
            break
        # 多个候选时取"没走过的"里第一个（边界是单链，正常只有 1 个）
        prev, cur = cur, nxt[0]
        chain.append(cur)
    return chain


def boundary_rings(els, nodes):
    """单元集 -> 有序轮廓环列表（按面积降序）"""
    fe = free_edges(els)
    if not fe:
        return []
    nb = collections.defaultdict(list)
    for u, v in fe:
        nb[u].append(v)
        nb[v].append(u)
    seen, rings = set(), []
    for s in sorted(nb):
        if s in seen:
            continue
        st, grp = [s], set()
        while st:
            q = st.pop()
            if q in grp:
                continue
            grp.add(q)
            st.extend(m for m in nb[q] if m not in grp)
        seen |= grp
        ch = order_chain(grp, nb)
        if len(ch) >= 3:
            area = abs(sum(nodes[ch[i]][0] * nodes[ch[(i + 1) % len(ch)]][1] -
                           nodes[ch[(i + 1) % len(ch)]][0] * nodes[ch[i]][1]
                           for i in range(len(ch)))) / 2
            rings.append((area, ch))
    rings.sort(key=lambda t: -t[0])
    return rings


def point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def convex_hull(pts):
    pts = sorted(set((round(p[0], 4), round(p[1], 4)) for p in pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo = []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", required=True)
    ap.add_argument("--belt", type=int, default=2)
    ap.add_argument("--tether", type=int, default=5)
    ap.add_argument("--cav", type=int, default=3)
    ap.add_argument("--out", default="anchors.json")
    ap.add_argument("--png", default="")
    a = ap.parse_args()

    nodes, els = read_k(a.k)
    belt = [ns for _, pid, ns in els if pid == a.belt]
    teth = [ns for _, pid, ns in els if pid == a.tether]
    cav_n = {n for _, pid, ns in els if pid == a.cav for n in ns}
    print(f"布带 {len(belt)} 单元  拉带 {len(teth)} 单元  节点 {len(nodes)}")

    # 布带自由边界 —— 只取【外边界】: 与气腔共节点的内边界必须排除。
    # 参考模型 5P-BAG_004 的判据是 tether∩cav = 0 (拉带只连布带, 不连气腔),
    # 若把内边界节点当锚固点, 拉带就会挂到气腔上, 直接违反该判据。
    fe = free_edges(belt)
    bnd_all = {n for e in fe for n in e}
    bnd = sorted(bnd_all - cav_n)
    print(f"布带自由边界: {len(fe)} 条边 / {len(bnd_all)} 节点 -> "
          f"外边界 {len(bnd)} (排除与气腔共享 {len(bnd_all)-len(bnd)})")

    nb = collections.defaultdict(list)
    for u, v in fe:
        nb[u].append(v)
        nb[v].append(u)

    # 拉带连通块
    adj_t = collections.defaultdict(set)
    for i, ns in enumerate(teth):
        for n in ns:
            for m in ns:
                if m != n:
                    adj_t[n].add(m)
    seen, blocks = set(), []
    for n in sorted(adj_t):
        if n in seen:
            continue
        st, grp = [n], set()
        while st:
            q = st.pop()
            if q in grp:
                continue
            grp.add(q)
            st.extend(m for m in adj_t[q] if m not in grp)
        seen |= grp
        blocks.append(grp)
    print(f"拉带连通块 {len(blocks)} 块, 规模 {sorted((len(b) for b in blocks), reverse=True)[:12]}")

    # 逐块: 真实轮廓环 -> 布带边界点落在环内 -> 按边界顺序成链
    result = []
    used_b = set()
    for bi, blk in enumerate(sorted(blocks, key=lambda s: -len(s))):
        sub = [e for e in teth if all(n in blk for n in e)]
        rings = boundary_rings(sub, nodes)
        if not rings:
            continue
        poly = [nodes[n][:2] for n in rings[0][1]]      # 最大环 = 外轮廓
        hull = convex_hull([nodes[n][:2] for n in blk])
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        inside = []
        for b in bnd:
            x, y, _ = nodes[b]
            if not (x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1):
                continue
            if point_in_poly((x, y), poly):
                inside.append(b)
        if not inside:
            continue
        ch = order_chain(inside, nb)
        if len(ch) < 3:
            continue
        used_b |= set(ch)
        pts = [nodes[n][:2] for n in ch]
        span = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        result.append({"blk": bi, "ids": ch, "chain": [list(p) for p in pts],
                       "n": len(ch), "span": round(span, 3),
                       "hull": [list(p) for p in hull]})
        print(f"  块{bi}: 外轮廓 {len(poly)} 点  锚固链 {len(ch)} 点  跨度 {span:.1f}mm  "
              f"X[{pts[0][0]:.1f},{pts[-1][0]:.1f}] Y[{min(p[1] for p in pts):.1f},{max(p[1] for p in pts):.1f}]")

    print(f"\n合计锚固链 {len(result)} 条 / {sum(r['n'] for r in result)} 节点"
          f"  (布带边界节点中被覆盖 {len(used_b)})")
    json.dump(result, open(a.out, "w", encoding="utf-8"), indent=1)
    print("写出", a.out)

    if a.png:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(11, 7))
            for ns in belt:
                ax.fill([nodes[n][0] for n in ns], [nodes[n][1] for n in ns],
                        facecolors="none", edgecolors="#d8dde3", linewidths=0.3)
            for blk in blocks:
                h = convex_hull([nodes[n][:2] for n in blk])
                if len(h) >= 3:
                    ax.fill([p[0] for p in h], [p[1] for p in h],
                            facecolors="#4a90d9", alpha=.18, edgecolors="#4a90d9", linewidths=.8)
            for r in result:
                p = r["chain"]
                ax.plot([q[0] for q in p], [q[1] for q in p], "-", color="#e5383b", lw=2.4)
                ax.plot([q[0] for q in p], [q[1] for q in p], "o", color="#e5383b", ms=4)
            ax.set_aspect("equal")
            ax.set_title(f"锚固链规划: {len(result)} 条 / {sum(r['n'] for r in result)} 节点")
            fig.tight_layout()
            fig.savefig(a.png, dpi=130)
            print("出图", a.png)
        except Exception as e:
            print("出图失败:", e)


if __name__ == "__main__":
    main()
