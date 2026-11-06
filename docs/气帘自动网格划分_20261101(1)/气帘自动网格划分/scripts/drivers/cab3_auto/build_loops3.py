# -*- coding: utf-8 -*-
"""正确闭合环 v3：显式环序 + orient_cyclic 定向 + 缺口直线桥接。
belt: comp2 全 67 线(去 266) + 桥线[773,815,814]
cavity: comp3 全 109 - 3 小闭环(15) = 94 线, 另 3 小闭环作洞
"""
import json, math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Polygon as MplPoly

fp = 'C:/Windows/Fonts/msyh.ttc'
font_manager.fontManager.addfont(fp)
plt.rcParams['font.sans-serif'] = font_manager.FontProperties(fname=fp).get_name()
plt.rcParams['axes.unicode_minus'] = False

import os
P = (os.environ.get('WORKDIR') or './cab3').rstrip('/') + '/'
raw = {}
for ln in open(P + 'lines_pts_all.txt', encoding='utf-8', errors='replace'):
    if '|' not in ln:
        continue
    h, rest = ln.split('|', 1)
    p = h.split()
    if len(p) < 7:
        continue
    try:
        comp = p[0]; lid = int(p[1])
        sp = (float(p[3]), float(p[4])); ep = (float(p[5]), float(p[6]))
    except Exception:
        continue
    pts = []
    for s in rest.strip().split(';'):
        s = s.strip()
        if not s:
            continue
        a = s.split()
        if len(a) >= 2:
            pts.append((float(a[0]), float(a[1])))
    if pts:
        raw[lid] = dict(comp=comp, sp=sp, ep=ep, pts=pts)

TOL = 8.0


def orient_cyclic(order):
    seq = [(order[0], True)]
    prev_end = raw[order[0]]['ep']
    for lid in order[1:]:
        sp, ep = raw[lid]['sp'], raw[lid]['ep']
        d_sp = math.hypot(sp[0] - prev_end[0], sp[1] - prev_end[1])
        d_ep = math.hypot(ep[0] - prev_end[0], ep[1] - prev_end[1])
        if d_sp < 1e-6:
            fwd = True
        elif d_ep < 1e-6:
            fwd = False
        elif d_sp < TOL and d_ep < TOL:
            fwd = (d_sp <= d_ep)
        elif d_sp < TOL:
            fwd = True
        elif d_ep < TOL:
            fwd = False
        else:
            fwd = True
        seq.append((lid, fwd))
        prev_end = raw[lid]['ep'] if fwd else raw[lid]['sp']
    return seq


def chain_from_seq(seq, eps=0.02):
    chain = []; gaps = []
    prev = None; prev_lid = None
    for lid, fwd in seq:
        d = raw[lid]
        pp = d['pts'] if fwd else d['pts'][::-1]
        if prev is not None:
            g = math.hypot(pp[0][0] - prev[0], pp[0][1] - prev[1])
            if g > 0.05:
                gaps.append((prev_lid, lid, g))
        for pt in pp:
            if not chain or math.hypot(pt[0] - chain[-1][0], pt[1] - chain[-1][1]) > eps:
                chain.append(pt)
        prev = pp[-1]; prev_lid = lid
    return chain, gaps


BELT_ORDER = [1, 549, 805, 269, 806, 312, 807, 808, 809, 810, 811, 812, 813,
              766, 767, 768, 769, 770, 771, 772, 773, 815, 814,
              774, 775, 776, 777, 778, 779, 780, 781, 782, 783, 784, 454, 455,
              357, 785, 402, 786, 449, 787, 487, 504, 97, 264, 96, 263, 80, 788, 789,
              790, 791, 792, 793, 794, 795,
              796, 797, 798, 799, 800, 801, 802, 803,
              804, 262, 267, 268]

CAV_ORDER = [814, 652, 653, 502, 505, 500, 611, 499, 610, 501, 506, 503,
             654, 655, 656, 657, 658, 659, 660, 661, 662, 663, 664, 665, 666, 667, 668, 669,
             670, 671, 672, 673, 674, 675, 676, 677, 678, 679, 680, 686, 687, 688, 689,
             690, 691, 692, 693, 694, 695, 696, 697, 703, 704, 705, 706, 707, 708, 709,
             715, 716, 717, 718, 719, 720, 721, 722, 723, 724, 725, 726, 727, 728, 729, 730, 731, 732,
             733, 734, 735, 736, 737, 738, 739, 740, 741, 742, 743, 744, 745, 746, 747,
             750, 7730, 815]

HOLES = [[681, 682, 683, 684, 685], [698, 699, 700, 701, 702], [710, 711, 712, 713, 714]]

comp2 = sorted([l for l, d in raw.items() if d['comp'] == '2'])
comp3 = sorted([l for l, d in raw.items() if d['comp'] == '3'])

# ---- 特殊处理：comp3 线 750 的终点落在 comp3 线 773 上。
#      布带环用 773 全长；气腔环在 750->773 交界处把 773 切成两段，
#      气腔环只走"交界点 -> 815"那一段，避免回路 spike / 自交。
SPLIT_AT = raw[750]['ep']
_p773 = raw[773]['pts']
_d = [math.hypot(p[0] - SPLIT_AT[0], p[1] - SPLIT_AT[1]) for p in _p773]
_i = _d.index(min(_d))
assert _d[_i] < 0.5, '750 endpoint not on 773 (d=%.3f)' % _d[_i]
raw[7730] = dict(comp='3', sp=tuple(_p773[_i]), ep=raw[773]['ep'], pts=_p773[_i:])
print('773 split at idx %d -> 7730 has %d pts' % (_i, len(_p773) - _i))

