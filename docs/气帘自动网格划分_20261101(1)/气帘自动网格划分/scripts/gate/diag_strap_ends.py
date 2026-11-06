# -*- coding: utf-8 -*-
"""分析当前 K 中 R7/R8 网格: 共节点 + 自由边(找端边)"""
import numpy as np
from collections import Counter

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

p5 = els.get(5, [])
belt_nodes = set(n for _, ns in els.get(2, []) for n in ns)

def free_edges(pid_els):
    ec = Counter()
    for _, ns in pid_els:
        for a, b in zip(ns, ns[1:] + ns[:1]):
            ec[tuple(sorted((a, b)))] += 1
    return [e for e, c in ec.items() if c == 1]

for name, zcond in (('R7', lambda z: z > 1100), ('R8', lambda z: z <= 1100)):
    sub = [(eid, ns) for eid, ns in p5
           if zcond(np.mean([nodes[n][2] for n in ns])) and
           np.mean([nodes[n][0] for n in ns]) < 1250]
    co = set()
    for eid, ns in sub:
        for n in ns:
            if n in belt_nodes:
                co.add(n)
    fe = free_edges(sub)
    print(f'=== {name}: {len(sub)} 单元, 共节点 {len(co)}, 自由边 {len(fe)} ===')
    # 共节点
    cp = sorted((nodes[n][0], nodes[n][2]) for n in co)
    for x, z in cp:
        print(f'   co-node x={x:8.2f} z={z:8.2f}')
    # 右端自由边 (X > 1050)
    rf = [(a, b) for a, b in fe if nodes[a][0] > 1050 and nodes[b][0] > 1050]
    print(f'   右端(X>1050)自由边 {len(rf)} 条:')
    for a, b in sorted(rf, key=lambda e: nodes[e[0]][0]):
        pa, pb = nodes[a], nodes[b]
        ln = ((pa[0]-pb[0])**2 + (pa[2]-pb[2])**2) ** 0.5
        print(f'     ({pa[0]:8.2f},{pa[2]:8.2f})-({pb[0]:8.2f},{pb[2]:8.2f}) 长{ln:5.1f}mm')
    # 右端所有节点
    rn = sorted(set(n for _, ns in sub for n in ns if nodes[n][0] > 1060))
    print(f'   右端(X>1060)节点 {len(rn)} 个, X[{min(nodes[n][0] for n in rn):.1f},{max(nodes[n][0] for n in rn):.1f}]')
    print()
