# -*- coding: utf-8 -*-
"""左拉带连接 before/after 对比: bak_oldtabs(旧) vs airbag_step1_2026.k(新)"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly
from matplotlib.collections import PatchCollection
import numpy as np
import sys


def load(path):
    nodes = {}; sec = None; els = {}
    for l in open(path, encoding='utf-8', errors='replace'):
        s = l.strip()
        if s.startswith('*'):
            sec = s.upper().split()[0]; continue
        if not s or s.startswith('$'):
            continue
        p = [x.strip() for x in s.split(',')]
        if sec == '*NODE':
            try: nodes[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))
            except Exception: pass
        elif sec == '*ELEMENT_SHELL':
            try:
                pid = int(p[1]); ns = [int(x) for x in p[2:] if x.strip()]
                els.setdefault(pid, []).append(ns)
            except Exception: pass
    return nodes, els


def panel(ax, nodes, els, title, bad):
    belt_nodes = set(n for ns in els.get(2, []) for n in ns)
    patches = []
    for ns in els.get(2, []):
        pts = [(nodes[n][0], nodes[n][2]) for n in ns if n in nodes]
        if pts and any(1030 < q[0] < 1140 and 920 < q[1] < 990 for q in pts) and len(pts) >= 3:
            patches.append(MplPoly(pts, closed=True))
    if patches:
        ax.add_collection(PatchCollection(patches, facecolor='#d0d0d0',
                                          edgecolor='#909090', linewidth=0.3, alpha=0.85))
    r8 = [ns for ns in els.get(5, [])
          if all(900 <= nodes[n][0] <= 1112 and 933 <= nodes[n][2] <= 970 for n in ns if n in nodes)]
    patches = []
    for ns in r8:
        pts = [(nodes[n][0], nodes[n][2]) for n in ns if n in nodes]
        if len(pts) >= 3:
            patches.append(MplPoly(pts, closed=True))
    if patches:
        ax.add_collection(PatchCollection(patches, facecolor='#40c040', edgecolor='none', alpha=0.75))
    cn = set()
    for ns in r8:
        for n in ns:
            if n in belt_nodes:
                cn.add(n)
    if cn:
        cp = np.array([(nodes[n][0], nodes[n][2]) for n in cn])
        ax.scatter(cp[:, 0], cp[:, 1], c='red', s=50, zorder=6,
                   edgecolors='darkred', linewidths=0.5)
        if bad:
            # 标出错误共节点造成的长自由边
            ax.annotate(f'{len(cn)} co-nodes, SCATTERED\n(diagonal tip, zigzag noise)',
                        xy=(float(np.mean(cp[:, 0])), float(np.mean(cp[:, 1]))),
                        xytext=(1040, 975), fontsize=10, color='darkred',
                        arrowprops=dict(arrowstyle='->', color='darkred'))
        else:
            xs = cp[:, 0]; zs = cp[:, 1]
            ax.plot([xs.min(), xs.max()], [zs.min(), zs.min()], 'r--', lw=1.2)
            ax.plot([xs.min(), xs.max()], [zs.max(), zs.max()], 'r--', lw=1.2)
            ax.annotate(f'{len(cn)} co-nodes on ONE vertical line\nx={np.mean(xs):.1f}, '
                        f'z {zs.min():.1f}~{zs.max():.1f}',
                        xy=(float(np.mean(xs)), float((zs.min() + zs.max()) / 2)),
                        xytext=(1040, 975), fontsize=10, color='darkred',
                        arrowprops=dict(arrowstyle='->', color='darkred'))
    ax.set_xlim(1030, 1140); ax.set_ylim(920, 990)
    ax.set_aspect('equal'); ax.grid(True, alpha=0.3)
    ax.set_title(title, fontsize=12)


n1, e1 = load('out/airbag_step1_2026.bak_oldtabs_portfixed.k')
n2, e2 = load('out/airbag_step1_2026.k')
fig, axes = plt.subplots(1, 2, figsize=(18, 7))
panel(axes[0], n1, e1, 'BEFORE (2026-10-20): whole-overlap merge + zigzag tip', True)
panel(axes[1], n2, e2, 'AFTER (2026-10-21): single VERTICAL bonding line at strap tip', False)
plt.suptitle('R8 (HORIZ) left strap connection: belt=gray, strap=green, co-nodes=red', fontsize=13)
plt.tight_layout()
plt.savefig('out/v_r8_before_after.png', dpi=110)
print('saved out/v_r8_before_after.png')
