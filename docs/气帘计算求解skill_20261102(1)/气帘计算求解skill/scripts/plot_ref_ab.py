#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
plot_ref_ab.py —— 把"本模型"和"参考模型"的锚点/拉带几何画成上下 A/B 对照图。

这是判断"锚点位置对不对"的唯一硬标准：**同图同比例，肉眼比对**。
比"看数字觉得别扭"可靠得多（本轮靠它确认了凸台顶面取点是对的，也与参考完全同构）。

用法
    python plot_ref_ab.py  <this_bag> <this_body> <this_spring> \
                           <ref_bag>  <ref_body>  <ref_spring>  [out.png]

示例
    python plot_ref_ab.py \
        s5_final/cab2_clean.k s5_final/BIW_clean.k s5_final/Spring_swap.k \
        ref/5P-BAG_005.key    ref/Vehicle.k       ref/Spring_move.k \
        img/compare_geometry.png

图上约定
    蓝  = 气帘壳单元     灰 = 车身壳单元
    红圆= 气帘端锚点     绿方= 车身端锚点     红线 = 拉绳

自动兼容两种 deck 格式（P-S82）：
    · 逗号自由格式（本技能生成的 deck）：*ELEMENT_SHELL = eid,pid,n1..n4
    · 8 字符定宽（多数参考 deck）：      *ELEMENT_SHELL = eid pid n1 n2 n3 n4
    判法：行内含逗号走自由格式，否则按 8 字符切。
"""
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection


# ---------------------------------------------------------------- deck 解析
def _fields(ln, n):
    """按行内是否有逗号自适应切字段"""
    if ',' in ln:
        s = ln.replace(',', ' ').split()
    else:
        s = [ln[i * 8:(i + 1) * 8] for i in range(n)]
    return [x for x in s if x.strip() != '']


def _blocks(path, kws):
    """按关键字块产出 (kw, 行列表)"""
    cur, buf = None, []
    for ln in open(path, encoding='ascii', errors='ignore'):
        u = ln.strip().upper()
        if u.startswith('*'):
            if cur is not None:
                yield cur, buf
            cur = next((k for k in kws if u.startswith(k)), None)
            buf = []
            continue
        if cur is None or ln.lstrip().startswith('$'):
            continue
        buf.append(ln.rstrip('\n'))
    if cur is not None:
        yield cur, buf


def read_nodes(path):
    """*NODE 定宽是 I8 + 3E16（坐标各占 16 字符），与 *ELEMENT_* 的 I8 不同！
    踩过：按 8 字符切会把 "2010.092155" 拆成 "20" + "10092155"，坐标全错。"""
    n = {}
    for kw, lines in _blocks(path, ('*NODE',)):
        if 'REFERENCE' in kw:
            continue
        for ln in lines:
            if ',' in ln:
                f = ln.replace(',', ' ').split()
                if len(f) >= 4:
                    try:
                        n[int(f[0])] = (float(f[1]), float(f[2]), float(f[3]))
                    except ValueError:
                        pass
                continue
            if len(ln) >= 56:
                try:
                    n[int(ln[0:8])] = (float(ln[8:24]), float(ln[24:40]), float(ln[40:56]))
                    continue
                except ValueError:
                    pass
            f = ln.split()
            if len(f) >= 4:
                try:
                    n[int(f[0])] = (float(f[1]), float(f[2]), float(f[3]))
                except ValueError:
                    pass
    return n


def read_shells(path):
    out = []
    for kw, lines in _blocks(path, ('*ELEMENT_SHELL',)):
        for ln in lines:
            if ',' in ln:
                f = ln.replace(',', ' ').split()
                if len(f) < 6:
                    continue
                try:
                    k = [int(float(x)) for x in f[2:6]]      # s[1] 是 pid，节点在 s[2:6]
                except ValueError:
                    continue
            else:
                if len(ln) < 48:
                    continue
                try:
                    k = [int(ln[i:i + 8]) for i in (16, 24, 32, 40)]
                except ValueError:
                    continue
            if k[0] > 0 and all(v > 0 for v in k):
                out.append(k)
    return out


def read_lines(path):
    """*ELEMENT_BEAM / *ELEMENT_DISCRETE：8 字符定宽 eid pid n1 n2"""
    out, seen = [], set()
    for kw, lines in _blocks(path, ('*ELEMENT_BEAM', '*ELEMENT_DISCRETE')):
        for ln in lines:
            if len(ln) < 33:
                continue
            try:
                eid = int(ln[0:8]); n1 = int(ln[16:24]); n2 = int(ln[24:32])
            except ValueError:
                continue
            if eid <= 0 or n1 <= 0 or n2 <= 0:
                continue
            key = tuple(sorted((n1, n2)))
            if key in seen:          # BEAM+DISCRETE 双定义，去重（P-S82 补充）
                continue
            seen.add(key)
            out.append((eid, n1, n2))
    return out


def segs(els, nd, axes=(0, 2)):
    i, j = axes
    out = []
    for k in els:
        ps = [nd.get(n) for n in k]
        if any(v is None for v in ps):
            continue
        for a in range(len(ps)):
            q, r = ps[a], ps[(a + 1) % len(ps)]
            out.append([(q[i], q[j]), (r[i], r[j])])
    return out


# ---------------------------------------------------------------- 主流程
def draw(ax, title, bag_k, body_k, spring_k):
    bn, wn = read_nodes(bag_k), read_nodes(body_k)
    be, we = read_shells(bag_k), read_shells(body_k)
    sp = read_lines(spring_k)
    ax.add_collection(LineCollection(segs(we, wn), colors='#c2c8d0', linewidths=0.25))
    ax.add_collection(LineCollection(segs(be, bn), colors='#2b7de9', linewidths=0.30))
    nrope = 0
    for eid, a, b in sp:
        if a in wn and b in bn:      # 统一成 (气帘端, 车身端)
            a, b = b, a
        if a in bn and b in wn:
            p, q = bn[a], wn[b]
            ax.plot([p[0], q[0]], [p[2], q[2]], '-', color='#e8442a', lw=1.8, zorder=5)
            ax.plot([p[0]], [p[2]], 'o', color='#e8442a', ms=5, zorder=6)
            ax.plot([q[0]], [q[2]], 's', color='#00a36c', ms=5, zorder=6)
            nrope += 1
    xs = [v[0] for v in bn.values()] + [v[0] for v in wn.values()]
    zs = [v[2] for v in bn.values()] + [v[2] for v in wn.values()]
    ax.set_xlim(min(xs) - 30, max(xs) + 30)
    ax.set_ylim(min(min(zs), 650) - 30, max(zs) + 30)
    ax.set_aspect('equal')
    ax.set_xlabel('X (mm)'); ax.set_ylabel('Z (mm)')
    ax.set_title('%s   ropes=%d  bagNodes=%d  bodyNodes=%d' % (title, nrope, len(bn), len(wn)))
    print('%-10s ropes=%-3d bag n=%-6d body n=%-6d  Z[%.1f,%.1f]'
          % (title.split()[0], nrope, len(bn), len(wn), min(zs), max(zs)))


def main():
    if len(sys.argv) < 7:
        print(__doc__)
        return 2
    out = sys.argv[7] if len(sys.argv) > 7 else 'compare_geometry.png'
    fig, axs = plt.subplots(2, 1, figsize=(22, 15))
    draw(axs[0], 'THIS MODEL (9 tabs + port, ropes vertical)', *sys.argv[1:4])
    draw(axs[1], 'REFERENCE (same convention)', *sys.argv[4:7])
    plt.tight_layout()
    plt.savefig(out, dpi=95)
    print('saved', out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
