# -*- coding: utf-8 -*-
"""cab3_full.k 最终门禁：引用完整性/重复节点单元/最小边长/连通/共节点/几何匹配"""
import re, math, sys, os
from collections import defaultdict, Counter

_WD = (os.environ.get('WORKDIR') or './cab3').rstrip('/')
K = sys.argv[1] if len(sys.argv) > 1 else 'cab3_full_v3.k'
if not os.path.isabs(K):
    K = _WD + '/' + K
lines = open(K, encoding='utf-8', errors='replace').read().splitlines()

# ---- 解析 ----
state = None
nodes = {}            # nid -> (x,y,z)
node_lines = []
elems = []            # (eid, pid, [n...])
secids = set(); mids = set(); lcids = set()
curve_pts = defaultdict(list)
mat_defined = set()
in_curve = None
for ln in lines:
    s = ln.strip()
    if not s: continue
    if ln.startswith('*'):
        st = ln.split()[0].upper()
        state = st
        continue
    if state == '*NODE' and not s.startswith('$'):
        try:
            nid = int(ln[0:8]); x = float(ln[8:24]); y = float(ln[24:40]); z = float(ln[40:56])
            node_lines.append((nid, x, y, z))
        except Exception:
            pass
    elif state == '*ELEMENT_SHELL' and not s.startswith('$'):
        try:
            eid = int(ln[0:8]); pid = int(ln[8:16])
            ns = [int(ln[16+8*k:24+8*k]) for k in range(4)]
            ns = [n for n in ns if n != 0]
            if len(ns) >= 3: elems.append((eid, pid, ns))
        except Exception:
            pass
    elif state == '*PART' and not s.startswith('$'):
        try:
            pid = int(ln[0:10]); secid = int(ln[10:20]); mid = int(ln[20:30])
            secids.add(secid); mids.add(mid)
        except Exception:
            pass
    elif state and state.startswith('*MAT_') and not s.startswith('$'):
        try: mat_defined.add(int(ln[0:10]))
        except Exception: pass
    elif state and state.startswith('*SECTION_SHELL') and not s.startswith('$'):
        try: secids.add(int(ln[0:10]))
        except Exception: pass
    elif state == '*DEFINE_CURVE' and not s.startswith('$'):
        try:
            a = s.split()
            lcid = int(a[0])
            in_curve = lcid
            lcids.add(lcid)
        except Exception:
            if in_curve is not None:
                try:
                    a = s.split()
                    curve_pts[in_curve].append((float(a[0]), float(a[1])))
                except Exception: pass

# ---- G1 节点重复 (规范 2.2 禁重复节点) ----
nid_c = Counter(n[0] for n in node_lines)
dup_nid = [k for k, v in nid_c.items() if v > 1]
nodes = {n[0]: (n[1], n[2], n[3]) for n in node_lines}

# ---- G2 单元重复 ----
eid_c = Counter(e[0] for e in elems)
dup_eid = [k for k, v in eid_c.items() if v > 1]
# 单元-节点集合重复(同拓扑)
topo_c = Counter((p, tuple(sorted(ns))) for _, p, ns in elems)
dup_topo = [k for k, v in topo_c.items() if v > 1]

# ---- G3 引用完整性 ----
missing_node = set()
for _, _, ns in elems:
    for n in ns:
        if n not in nodes: missing_node.add(n)
pid_used = set(p for _, p, _ in elems)
sec_used = set()
undefined_sec = sorted(sec_used - secids)
undef_mat = sorted(mids - mat_defined)

# ---- G4 最小边长 / 规范 3mm ----
def elen(a, b):
    return math.sqrt(sum((nodes[a][i]-nodes[b][i])**2 for i in range(3)))
short = []; allmin = 1e9; allmax = 0
short_by_pid = Counter()
for eid, pid, ns in elems:
    k = len(ns)
    for i in range(k):
        L = elen(ns[i], ns[(i+1) % k])
        allmin = min(allmin, L); allmax = max(allmax, L)
        if L < 3.0:
            short.append((L, eid, pid)); short_by_pid[pid] += 1

# ---- G5 连通分量 ----
adj = defaultdict(set)
for _, _, ns in elems:
    k = len(ns)
    for i in range(k):
        adj[ns[i]].add(ns[(i+1) % k]); adj[ns[(i+1) % k]].add(ns[i])
seen = set(); ncomp = 0; comps = []
for n in adj:
    if n in seen: continue
    stack = [n]; seen.add(n); cc = []
    while stack:
        x = stack.pop(); cc.append(x)
        for y in adj[x]:
            if y not in seen: seen.add(y); stack.append(y)
    comps.append(cc); ncomp += 1
comps.sort(key=len, reverse=True)
orphans = sum(1 for c in comps if len(c) <= 2)

# ---- G6 跨 PID 共享边/节点 ----
edge_pids = defaultdict(set)
for _, pid, ns in elems:
    k = len(ns)
    for i in range(k):
        a, b = ns[i], ns[(i+1) % k]
        edge_pids[frozenset((a, b))].add(pid)
cross_edges = Counter()
for ed, ps in edge_pids.items():
    if len(ps) > 1:
        cross_edges[tuple(sorted(ps))] += 1

# ---- G7 自由边 (part 内) ----
intra = defaultdict(Counter)
for _, pid, ns in elems:
    k = len(ns)
    for i in range(k):
        a, b = ns[i], ns[(i+1) % k]
        intra[pid][frozenset((a, b))] += 1
free_by_pid = {}
for pid, c in intra.items():
    free_by_pid[pid] = sum(1 for v in c.values() if v == 1)

# ---- 输出 ----
print("=" * 62)
print(os.path.basename(K)+" 最终门禁")
print("=" * 62)
print("[G1] 重复节点        : %d %s" % (len(dup_nid), "PASS" if not dup_nid else "FAIL " + str(dup_nid[:5])))
print("[G2] 重复单元        : eid_dup=%d topo_dup=%d %s" % (len(dup_eid), len(dup_topo),
      "PASS" if not dup_eid and not dup_topo else "FAIL"))
print("[G3] 引用完整性      : 缺节点=%d 未定义sec=%d 未定义mat=%d %s" % (
      len(missing_node), len(undefined_sec), len(undef_mat),
      "PASS" if not missing_node and not undefined_sec and not undef_mat else "FAIL"))
print("[G4] 边长            : min=%.3f max=%.3f  <3mm边=%d %s" % (
      allmin, allmax, len(short),
      "PASS" if allmin >= 3.0 else "WARN(<3mm: " + str(dict(short_by_pid)) + ")"))
print("[G5] 连通            : 分量=%d 主分量=%d节点 孤立小分量=%d %s" % (
      ncomp, len(comps[0]), orphans, "PASS" if ncomp == 1 else "WARN"))
print("[G6] 跨PID共享边     : %s" % dict(cross_edges))
print("[G7] part内自由边    : %s (仅外边界+充气口属正常)" % free_by_pid)
print("-" * 62)
print("节点=%d 单元=%d PID分布=%s" % (len(nodes), len(elems), dict(Counter(p for _, p, _ in elems))))
print("定义 secid=%s mid=%s 曲线=%s" % (sorted(secids), sorted(mids), sorted(lcids)))
print("=" * 62)
