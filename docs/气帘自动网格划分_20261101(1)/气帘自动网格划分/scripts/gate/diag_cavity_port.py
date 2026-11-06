"""诊断气腔(PID3)网格结构, 定位充气口: 自由边(开口)分布 / Y 分层 / 端点集中区"""
import collections, math, os
KPATH = os.environ.get("DECK", os.environ.get("WORKDIR", ".") + "/out/airbag_step1_2026.k")
nodes = {}
sec = None
for l in open(KPATH, encoding="utf-8"):
    s = l.strip()
    if s.startswith("*"):
        sec = s.upper().split()[0]; continue
    if sec == "*NODE" and s and not s.startswith("$"):
        f = [x.strip() for x in s.split(",")]
        try: nodes[int(f[0])] = (float(f[1]), float(f[2]), float(f[3]))
        except: pass

# 各 PID 单元
elems = collections.defaultdict(list)   # pid -> list of node-tuples
sec = None
for l in open(KPATH, encoding="utf-8"):
    s = l.strip()
    if s.startswith("*"):
        sec = s.upper().split()[0]; continue
    if sec == "*ELEMENT_SHELL" and s and not s.startswith("$"):
        p = [x.strip() for x in s.split(",")]
        try:
            pid = int(p[1]); ns = tuple(int(x) for x in p[2:] if x.strip())
            elems[pid].append(ns)
        except: pass

print("PID 单元数:", {pid: len(v) for pid, v in sorted(elems.items())})

cav = elems.get(3, [])
print(f"\n气腔 PID3: {len(cav)} 单元")
# Y 分层
ys = collections.Counter(round(nodes[n][1], 2) for e in cav for n in e)
print("Y 值分布:", dict(ys))

# 自由边: 边只属于 1 个单元
def edges(e):
    r = []
    m = len(e)
    for i in range(m):
        a, b = e[i], e[(i+1) % m]
        r.append(frozenset((a, b)))
    return r
edge_count = collections.Counter()
for e in cav:
    for ed in edges(e):
        edge_count[ed] += 1
free = [ed for ed, c in edge_count.items() if c == 1]
print(f"自由边(开口): {len(free)}")

# 自由边节点坐标分布: 按 X 分段统计
def midpt(ed):
    pts = [nodes[n] for n in ed]
    return (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts), sum(p[2] for p in pts)/len(pts))
xs = []; zs = []; ys_f = []
for ed in free:
    mx, my, mz = midpt(ed)
    xs.append(mx); ys_f.append(my); zs.append(mz)
if xs:
    print(f"自由边 X 范围 [{min(xs):.0f},{max(xs):.0f}], Y [{min(ys_f):.2f},{max(ys_f):.2f}], Z [{min(zs):.0f},{max(zs):.0f}]")
    # X 直方图 (每 100mm)
    hist = collections.Counter(int(x//100)*100 for x in xs)
    print("自由边 X 直方图 (每100mm):")
    for k in sorted(hist):
        print(f"  X[{k:5d},{k+100:5d}): {hist[k]:4d}")

# 气腔整体 X 范围 + 各 X 端点的 Y 分布(看端口两层面是否分开)
allcx = [nodes[n][0] for e in cav for n in e]
print(f"\n气腔 X 范围 [{min(allcx):.0f},{max(allcx):.0f}]")
