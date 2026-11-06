# -*- coding: utf-8 -*-
"""qa_full2.py — cab1_full.k (自由格式) 全量 QA
兼容两种格式: 有逗号=自由格式(按逗号切); 无逗号=定宽(按位置切)
"""
import numpy as np
from collections import Counter, defaultdict

K = r"./out/cab1_full.k"
lines = open(K, encoding="utf-8", errors="ignore").read().splitlines()

nodes, elems = {}, []
sec = None
skip_name = False
for line in lines:
    s = line.strip()
    if s.startswith("*"):
        sec = s.upper()
        skip_name = sec in ("*PART", "*SECTION_SHELL_TITLE",
                            "*MAT_PIECEWISE_LINEAR_PLASTICITY_TITLE")
        continue
    if not s or s.startswith("$"):
        continue
    if skip_name:
        skip_name = False
        continue
    p = s.split(",") if "," in s else s.split()
    if sec == "*NODE":
        nodes[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))
    elif sec == "*ELEMENT_SHELL":
        nids = [int(x) for x in p[2:6] if int(x) != 0]
        elems.append((int(p[0]), int(p[1]), nids))

print(f"nodes={len(nodes)} elems={len(elems)}")
print("PID 分布:", dict(Counter(p for _, p, _ in elems)))

# 1. 重复坐标
cm = defaultdict(list)
for n, c in nodes.items():
    cm[(round(c[0], 6), round(c[1], 6), round(c[2], 6))].append(n)
dup = {k: v for k, v in cm.items() if len(v) > 1}
print(f"[1] 重复坐标节点组: {len(dup)}")

# 2. 引用完整性 + 孤儿
used = set()
for _, _, nids in elems:
    used.update(nids)
miss = sum(1 for _, _, nids in elems for n in nids if n not in nodes)
orph = [n for n in nodes if n not in used]
print(f"[2] 引用缺失节点: {miss}, 零引用孤儿: {len(orph)}")

# 3. bbox
a = np.array(list(nodes.values()))
print(f"[3] bbox: x[{a[:,0].min():.1f},{a[:,0].max():.1f}] "
      f"y[{a[:,1].min():.2f},{a[:,1].max():.2f}] z[{a[:,2].min():.1f},{a[:,2].max():.1f}]")

# 4. 最小单元尺寸 (跳过三角的 n3==n4 重复)
print("[4] 最短边:")
for pid in sorted(set(p for _, p, _ in elems)):
    mn = 1e18; mne = None; lens = []
    for e, p, nids in elems:
        if p != pid:
            continue
        pts = [nodes[n] for n in nids]
        m = len(pts)
        for i in range(m):
            L = np.linalg.norm(np.array(pts[(i + 1) % m]) - np.array(pts[i]))
            if L > 1e-9:
                lens.append(L)
            if 1e-9 < L < mn:
                mn, mne = L, e
    lens = np.array(lens)
    print(f"    PID{pid}: min={mn:.3f} (e{mne}) n<3mm={int((lens < 3).sum())}")

# 5. 自由边/非流形 (每部件内 + 部件间共节点)
ec = defaultdict(list)
for e, pid, nids in elems:
    m = len(nids)
    for i in range(m):
        ec[frozenset((nids[i], nids[(i + 1) % m]))].append((pid, e))
share = Counter(len(v) for v in ec.values())
print(f"[5] 边共享数分布: {dict(sorted(share.items()))}  (1=自由边 2=流形 3+=非流形)")

# 6. PID5∩PID2 共节点 (拉带-布带连接)
n5 = set()
for _, p, nids in elems:
    if p == 5:
        n5.update(nids)
n2 = set()
for _, p, nids in elems:
    if p == 2:
        n2.update(nids)
print(f"[6] PID5∩PID2 共节点: {len(n5 & n2)}")

# 7. 关键词序列
kws = [l.strip() for l in lines if l.startswith("*")]
print(f"[7] 关键词: {kws}")
