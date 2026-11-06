"""充气口气腔捏合 (用户 2026-10-21 要求)
气腔 PID3 在充气口是一条对角缝隙: 上(Y+0.5)/下(Y-0.5)两层面各自的缝隙唇边节点 XZ 重合但各自独立
-> 26 条自由边(开口). 本脚本把重合的上下唇节点对捏合到中面 Y=0 (共享节点), 闭合缝隙,
   并剔除捏合后重合的镜像三角单元, 删除孤立旧节点.
幂等: 若端口已无自由边则跳过. 仅在 PID3 上操作, 不动 PID2/4/5.
"""
import collections, math, os

KPATH = os.environ.get("DECK", os.environ.get("WORKDIR", ".") + "/out/airbag_step1_2026.k")
CAV_PID = 3
TOL_XZ = 2.0

lines = open(KPATH, encoding="utf-8").read().split("\n")

# ---------- 解析 ----------
nodes = {}
elements = []              # (line_index, eid, pid, [n...])
sec = None
for i, l in enumerate(lines):
    s = l.strip()
    if s.startswith("*"):
        sec = s.upper().split()[0]; continue
    if not s or s.startswith("$"):
        continue
    if sec == "*NODE":
        f = [x.strip() for x in s.split(",")]
        try:
            nodes[int(f[0])] = (float(f[1]), float(f[2]), float(f[3]))
        except (ValueError, IndexError):
            pass
    elif sec == "*ELEMENT_SHELL":
        f = [x.strip() for x in s.split(",")]
        try:
            elements.append((i, int(f[0]), int(f[1]), [int(x) for x in f[2:] if x.strip()]))
        except (ValueError, IndexError):
            pass

# ---------- PID3 自由边 -> 端口节点 ----------
cav = [(i, eid, ns) for (i, eid, pid, ns) in elements if pid == CAV_PID]
def edge_set(ns):
    return [frozenset((ns[k], ns[(k+1) % len(ns)])) for k in range(len(ns))]
ec = collections.Counter()
for _, _, ns in cav:
    for ed in edge_set(ns):
        ec[ed] += 1
free_nodes = set(n for ed, c in ec.items() if c == 1 for n in ed)
print(f"PID3 单元 {len(cav)}, 端口自由边节点 {len(free_nodes)}")
if not free_nodes:
    print("端口已无自由边 -> 已捏合, 跳过")
    raise SystemExit

by_y = collections.defaultdict(list)
for n in free_nodes:
    if n in nodes:
        by_y[round(nodes[n][1], 1)].append(n)
top = by_y.get(0.5, []); bot = by_y.get(-0.5, []); mid = by_y.get(0.0, [])
print(f"  上(Y+0.5){len(top)} 下(Y-0.5){len(bot)} 中(Y0){len(mid)}")

# ---------- 上下唇 XZ 重合配对 -> 捏合到 Y=0 ----------
remap = {}
new_nodes = []
used_bot = set()
next_gid = max(nodes) + 1
pairs = 0
for t in sorted(top, key=lambda n: (nodes[n][2], nodes[n][0])):
    xt, _, zt = nodes[t]
    cand = [b for b in bot if b not in used_bot and math.hypot(nodes[b][0]-xt, nodes[b][2]-zt) <= TOL_XZ]
    if not cand:
        print(f"  !! 上节点 n{t} ({xt:.1f},{zt:.1f}) 无重合下节点, 跳过"); continue
    b = min(cand, key=lambda b: math.hypot(nodes[b][0]-xt, nodes[b][2]-zt))
    used_bot.add(b)
    xb, _, zb = nodes[b]
    g = next_gid; next_gid += 1
    new_nodes.append((g, (xt+xb)/2, 0.0, (zt+zb)/2))
    remap[t] = g; remap[b] = g
    pairs += 1
print(f"捏合配对 {pairs} 对 -> 新建 Y0 节点 {len(new_nodes)} (gid {new_nodes[0][0]}~{new_nodes[-1][0]})" if new_nodes else "无配对")

# ---------- 重写元素: remap + 去重 + 退化剔除 ----------
elem_line_ns = {}
seen_sets = {}
drop_lines = set()
touched = set(remap.keys())
for (i, eid, pid, ns) in elements:
    rns = [remap.get(n, n) for n in ns]
    elem_line_ns[i] = rns
    if any(n in touched for n in ns):
        u = tuple(dict.fromkeys(rns))
        if len(u) < 3:
            drop_lines.add(i); continue
        key = tuple(sorted(u))
        if key in seen_sets:
            drop_lines.add(i); continue
        seen_sets[key] = eid

still_used = set()
for (i, eid, pid, ns) in elements:
    if i in drop_lines:
        continue
    still_used.update(elem_line_ns[i])
orphan = set(remap.keys()) - still_used
print(f"丢弃单元 {len(drop_lines)}, 孤立旧节点 {len(orphan)}")

# ---------- 写回 ----------
line_eid_pid = {i: (eid, pid) for (i, eid, pid, ns) in elements}
out = []
sec = None
node_open = False
for i, l in enumerate(lines):
    s = l.strip()
    if s.startswith("*"):
        if sec == "*NODE" and node_open:
            for g, x, y, z in new_nodes:
                out.append(f"{g}, {x:.6f}, {y:.6f}, {z:.6f}")
            node_open = False
        sec = s.upper().split()[0]
        out.append(l)
        if sec == "*NODE":
            node_open = True
        continue
    if sec == "*NODE":
        f = [x.strip() for x in s.split(",")]
        try:
            if int(f[0]) in orphan:
                continue
        except (ValueError, IndexError):
            pass
        out.append(l)
    elif sec == "*ELEMENT_SHELL":
        if i in drop_lines:
            continue
        if i in elem_line_ns:
            eid, pid = line_eid_pid[i]
            out.append(f"{eid}, {pid}, " + ", ".join(str(n) for n in elem_line_ns[i]))
        else:
            out.append(l)
    else:
        out.append(l)

# 文件末尾若 *NODE 是最后一段, 补新节点
if node_open:
    for g, x, y, z in new_nodes:
        out.append(f"{g}, {x:.6f}, {y:.6f}, {z:.6f}")

open(KPATH, "w", encoding="utf-8", newline="\n").write("\n".join(out))
print(f"K 已更新: 节点 -{len(orphan)} +{len(new_nodes)}, 单元 -{len(drop_lines)}")
