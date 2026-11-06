# -*- coding: utf-8 -*-
"""render_pid5_map.py — 拉带分区覆盖图：逐连通组分着色，看有没有整块丢"""
import sys
sys.path.insert(0, ".")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from render_anchor_side import read_k

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

C = ["#e5383b", "#f4a261", "#2a9d8f", "#457b9d", "#8e7dbe",
     "#d4a373", "#90be6d", "#f28482", "#577590", "#b56576"]


def comps(nodes, els):
    sub = [(eid, ns) for eid, p, ns in els if p == 5]
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
    g = {}
    for eid, ns in sub:
        g.setdefault(find(ns[0]), []).append((eid, ns))
    out = []
    for _, lst in g.items():
        area = 0.0
        P = []
        for _, ns in lst:
            Q = [nodes[n] for n in ns]
            P += Q
            s = 0.0
            for i in range(len(Q)):
                j = (i + 1) % len(Q)
                s += Q[i][0] * Q[j][1] - Q[j][0] * Q[i][1]
            area += abs(s) / 2
        cx = sum(p[0] for p in P) / len(P)
        out.append((cx, lst, area))
    out.sort(key=lambda t: t[0])
    return out


def draw(ax, path, title):
    nodes, els = read_k(path)
    cs = comps(nodes, els)
    tot = sum(c[2] for c in cs)
    for i, (cx, lst, area) in enumerate(cs):
        polys = [[(nodes[n][0], nodes[n][1]) for n in ns] for _, ns in lst]
        col = C[i % len(C)]
        for p in polys:
            ax.fill([q[0] for q in p], [q[1] for q in p],
                    facecolor=col, edgecolor="#33383d", linewidth=0.15, alpha=.9)
        xs = [q[0] for p in polys for q in p]
        ys = [q[1] for p in polys for q in p]
        ax.text((min(xs) + max(xs)) / 2, max(ys) + 12, f"#{i}\n{area:.0f}",
                fontsize=6.5, ha="center", color="#222")
    ax.set_aspect("equal")
    ax.set_title(f"{title}   组分 {len(cs)} / 面积 {tot:.0f} mm²", fontsize=10)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.grid(alpha=.15, lw=.4)


def main():
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.6), sharey=True)
    draw(ax[0], sys.argv[1], sys.argv[3])
    draw(ax[1], sys.argv[2], sys.argv[4])
    fig.suptitle("拉带(PID5) 分区覆盖核对 —— 每块一个颜色，看有没有整块丢", fontsize=11)
    fig.tight_layout()
    fig.savefig(sys.argv[5], dpi=150, bbox_inches="tight")
    print("写出", sys.argv[5])


if __name__ == "__main__":
    main()
