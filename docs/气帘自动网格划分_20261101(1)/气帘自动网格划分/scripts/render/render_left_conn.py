# -*- coding: utf-8 -*-
"""渲染左拉带连接区(用户 2026-10-21 要求: 啮合点在拉带末端, 粘合线垂直布带长度方向)
面板: ① 全模型概览 ② R7(CURVE)连接放大 ③ R8(HORIZ)连接放大
共节点=红点, 布带=灰, R7=蓝, R8=绿, 竖直粘合线=红色虚线标注
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly
from matplotlib.collections import PatchCollection
import numpy as np

nodes = {}
sec = None
els = {}
import os
KPATH = os.environ.get('DECK', 'out/airbag_step1_2026.k')
for l in open(KPATH, encoding='utf-8', errors='replace'):
    s = l.strip()
    if s.startswith('*'):
        sec = s.upper().split()[0]
        continue
    if not s or s.startswith('$'):
        continue
    p = [x.strip() for x in s.split(',')]
    if sec == '*NODE':
        try:
            nodes[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))
        except (ValueError, IndexError):
            pass
    elif sec == '*ELEMENT_SHELL':
        try:
            pid = int(p[1])
            ns = [int(x) for x in p[2:] if x.strip()]
            els.setdefault(pid, []).append((int(p[0]), ns))
        except (ValueError, IndexError):
            pass

belt_nodes = set(n for _, ns in els.get(2, []) for n in ns)
p5 = els.get(5, [])


def ebbox(ns):
    pts = [(nodes[n][0], nodes[n][2]) for n in ns if n in nodes]
    if not pts:
        return None
    return (min(q[0] for q in pts), max(q[0] for q in pts),
            min(q[1] for q in pts), max(q[1] for q in pts))


# 按拉带真实几何包络分类 (CAD: R7 x977-1116 z1183-1259; R8 x908-1106 z938-964)
r7, r8, other_els = [], [], []
for eid, ns in p5:
    b = ebbox(ns)
    if b is None:
        continue
    x0, x1, z0, z1 = b
    if 970 <= x0 and x1 <= 1122 and 1178 <= z0 and z1 <= 1265:
        r7.append((eid, ns))
    elif 900 <= x0 and x1 <= 1112 and 933 <= z0 and z1 <= 970:
        r8.append((eid, ns))
    else:
        other_els.append((eid, ns))
print(f'PID5: R7={len(r7)}, R8={len(r8)}, bosses/others={len(other_els)}')


def draw_belt(ax, xlo, xhi, zlo, zhi):
    patches = []
    for _, ns in els.get(2, []):
        pts = [(nodes[n][0], nodes[n][2]) for n in ns if n in nodes]
        if pts and any(xlo - 50 < q[0] < xhi + 50 and zlo - 50 < q[1] < zhi + 50 for q in pts):
            if len(pts) >= 3:
                patches.append(MplPoly(pts, closed=True))
    if patches:
        pc = PatchCollection(patches, facecolor='#d0d0d0', edgecolor='#909090',
                             linewidth=0.3, alpha=0.85)
        ax.add_collection(pc)


def draw_region(ax, region, color):
    patches = []
    for _, ns in region:
        pts = [(nodes[n][0], nodes[n][2]) for n in ns if n in nodes]
        if len(pts) >= 3:
            patches.append(MplPoly(pts, closed=True))
    if patches:
        pc = PatchCollection(patches, facecolor=color, edgecolor='none', alpha=0.75)
        ax.add_collection(pc)


def draw_conodes(ax, region, label=True):
    cn = set()
    for _, ns in region:
        for n in ns:
            if n in belt_nodes:
                cn.add(n)
    if cn:
        cp = np.array([(nodes[n][0], nodes[n][2]) for n in cn])
        ax.scatter(cp[:, 0], cp[:, 1], c='red', s=45, zorder=6,
                   edgecolors='darkred', linewidths=0.5,
                   label=f'co-nodes {len(cn)}' if label else None)
        return cn
    return set()


fig, axes = plt.subplots(1, 3, figsize=(24, 8))

# ---- ① 概览 ----
ax = axes[0]
draw_belt(ax, 900, 3150, 550, 1400)
draw_region(ax, other_els, '#c8a0c8')
draw_region(ax, r7, '#4080ff')
draw_region(ax, r8, '#40c040')
draw_conodes(ax, r7 + r8, label=False)
ax.set_xlim(880, 3200); ax.set_ylim(550, 1420)
ax.set_aspect('equal')
ax.set_title('OVERVIEW  belt=gray  bosses=purple  R7=blue  R8=green  co-nodes=red')
ax.grid(True, alpha=0.3)

# ---- ② R7 连接放大 ----
ax = axes[1]
draw_belt(ax, 1040, 1260, 1140, 1290)
draw_region(ax, other_els, '#c8a0c8')
draw_region(ax, r7, '#4080ff')
cn7 = draw_conodes(ax, r7)
ax.set_xlim(1040, 1260); ax.set_ylim(1140, 1290)
ax.set_aspect('equal')
ax.set_title('R7 (CURVE) connection: vertical bonding line at strap tip')
ax.grid(True, alpha=0.3)
ax.legend(loc='lower left', fontsize=9)
if cn7:
    xs = [nodes[n][0] for n in cn7]
    zs = [nodes[n][2] for n in cn7]
    if xs:
        ax.plot([min(xs), max(xs)], [min(zs), min(zs)], 'r--', lw=1.2)
        ax.plot([min(xs), max(xs)], [max(zs), max(zs)], 'r--', lw=1.2)
        ax.annotate(f'bonding line\nx={np.mean(xs):.1f}, z {min(zs):.0f}~{max(zs):.0f}\n'
                    f'({len(xs)} co-nodes, vertical)',
                    xy=(np.mean(xs), (min(zs) + max(zs)) / 2),
                    xytext=(1085, 1265), fontsize=9, color='darkred',
                    arrowprops=dict(arrowstyle='->', color='darkred'))

# ---- ③ R8 连接放大 ----
ax = axes[2]
draw_belt(ax, 1030, 1140, 920, 990)
draw_region(ax, other_els, '#c8a0c8')
draw_region(ax, r8, '#40c040')
cn8 = draw_conodes(ax, r8)
ax.set_xlim(1030, 1140); ax.set_ylim(920, 990)
ax.set_aspect('equal')
ax.set_title('R8 (HORIZ) connection: vertical bonding line at strap tip')
ax.grid(True, alpha=0.3)
ax.legend(loc='lower left', fontsize=9)
if cn8:
    xs = [nodes[n][0] for n in cn8]
    zs = [nodes[n][2] for n in cn8]
    ax.plot([min(xs), max(xs)], [min(zs), min(zs)], 'r--', lw=1.2)
    ax.plot([min(xs), max(xs)], [max(zs), max(zs)], 'r--', lw=1.2)
    ax.annotate(f'bonding line\nx={np.mean(xs):.1f}, z {min(zs):.1f}~{max(zs):.1f}\n'
                f'({len(xs)} co-nodes, vertical)',
                xy=(np.mean(xs), (min(zs) + max(zs)) / 2),
                xytext=(1060, 975), fontsize=9, color='darkred',
                arrowprops=dict(arrowstyle='->', color='darkred'))

plt.tight_layout()
plt.savefig('out/v_left_conn.png', dpi=110)
print('saved out/v_left_conn.png')
if cn7:
    print('R7 co-nodes:', sorted((round(nodes[n][0], 2), round(nodes[n][2], 2))
                                 for n in cn7 if nodes[n][2] > 1150))
if cn8:
    print('R8 co-nodes:', sorted((round(nodes[n][0], 2), round(nodes[n][2], 2)) for n in cn8))
