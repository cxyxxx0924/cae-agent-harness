import collections, math

f = os.environ.get("DECK", "out/airbag_step1_2026.k")
import os
sec = None
nodes = {}
elems = []
for l in open(f, encoding="utf-8"):
    t = l.strip()
    if t.startswith("*"):
        sec = t.upper().split()[0]
        continue
    if not t or t.startswith("$"):
        continue
    p = [x.strip() for x in t.split(",")]
    if sec == "*NODE":
        try:
            nodes[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))
        except (ValueError, IndexError):
            pass
    elif sec == "*ELEMENT_SHELL":
        try:
            elems.append((int(p[0]), int(p[1]), tuple(int(x) for x in p[2:] if x.strip())))
        except (ValueError, IndexError):
            pass

print(f"nodes {len(nodes)}, elems {len(elems)}")

# 找长边: XZ 平面距离 > 20mm 即视为"飞丝"候选
LONG = 20.0
long_edges = collections.Counter()      # (pid) -> count
samples = collections.defaultdict(list)
for eid, pid, ns in elems:
    k = len(ns)
    for i in range(k):
        a, b = ns[i], ns[(i + 1) % k]
        pa, pb = nodes[a], nodes[b]
        d = math.hypot(pa[0] - pb[0], pa[2] - pb[2])
        if d > LONG:
            long_edges[pid] += 1
            if len(samples[pid]) < 6:
                samples[pid].append((eid, a, b, round(d, 1), pa, pb))

print(f"\nedges longer than {LONG}mm (XZ), by pid:")
for pid, c in sorted(long_edges.items()):
    print(f"  PID{pid}: {c}")
    for s in samples[pid]:
        print(f"    eid {s[0]}: n{s[1]}{s[4]} -> n{s[2]}{s[5]}  d={s[3]}mm")

# 也检查 3D 距离（排除纯 Y 向长边误报）
long3 = 0
for eid, pid, ns in elems:
    k = len(ns)
    for i in range(k):
        a, b = ns[i], ns[(i + 1) % k]
        pa, pb = nodes[a], nodes[b]
        d3 = math.dist(pa, pb)
        if d3 > 30.0:
            long3 += 1
print(f"\n3D edges > 30mm total: {long3}")