_belt_ref = sorted([l for l in comp2 if l != 266] + [773, 815, 814])
_cav_ref = sorted([l for l in comp3 if l not in [x for h in HOLES for x in h]])
assert sorted(BELT_ORDER) == _belt_ref, 'belt order mismatch'
assert sorted([l if l != 7730 else 773 for l in CAV_ORDER]) == _cav_ref, 'cav order mismatch'
print('order check OK: belt %d lines, cavity %d lines' % (len(BELT_ORDER), len(CAV_ORDER)))


def poly_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def report(name, order):
    seq = orient_cyclic(order)
    ch, gaps = chain_from_seq(seq)
    cg = math.hypot(ch[0][0] - ch[-1][0], ch[0][1] - ch[-1][1])
    a = abs(poly_area(ch))
    print('[%s] npts=%d area=%.1f close_gap=%.3f gaps=%d' % (name, len(ch), a, cg, len(gaps)))
    for g in gaps:
        print('    gap %s->%s : %.3f mm' % g)
    return ch, a, gaps


belt_ch, belt_area, belt_gaps = report('belt', BELT_ORDER)
cav_ch, cav_area, cav_gaps = report('cavity', CAV_ORDER)
holes = []
for i, h in enumerate(HOLES):
    hc, ha, hg = report('hole%d' % i, h)
    holes.append(dict(pts=hc, area=ha))

# 自交检查（简单：相邻非邻边求交太慢，用 matplotlib path 或跳过；改用射线法查点）
print('\nbelt_area=%.1f cavity_area=%.1f belt-cavity=%.1f' % (belt_area, cav_area, belt_area - cav_area))

fig, ax = plt.subplots(figsize=(16, 9))
for lid, d in raw.items():
    xs = [p[0] for p in d['pts']]; ys = [p[1] for p in d['pts']]
    c = {'1': '0.8', '2': 'tab:blue', '3': 'tab:red', '4': 'tab:green', '5': 'tab:orange'}[d['comp']]
    plt.plot(xs, ys, color=c, lw=0.7, alpha=0.45)
ax.add_patch(MplPoly(belt_ch, closed=True, facecolor='tab:blue', edgecolor='k', lw=1.4, alpha=0.35))
ax.add_patch(MplPoly(cav_ch, closed=True, facecolor='tab:red', edgecolor='k', lw=1.4, alpha=0.35))
for h in holes:
    ax.add_patch(MplPoly(h['pts'], closed=True, facecolor='white', edgecolor='k', lw=1.2))
plt.xlim(140, 640); plt.ylim(50, 212)
ax.set_aspect('equal')
plt.title('loops v3: belt(blue) / cavity(red) / holes(white)')
plt.grid(alpha=0.2, lw=0.4)
plt.tight_layout(); plt.savefig(P + 'v_loops_v3.png', dpi=110)
plt.close()

# 充气口区放大
fig, ax = plt.subplots(figsize=(15, 10))
for lid, d in raw.items():
    xs = [p[0] for p in d['pts']]; ys = [p[1] for p in d['pts']]
    if max(xs) < 380 or min(xs) > 640 or max(ys) < 155:
        continue
    c = {'1': '0.5', '2': 'tab:blue', '3': 'tab:red', '4': 'tab:green', '5': 'tab:orange'}[d['comp']]
    plt.plot(xs, ys, color=c, lw=1.6, alpha=0.9)
    plt.annotate('%s:%d' % (d['comp'], lid), (xs[len(xs) // 2], ys[len(ys) // 2]), fontsize=6.5,
                 color=c, ha='center', va='center',
                 bbox=dict(boxstyle='round,pad=0.1', fc='white', ec='none', alpha=0.8))
ax.add_patch(MplPoly(belt_ch, closed=True, facecolor='tab:blue', edgecolor='k', lw=1.6, alpha=0.35))
ax.add_patch(MplPoly(cav_ch, closed=True, facecolor='tab:red', edgecolor='k', lw=1.6, alpha=0.35))
plt.xlim(380, 640); plt.ylim(155, 212)
ax.set_aspect('equal')
plt.title('chongqikou qu v3')
plt.grid(alpha=0.2, lw=0.4)
plt.tight_layout(); plt.savefig(P + 'v_loops_v3_port.png', dpi=120)
plt.close()

json.dump(dict(belt=dict(pts=belt_ch, lines=BELT_ORDER, area=belt_area, gaps=belt_gaps),
               cavity=dict(pts=cav_ch, lines=[773 if l == 7730 else l for l in CAV_ORDER],
                           area=cav_area, gaps=cav_gaps),
               holes=[dict(pts=h['pts'], area=h['area']) for h in holes]),
          open(P + 'loops_v3.json', 'w'))
print('-> loops_v3.json')

# 自交终检
def selfint(ch):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    n = len(ch); bad = 0
    for a in range(n):
        for b in range(a + 2, n):
            if a == 0 and b == n - 1:
                continue
            p1, p2 = ch[a], ch[(a + 1) % n]; p3, p4 = ch[b], ch[(b + 1) % n]
            o1, o2, o3, o4 = o(p1, p2, p3), o(p1, p2, p4), o(p3, p4, p1), o(p3, p4, p2)
            if o1 * o2 < 0 and o3 * o4 < 0:
                bad += 1
    return bad
print('self-intersections: belt=%d cavity=%d' % (selfint(belt_ch), selfint(cav_ch)))
