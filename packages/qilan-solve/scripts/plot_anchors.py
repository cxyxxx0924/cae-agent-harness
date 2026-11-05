# -*- coding: utf-8 -*-
"""XZ 视图：cab2 壳单元 + BIW 壳单元 + 10 根绳，检查锚点/绳走向"""
import sys, math, numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

DD = sys.argv[1] if len(sys.argv) > 1 else '.'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'img'

def read_kw(path, kw, nf):
    """按关键字块读取前 nf 个整数字段，返回 [(id, x, y, z)]"""
    rows = []; cur = False
    for ln in open(path, encoding='ascii', errors='ignore'):
        u = ln.strip().upper()
        if u.startswith('*'):
            cur = u.startswith(kw)
            continue
        if not cur or ln.lstrip().startswith('$'): continue
        s = ln.replace(',', ' ').split()
        if len(s) < 1 + nf: continue
        try: rows.append([int(s[0])] + [float(x) for x in s[1:1+nf]])
        except ValueError: pass
    return rows

def nodes(p):
    return {r[0]: (r[1], r[2], r[3]) for r in read_kw(p, '*NODE', 3)}

def shells(p):
    out = []
    for r in read_kw(p, '*ELEMENT_SHELL', 5):   # eid, pid, n1..n4
        k = [int(round(v)) for v in r[2:6]]
        if r[0] > 0 and all(v > 0 for v in k): out.append(k)
    return out

def beams(p):
    """*ELEMENT_BEAM / *ELEMENT_DISCRETE 是 8 字符定宽：eid pid n1 n2"""
    out = []; cur = False
    for ln in open(p, encoding='ascii', errors='ignore'):
        u = ln.strip().upper()
        if u.startswith('*'):
            cur = u.startswith('*ELEMENT_BEAM') or u.startswith('*ELEMENT_DISCRETE')
            continue
        if not cur or ln.lstrip().startswith('$') or len(ln) < 33: continue
        try:
            eid = int(ln[0:8]); n1 = int(ln[16:24]); n2 = int(ln[24:32])
        except ValueError: continue
        if eid > 0 and n1 > 0 and n2 > 0: out.append((eid, n1, n2))
    return out

bn = nodes(DD + '/cab2_clean.k'); wn = nodes(DD + '/BIW_clean.k')
be = shells(DD + '/cab2_clean.k'); we = shells(DD + '/BIW_clean.k')
sp = beams(DD + '/Spring_swap.k')
print('bag n=%d sh=%d | biw n=%d sh=%d | beams=%d' % (len(bn), len(be), len(wn), len(we), len(sp)))

def segs(el, nd, axes):
    """axes = (i, j) 取哪两个分量"""
    i, j = axes; out = []
    for k in el:
        pts = [nd.get(n) for n in k]
        if any(v is None for v in pts): continue
        for a in range(len(pts)):
            q, r = pts[a], pts[(a + 1) % len(pts)]
            out.append([(q[i], q[j]), (r[i], r[j])])
    return out

# XZ: 横轴 X，纵轴 Z；XY: 横轴 X，纵轴 Y
views = [('XZ', (0, 2), 'X (mm)', 'Z (mm)'), ('XY', (0, 1), 'X (mm)', 'Y (mm)')]

for name, axes, xl, yl in views:
    ia, ja = axes
    segb = segs(be, bn, axes)
    segw = segs(we, wn, axes)
    rp = [(bn[n1][ia], bn[n1][ja], wn[n2][ia], wn[n2][ja]) for (e, n1, n2) in sp if n1 in bn and n2 in wn]
    print(name, 'segb', len(segb), 'segw', len(segw), 'ropes', len(rp))
    allp = [p for sg in segb + segw for p in sg] + [[a, b] for (a, b, c, d) in rp] + [[c, d] for (a, b, c, d) in rp]
    A = np.array(allp, dtype=float)
    fig, ax = plt.subplots(figsize=(24, 9))
    ax.add_collection(LineCollection(segw, colors='#b9c0c9', linewidths=0.3))
    ax.add_collection(LineCollection(segb, colors='#2b7de9', linewidths=0.35))
    for (x1, y1, x2, y2) in rp:
        ax.plot([x1, x2], [y1, y2], '-', color='#e8442a', lw=1.8, zorder=5)
        ax.plot([x1], [y1], 'o', color='#e8442a', ms=5, zorder=6)
        ax.plot([x2], [y2], 's', color='#00a36c', ms=5, zorder=6)
    ax.set_xlim(A[:, 0].min() - 30, A[:, 0].max() + 30)
    ax.set_ylim(A[:, 1].min() - 30, A[:, 1].max() + 30)
    ax.set_aspect('equal'); ax.set_xlabel(xl); ax.set_ylabel(yl)
    ax.set_title('%s  bag=blue  body=grey  rope=red  bag-anchor=o  body-anchor=s' % name)
    plt.tight_layout(); plt.savefig('%s/anchors_%s.png' % (OUT, name.lower()), dpi=100)
    print('saved %s/anchors_%s.png' % (OUT, name.lower()))
    # zoom: 左端 tether1 区域（必须在 close 之前重设坐标）
    if name == 'XZ':
        ax.set_xlim(980, 1330); ax.set_ylim(600, 1260)
        ax.set_title('XZ zoom  left end (tether1/tether2)')
        plt.tight_layout(); plt.savefig('%s/anchors_zoom_left.png' % OUT, dpi=140)
        print('saved %s/anchors_zoom_left.png' % OUT)
    plt.close()
