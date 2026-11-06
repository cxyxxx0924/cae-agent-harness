# -*- coding: utf-8 -*-
"""全局环分析：按 comp 把所有 line 连成链，找出所有闭环/开链。
输出 JSON: loops_all.json + 控制台摘要。"""
import json, math, os
from collections import defaultdict

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
        raw[lid] = dict(sp=sp, ep=ep, pts=pts, comp=comp)

bycomp = defaultdict(list)
for lid, d in raw.items():
    bycomp[d['comp']].append(lid)
for c in bycomp:
    bycomp[c].sort()

TOL = 0.8  # mm 端点吸附


def chain_lines(lids):
    """把一组线连成链（贪心端点匹配）。返回 [chain]，chain=[(lid,fwd),...]"""
    remaining = list(lids)
    chains = []
    while remaining:
        # 从剩余中取一条作为种子
        seed = remaining.pop(0)
        chain = [seed]
        # 向前生长
        changed = True
        while changed:
            changed = False
            sp, ep = raw[chain[-1]]['sp'], raw[chain[-1]]['ep']
            # 找能接在尾部的
            best = None; bestd = 1e18; bestfwd = True
            for lid in remaining:
                s2, e2 = raw[lid]['sp'], raw[lid]['ep']
                d_s = math.hypot(ep[0] - s2[0], ep[1] - s2[1])
                d_e = math.hypot(ep[0] - e2[0], ep[1] - e2[1])
                if d_s < bestd:
                    bestd, best, bestfwd = d_s, lid, True
                if d_e < bestd:
                    bestd, best, bestfwd = d_e, lid, False
            if best is not None and bestd <= TOL:
                chain.append(best)
                remaining.remove(best)
                changed = True
            elif best is not None and bestd < 3.0:
                # 勉强接上（记录 gap 但继续）
                chain.append(best)
                remaining.remove(best)
                changed = True
            else:
                break
        # 反向生长
        changed = True
        while changed:
            changed = False
            sp = raw[chain[0]]['sp']
            best = None; bestd = 1e18; bestfwd = True
            for lid in remaining:
                s2, e2 = raw[lid]['sp'], raw[lid]['ep']
                d_e = math.hypot(sp[0] - e2[0], sp[1] - e2[1])
                d_s = math.hypot(sp[0] - s2[0], sp[1] - s2[1])
                if d_e < bestd:
                    bestd, best, bestfwd = d_e, lid, True
                if d_s < bestd:
                    bestd, best, bestfwd = d_s, lid, False
            if best is not None and bestd <= TOL:
                chain.insert(0, best)
                remaining.remove(best)
                changed = True
            elif best is not None and bestd < 3.0:
                chain.insert(0, best)
                remaining.remove(best)
                changed = True
            else:
                break
        chains.append(chain)
    return chains


def chain_pts(chain, fwd_first=True):
    out = []
    # 统一方向
    seq = [(chain[0], True)]
    prev = raw[chain[0]]['ep']
    for lid in chain[1:]:
        sp, ep = raw[lid]['sp'], raw[lid]['ep']
        ds = math.hypot(sp[0] - prev[0], sp[1] - prev[1])
        de = math.hypot(ep[0] - prev[0], ep[1] - prev[1])
        fwd = ds <= de
        seq.append((lid, fwd))
        prev = ep if fwd else sp
    for lid, fwd in seq:
        d = raw[lid]
        pts = d['pts'] if fwd else d['pts'][::-1]
        # 去重相邻点
        for pt in pts:
            if not out or math.hypot(pt[0] - out[-1][0], pt[1] - out[-1][1]) > 1e-6:
                out.append(pt)
    return out, seq


def poly_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return a / 2.0


result = {}
for comp, lids in sorted(bycomp.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 99):
    chains = chain_lines(lids)
    info = []
    for ch in chains:
        pts, seq = chain_pts(ch)
        closed = (len(ch) >= 3 and
                  math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1.5)
        a = poly_area(pts) if closed else 0.0
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        info.append(dict(lines=ch, closed=closed, area=abs(a),
                         npts=len(pts),
                         xrange=[round(min(xs), 2), round(max(xs), 2)],
                         yrange=[round(min(ys), 2), round(max(ys), 2)]))
    info.sort(key=lambda d: -d['area'])
    result['comp' + comp] = dict(n_lines=len(lids), n_chains=len(chains), chains=info)
    print('=== comp%s: %d lines -> %d chains ===' % (comp, len(lids), len(chains)))
    for i, c in enumerate(info):
        print('  chain%d: %d lines closed=%s area=%.0f X[%.1f,%.1f] Y[%.1f,%.1f]' %
              (i, len(c['lines']), c['closed'], c['area'],
               c['xrange'][0], c['xrange'][1], c['yrange'][0], c['yrange'][1]))
        print('    lines: %s' % c['lines'][:40] + (' ...' if len(c['lines']) > 40 else ''))

json.dump(result, open(P + 'loops_all.json', 'w'), indent=1)
print('\n-> loops_all.json')
