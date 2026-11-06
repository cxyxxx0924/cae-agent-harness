# -*- coding: utf-8 -*-
"""render_anchor_side.py — 锚固区【侧视】对比

侧视 = 横轴沿锚固链方向（X），纵轴 Z 放大 K 倍。
看得见的东西：布带那一排在 Z=0，拉带本体在 Z=-1，
中间那一条"跨 Z 过渡排"是不是宽度均匀、斜率一致、上下边对齐。

用法:
  python render_anchor_side.py <v3.k> <v4.k> <cx> <cy> <half> <out.png> [zex]
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


def classify(nodes, els, cx, cy, half):
    """返回 (多段线集合, 颜色集合, 统计)"""
    polys, cols = [], []
    tops, bots = [], []          # 过渡单元 上边(Z=0) / 下边(Z=-1) 的 X 区间
    for eid, pid, ns in els:
        if pid not in (2, 5) or len(ns) < 3:
            continue
        P = [nodes[n] for n in ns]
        if not all(abs(p[0] - cx) < half and abs(p[1] - cy) < half for p in P):
            continue
        polys.append([(p[0], p[2]) for p in P])
        zs = np.array([p[2] for p in P])
        if pid == 2:
            cols.append("#c9ced6")
            continue
        if (np.abs(zs) < 1e-6).any() and (np.abs(zs + 1.0) < 1e-6).any():
            cols.append("#e07a5f")                      # 跨 Z 过渡排
            top = [p[0] for p in P if abs(p[2]) < 1e-6]
            bot = [p[0] for p in P if abs(p[2] + 1.0) < 1e-6]
            if top and bot:
                tops.append((min(top), max(top)))
                bots.append((min(bot), max(bot)))
        else:
            cols.append("#4a90d9")                      # 拉带本体
    stat = {}
    if tops:
        w = [b - a for a, b in tops]
        off = [(b[0] + b[1]) / 2 - (a[0] + a[1]) / 2 for a, b in zip(tops, bots)]
        stat = dict(n=len(tops), wmin=min(w), wmax=max(w),
                    omin=min(off), omax=max(off),
                    ostd=float(np.std(off)))
    return polys, cols, stat


def draw(ax, path, cx, cy, half, title, zex=8.0):
    nodes, els = read_k(path)
    polys, cols, st = classify(nodes, els, cx, cy, half)
    ax.add_collection(PolyCollection(polys, facecolors=cols, edgecolors="#2b3035",
                                     linewidths=0.6, alpha=0.95))
    ax.axhline(0, color="#555", lw=1.0, ls="--")
    ax.axhline(-1.0, color="#555", lw=1.0, ls="--")
    ax.text(cx - half * 0.97, 0.06, "布带 Z=0", fontsize=8, color="#333",
            va="bottom")
    ax.text(cx - half * 0.97, -1.06, "拉带 Z=-1", fontsize=8, color="#333",
            va="top")
    sub = ""
    if st:
        sub = f"\n过渡 {st['n']} | 宽 {st['wmin']:.2f}~{st['wmax']:.2f}mm | " \
              f"错位 {st['omin']:+.2f}~{st['omax']:+.2f}mm σ={st['ostd']:.2f}"
    ax.set_title(title + sub, fontsize=9)
    ax.set_xlim(cx - half, cx + half)
    ax.set_ylim(-1.55, 0.55)
    ax.set_xlabel("X 沿锚固链 (mm)")
    ax.set_ylabel("Z（1mm 落差已纵向放大）")
    ax.set_yticks([])
    ax.grid(alpha=.18, lw=.4)


def main():
    v3, v4 = sys.argv[1], sys.argv[2]
    cx, cy, half = float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
    out = sys.argv[6]
    zex = float(sys.argv[7]) if len(sys.argv) > 7 else 8.0
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.0), sharey=True)
    draw(ax[0], v3, cx, cy, half, "v3  硬吸附（先划好再拉过去）", zex)
    draw(ax[1], v4, cx, cy, half, "v4  三刀切（锚固边直接生成布带节点）", zex)
    fig.suptitle(f"锚固区侧视  X {cx:.0f}±{half:.0f}  "
                 f"灰=布带  蓝=拉带本体  橙红=跨 Z 过渡排", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print("写出", out)


if __name__ == "__main__":
    main()
