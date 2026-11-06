"""验证 2026 第一步网格: 分组统计 / 界面共节点 / 边界贴合环曲线"""
import math, collections, pathlib, os

P = pathlib.Path(os.environ.get("WORKDIR", r".")) / "out"
mesh = P / "step1_mesh_2026.txt"

nodes = {}
elems = collections.defaultdict(list)   # tag -> [(eid, [nids])]
for line in open(mesh, encoding="utf-8"):
    f = line.replace("{", " ").replace("}", " ").split()
    if not f:
        continue
    if f[0] == "N":
        nodes[int(f[1])] = (float(f[2]), float(f[3]), float(f[4]))
    elif f[0] == "S":
        elems[f[1]].append((int(f[2]), [int(x) for x in f[3:]]))

print("=== 分组统计 ===")
tot = 0
for tag in sorted(elems):
    es = elems[tag]
    nq = sum(1 for _, ns in es if len(ns) == 4)
    nt = sum(1 for _, ns in es if len(ns) == 3)
    nd = set()
    for _, ns in es:
        nd.update(ns)
    area = 0.0
    for _, ns in es:
        u = list(dict.fromkeys(ns))
        if len(u) >= 3:
            for i in range(1, len(u) - 1):
                a, b, c = nodes[u[0]], nodes[u[i]], nodes[u[i + 1]]
                area += abs((b[0]-a[0])*(c[2]-a[2]) - (c[0]-a[0])*(b[2]-a[2])) / 2
    tot += len(es)
    print(f"  {tag:6s} elems={len(es):6d} quad={nq:6d} tria={nt:5d} nodes={len(nd):6d} area={area:10.1f}")
print(f"  合计 elems={tot}  nodes={len(nodes)}")


def boundary_nodes(tag):
    """只被一个单元使用的边 → 边界边 → 其节点"""
    ec = collections.Counter()
    for _, ns in elems[tag]:
        u = list(dict.fromkeys(ns))
        for i in range(len(u)):
            a, b = u[i], u[(i + 1) % len(u)]
            ec[(min(a, b), max(a, b))] += 1
    bn = set()
    for (a, b), c in ec.items():
        if c == 1:
            bn.add(a); bn.add(b)
    return bn


def nodes_of(tag):
    s = set()
    for _, ns in elems[tag]:
        s.update(ns)
    return s

print("\n=== 界面共节点 ===")
seam_tags = [t for t in sorted(elems) if t.startswith("seam")]
seam_all = set()
for t in seam_tags:
    seam_all |= nodes_of(t)
cav_n = nodes_of("cav")
belt_n = nodes_of("belt")

for t in seam_tags:
    b = boundary_nodes(t)
    inter = b & cav_n
    print(f"  {t} 边界节点 {len(b):5d}  与 cav 共用 {len(inter):5d}  ({100*len(inter)/max(1,len(b)):.1f}%)")
sb = boundary_nodes("seam0")
cb = boundary_nodes("cav")
bb = boundary_nodes("belt")
print(f"  cav  边界节点 {len(cb):5d}  与 belt 共用 {len(cb & bb):5d}")
print(f"  belt 边界节点 {len(bb):5d}  与 cav  共用 {len(bb & cb):5d}")
print(f"  cav 边界 = 外轮廓(L3) + 5 洞边; 其中洞边节点 {(cb & seam_all).__len__()} 个落在缝面节点集内")

# 自由边 = 只被同组一个单元用且不被任何其他组单元用的节点 → 真破洞指示
allgroups = {t: nodes_of(t) for t in elems}
print("\n=== 跨组自由边检查（破洞指示）===")
for t in sorted(elems):
    ec = collections.Counter()
    for _, ns in elems[t]:
        u = list(dict.fromkeys(ns))
        for i in range(len(u)):
            a, b = u[i], u[(i + 1) % len(u)]
            ec[(min(a, b), max(a, b))] += 1
    internal = 0
    shared_other = 0
    freeedges = []
    for (a, b), c in ec.items():
        if c >= 2:
            internal += 1
        else:
            # 是否被别的组的单元用到
            used = any((a in allgroups[o]) and (b in allgroups[o])
                       and any(a in ns and b in ns for _, ns in elems[o])
                       for o in elems if o != t)
            if used:
                shared_other += 1
            else:
                freeedges.append((a, b))
    print(f"  {t:6s} 内部边={internal:6d} 与其他组共享边={shared_other:5d} 自由边(潜在破洞)={len(freeedges):5d}")
    if freeedges and len(freeedges) <= 8:
        for a, b in freeedges:
            print(f"        free {a}-{b}  {nodes[a]} {nodes[b]}")

# 单元质量
print("\n=== 质量 ===")
allq = []
for t in sorted(elems):
    mn = 1e9; mx = 0.0
    short = 0
    for _, ns in elems[t]:
        u = list(dict.fromkeys(ns))
        for i in range(len(u)):
            a, b = u[i], u[(i + 1) % len(u)]
            d = math.dist(nodes[a], nodes[b])
            mn = min(mn, d); mx = max(mx, d)
            if d < 3.0:
                short += 1
    print(f"  {t:6s} 边长 min={mn:.3f} max={mx:.3f}  <3mm 边数={short}")
    allq.append((mn, mx, short))
