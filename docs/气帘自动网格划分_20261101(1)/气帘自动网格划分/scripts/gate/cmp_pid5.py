# -*- coding: utf-8 -*-
"""cmp_pid5.py — 逐 PID5 连通组分的单元/节点/包围盒/面积对比"""
import sys
sys.path.insert(0, ".")
import numpy as np
from render_anchor_side import read_k


def comps(nodes, els, pid):
    sub = [(eid, ns) for eid, p, ns in els if p == pid]
    par = {}

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb

    for _, ns in sub:
        for n in ns:
            par.setdefault(n, n)
        for i in range(1, len(ns)):
            uni(ns[0], ns[i])
    grp = {}
    for eid, ns in sub:
        grp.setdefault(find(ns[0]), []).append((eid, ns))
    out = []
    for k, lst in grp.items():
        nn = sorted({n for _, ns in lst for n in ns})
        P = np.array([nodes[n] for n in nn])
        area = 0.0
        for _, ns in lst:
            Q = np.array([nodes[n] for n in ns])
            a = 0.0
            for i in range(len(Q)):
                j = (i + 1) % len(Q)
                a += Q[i][0] * Q[j][1] - Q[j][0] * Q[i][1]
            area += abs(a) / 2
        out.append(dict(ne=len(lst), nn=len(nn), area=area,
                        x0=P[:,0].min(), x1=P[:,0].max(),
                        y0=P[:,1].min(), y1=P[:,1].max(), z=float(P[:,2].mean())))
    out.sort(key=lambda d: d["x0"])
    return out


def main():
    for tag, f in [("v3", sys.argv[1]), ("v4", sys.argv[2])]:
        nodes, els = read_k(f)
        print(f"\n===== {tag}  PID5 连通组分 =====")
        print(f"{'#':>2} {'单元':>5} {'节点':>5} {'面积mm²':>9} "
              f"{'X0':>8} {'X1':>8} {'Y0':>7} {'Y1':>7} {'Z':>5}")
        tot_a = tot_e = 0
        for i, c in enumerate(comps(nodes, els, 5)):
            tot_a += c["area"]; tot_e += c["ne"]
            print(f"{i:>2} {c['ne']:>5} {c['nn']:>5} {c['area']:>9.1f} "
                  f"{c['x0']:>8.1f} {c['x1']:>8.1f} {c['y0']:>7.1f} {c['y1']:>7.1f} {c['z']:>5.2f}")
        print(f"   合计 {tot_e} 单元 / 面积 {tot_a:.1f} mm²")


if __name__ == "__main__":
    main()
