# -*- coding: utf-8 -*-
"""render_anchor_cmp.py — v3 vs v4 锚固区网格对比（俯视 + 侧视）

用法: python render_anchor_cmp.py <v3.k> <v4.k> <cx> <cy> <half> <out.png>
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def read_k(path):
    nodes, els = {}, []
    sec = None
    for line in open(path, encoding="ascii", errors="ignore"):
        if line.startswith("*"):
            sec = line.strip().upper()
            continue
        if not line.strip() or line.lstrip().startswith("$"):
            continue
        t = line.replace(",", " ").split()
        if sec == "*NODE" and len(t) >= 4:
            try:
                nodes[int(t[0])] = (float(t[1]), float(t[2]), float(t[3]))
            except ValueError:
                pass
        elif sec.startswith("*ELEMENT_SHELL") and len(t) >= 5:
            try:
                pid = int(t[1])
                ns = [int(x) for x in t[2:6] if int(x) > 0]
            except ValueError:
                continue
            els.append((int(t[0]), pid, ns))
    return nodes, els


def quad_warp(P):
    P = np.asarray(P, float)
    if len(P) == 3:
        return 0.0
    n1 = np.cross(P[1] - P[0], P[2] - P[0])
    n2 = np.cross(P[2] - P[0], P[3] - P[0])
    a1, a2 = np.linalg.norm(n1), np.linalg.norm(n2)
    if a1 < 1e-12 or a2 < 1e-12:
        return 90.0
    return float(np.degrees(np.arccos(np.clip(np.dot(n1, n2) / (a1 * a2), -1, 1))))


def draw(ax, path, cx, cy, half, title, zex=8.0):
    nodes, els = read_k(path)
    belt = {n for _, p, ns in els if p == 2 for n in ns}
    teth = {n for _, p, ns in els if p == 5 for n in ns}
    shared = belt & teth

    def inside(ns):
        return all(abs(nodes[n][0] - cx) < half and abs(nodes[n][1] - cy) < half for n in ns)

    # ---- 俯视 ----
    polys, cols, lws = [], [], []
    for eid, pid, ns in els:
        if pid not in (2, 5) or len(ns) < 3 or not inside(ns):
            continue
        polys.append([(nodes[n][0], nodes[n][1]) for n in ns])
        if pid == 2:
            cols.append("#c9ced6"); lws.append(0.4)
        else:
            zs = {round(nodes[n][2], 2) for n in ns}
            if any(abs(z) < 0.01 for z in zs) and any(abs(z + 1.0) < 0.01 for z in zs):
                w = quad_warp([nodes[n] for n in ns])
                cols.append(plt.cm.RdYlGn_r(min(1.0, w / 60.0)))
                lws.append(0.7)
            else:
                cols.append("#4a90d9"); lws.append(0.4)
    ax.add_collection(PolyCollection(polys, facecolors=cols, edgecolors="#33383d",
                                     linewidths=lws, alpha=0.95))
    sh = [(nodes[n][0], nodes[n][1]) for n in shared
          if abs(nodes[n][0] - cx) < half and abs(nodes[n][1] - cy) < half]
    if sh:
        ax.plot([p[0] for p in sh], [p[1] for p in sh], "o", color="#ff8c00",
                ms=5.0, mec="#7a3b00", mew=0.6, zorder=5)
    ax.set_xlim(cx - half, cx + half)
    ax.set_ylim(cy - half, cy + half)
    ax.set_aspect("equal")
    ax.set_title(f"{title}   共节点 {len(shared)}", fontsize=10)
    ax.set_xticks([]); ax.set_yticks([])


def main():
    v3, v4, cx, cy, half, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), \
        float(sys.argv[4]), float(sys.argv[5]), sys.argv[6]
    fig, ax = plt.subplots(1, 2, figsize=(13, 6.6))
    draw(ax[0], v3, cx, cy, half, "v3（旧的：拉带独立划，硬吸附）")
    draw(ax[1], v4, cx, cy, half, "v4（新的：三刀切，锚固边对齐布带）")
    sm = plt.cm.ScalarMappable(cmap="RdYlGn_r", norm=plt.Normalize(0, 60))
    cb = fig.colorbar(sm, ax=ax, fraction=0.02, pad=0.02)
    cb.set_label("过渡单元翘曲 (°)", fontsize=9)
    fig.suptitle(f"拉带-布带锚固区（X {cx:.0f}±{half:.0f}, Y {cy:.0f}±{half:.0f}）"
                 f"  灰=布带  蓝=拉带本体  暖色=跨 Z 的过渡排  橙点=共节点",
                 fontsize=11)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print("写出", out)


if __name__ == "__main__":
    main()
