"""拉带组装 v2: tabs mesh -> Y-1 分层 -> 与布带节点合并(参考 5P-BAG_004 模式) -> 合并进 airbag_step1_2026.k (PID5)
连接规则 (参考模型实证):
  - 参考 PID8(拉带) 与 PID6(单层布带) 有 115 个共节点, 拉带在重叠区爬到 Y0
  - 本脚本: 拉带节点距任一布带节点 <= TOL(3mm, XZ) -> 复用布带节点 gid (Y0, 真共节点)
  - 捏合用全局 1-to-1 贪心匹配(距离升序): 每个布带节点至多被一个拉带节点复用,
    从结构上杜绝"同一单元内两拉带节点映射到同一布带节点" -> 不丢任何单元(零退化)
  - 落空的密集处: 较远拉带节点保留为独立节点(取新 gid), 几何上贴着布带但不共节点
  - 坐标完全相同的拉带节点 (共享膝弦边两次离散) -> 合并为一个 gid
"""
import json, math, collections, os

P = os.environ.get("WORKDIR", ".") + "/out"
KPATH = os.environ.get("DECK", P + "/airbag_step1_2026.k")
Y_TAB = -1.0
TOL = 3.0

# ---------- 1. 读 K 文件节点 ----------
k_nodes = {}
sec = None
k_lines_raw = open(KPATH, encoding="utf-8").read().split("\n")
for l in k_lines_raw:
    s = l.strip()
    if s.startswith("*"):
        sec = s.upper().split()[0]
        continue
    if sec == "*NODE" and s and not s.startswith("$"):
        f = [x.strip() for x in s.split(",")]
        try:
            k_nodes[int(f[0])] = (float(f[1]), float(f[2]), float(f[3]))
        except (ValueError, IndexError):
            pass
print(f"K nodes: {len(k_nodes)}, max gid: {max(k_nodes)}")

# ---------- 2. 布带(单层, PID2) 节点: 直接从 K 文件取 (★铁律, 见 P29) ----------
# ★ assemble_step1_2026.py 写 K 时对节点做了 gid 重编号 (sorted 重排 + cav 内层一拆二),
#   导出文件 step1_mesh_2026.txt 的 nid 与 K 的 gid 不是同一套 id (错位 6.7 万节点)!
#   若用导出文件的 nid+坐标当合并目标, 写进 K 后那个 gid 实际在十几毫米外 -> 全模型飞丝.
#   合并目标必须读【目标 K 文件本身】: *NODE 坐标 + PID2 单元节点集合, 两边同一坐标系同一 id.
# 参考模型(5P-BAG_004)实证: 拉带 PID8 只与单层布带 PID6 共节点(115), 与气腔 PID4 共节点 0
#   -> 合并目标限定为 PID2, 绝不能并到 cavity/seam 上.
belt_set = set()
sec = None
for l in k_lines_raw:
    s = l.strip()
    if s.startswith("*"):
        sec = s.upper().split()[0]
        continue
    if sec == "*ELEMENT_SHELL" and s and not s.startswith("$"):
        p = [x.strip() for x in s.split(",")]
        try:
            if int(p[1]) == 2:
                belt_set.update(int(x) for x in p[2:] if x.strip())
        except (ValueError, IndexError):
            pass
belt_n = {gid: (k_nodes[gid][0], k_nodes[gid][2])   # (x, z)
          for gid in belt_set if gid in k_nodes}
print(f"belt(PID2) nodes from K: {len(belt_n)}")

# 网格加速: 2mm 桶
GRID = 2.0
grid = collections.defaultdict(list)
for nid, (x, z) in belt_n.items():
    grid[(int(x // GRID), int(z // GRID))].append(nid)

def belt_candidates(x, z):
    out = []
    gx, gz = int(x // GRID), int(z // GRID)
    for dx in (-2, -1, 0, 1, 2):
        for dz in (-2, -1, 0, 1, 2):
            for nid in grid[(gx + dx, gz + dz)]:
                bx, bz = belt_n[nid]
                d = math.hypot(bx - x, bz - z)
                if d <= TOL:
                    out.append((d, nid))
    out.sort()
    return out

# ---------- 3. 读拉带网格 ----------
t_nodes = {}   # hm nid -> (x, y, z)
t_elems = collections.defaultdict(list)
for l in open(P + "/tabs_mesh_2026.txt", encoding="utf-8"):
    f = l.replace("{", " ").replace("}", " ").split()
    if not f:
        continue
    if f[0] == "N":
        t_nodes[int(f[1])] = (float(f[2]), float(f[3]), float(f[4]))
    elif f[0] == "T":
        t_elems[f[1]].append([int(x) for x in f[3:]])
print(f"tab nodes {len(t_nodes)}, elems {sum(len(v) for v in t_elems.values())}")

# 节点 -> 区域(tag) 映射, 用于连接报告
node_tag = {}
for tag, es in t_elems.items():
    for ns in es:
        for n in ns:
            node_tag[n] = tag

# ---------- 3.5 坐标完全相同的拉带节点合并 (共享弦边安全网) ----------
cmap = {}
reps = {}
for nid, (x, y, z) in t_nodes.items():
    key = (round(x, 4), round(y, 4), round(z, 4))
    if key in cmap:
        reps[nid] = cmap[key]
    else:
        cmap[key] = nid
if reps:
    for tag in t_elems:
        t_elems[tag] = [[reps.get(n, n) for n in ns] for ns in t_elems[tag]]
print(f"coincident tab nodes merged: {len(reps)}")

# ---------- 3.7 连接边选择 (用户 2026-10-21: 只连一条边, 不连整个重叠区) ----------
# 参考模型(5P-BAG_004)实证:
#   凸台(上片穹顶): 与布带在"布带 Z 水平的一条边"共节点(~16/片, 水平, 平行布带长度方向)
#   左区长拉带(CURVE/HORIZ): R8 与布带只在【拉带末端】共节点——带体 Y-0.5 延伸到 X~1074,
#     爬坡到 Y0, 末端竖边(X~1079, Z947-957)3 个节点共节点 -> 粘合线垂直布带长度方向
#     (用户 2026-10-21: "啮合点应该在拉带的顶端, 粘合线垂直于布带的长度方向")
# 本脚本:
#   凸台片(tab*_up/dn): 并【该片外周边】上靠近布带、且位于该片最高连接 Z 附近 8mm(顶帽边)的节点
#   左拉带(tabc*/tabh*): 并【该片外周边】上靠近布带、且位于该片最右端 3mm(末端竖边)的节点
perim = {}
for tag, es in t_elems.items():
    ec = collections.Counter()
    for ns in es:
        for k in range(len(ns)):
            ec[frozenset((ns[k], ns[(k + 1) % len(ns)]))] += 1
    perim[tag] = set(n for ed, c in ec.items() if c == 1 for n in ed)

near = {}                      # 靠近布带的节点
for nid, (x, y, z) in t_nodes.items():
    if belt_candidates(x, z):
        near[nid] = True

def is_left_strap(tag):
    """左区长拉带: CURVE(弧形)/HORIZ(长横) 区域, tag=tabc*/tabh*"""
    return tag.startswith("tabc") or tag.startswith("tabh")

EDGE_BAND = 8.0                # 凸台顶帽连接带: 该片最高连接 Z 附近 8mm
END_BAND = 3.0                 # 左拉带末端连接带: 该片最右端 3mm(末端竖边, 垂直布带长度)
conn_nodes = set()
for tag, es in t_elems.items():
    near_in = [n for ns in es for n in set(ns) if n in near]
    if not near_in:
        continue
    if is_left_strap(tag):
        # 末端竖边: 靠近布带的自由边节点中位于最右端 END_BAND 内的
        # (该边沿 Z 向展开 = 垂直于布带 X 向长度方向)
        xend = max(t_nodes[n][0] for n in near_in)
        for n in near_in:
            if n in perim[tag] and t_nodes[n][0] >= xend - END_BAND:
                conn_nodes.add(n)
    else:
        ztop = max(t_nodes[n][2] for n in near_in)
        for n in near_in:
            if n in perim[tag] and t_nodes[n][2] >= ztop - EDGE_BAND:
                conn_nodes.add(n)
n_strap = sum(1 for n in conn_nodes if is_left_strap(node_tag[n]))
print(f"连接边节点: {len(conn_nodes)} (左拉带末端边 {n_strap} / 凸台顶帽边 {len(conn_nodes)-n_strap})")

# ---------- 4. 捏合 (仅连接边节点, 1-to-1 贪心合并到布带) ----------
cand = {}
for nid in conn_nodes:
    x, y, z = t_nodes[nid]
    cand[nid] = belt_candidates(x, z)
gid_map = {nid: None for nid in t_nodes}

# 全局 1-to-1 贪心匹配: 距离升序, 每个布带节点至多被一个拉带节点复用
# => 任意单元内不可能出现两个拉带节点映射到同一布带节点 -> 不丢单元(无退化)
# 少数密集处: 较远的拉带节点落空 -> 保留为独立节点(取新 gid), 仍满足"不删单元"
triples = []
for nid, c in cand.items():
    for d, bid in c:
        triples.append((d, nid, bid))
triples.sort()                       # 距离升序, 近者优先占位
used_tab, used_belt = set(), set()
for d, nid, bid in triples:
    if nid in used_tab or bid in used_belt:
        continue
    gid_map[nid] = bid
    used_tab.add(nid)
    used_belt.add(bid)
n_snap = sum(1 for v in gid_map.values() if v is not None)
print(f"1-to-1 merges: {n_snap}/{len(t_nodes)}")

# ---------- 5. gid 分配 ----------
gid_map2 = {}
next_gid = max(k_nodes) + 1
new_nodes = []
for nid, (x, y, z) in sorted(t_nodes.items()):
    b = gid_map.get(nid)
    if b is not None:
        gid_map2[nid] = b          # 复用布带节点 (Y0)
    else:
        gid_map2[nid] = next_gid
        new_nodes.append((next_gid, x, Y_TAB, z))
        next_gid += 1
n_merged = len(t_nodes) - len(new_nodes)
print(f"merged to belt: {n_merged}/{len(t_nodes)}, new nodes {len(new_nodes)} (Y={Y_TAB})")

# ---------- 5.5 既有单元节点集(剔除与布带/气腔/缝线重合的零厚度单元) ----------
# 拉带在重叠区节点全并到布带后, 个别拉带单元 4 节点全部落在布带上,
# 与布带单元完全重合(零厚度伪单元). 参考模型(5P-BAG_004)拉带靠"共节点"连接,
# 不存在重合单元 -> 这里把节点集与既有单元相同的拉带单元剔除(非乱删, 是真重合伪单元)
existing_sets = set()
sec = None
for l in k_lines_raw:
    s = l.strip()
    if s.startswith("*"):
        sec = s.upper().split()[0]
        continue
    if sec == "*ELEMENT_SHELL" and s and not s.startswith("$"):
        f = [x.strip() for x in s.split(",")]
        try:
            ns = tuple(int(x) for x in f[2:] if x.strip())
            if len(ns) >= 3:
                existing_sets.add(tuple(sorted(ns)))   # 用节点集(无序)比对
        except (ValueError, IndexError):
            pass
print(f"existing shell element sets: {len(existing_sets)}")
# 注: belt_set 已在第 2 节从 K 文件解析(与合并目标同源), 此处直接复用

# ---------- 6. 单元映射 ----------
kelems = []
ndrop_degen = 0
ndrop_dup = 0
seen = set()
for tag, es in t_elems.items():
    for ns in es:
        u = tuple(dict.fromkeys(gid_map2[n] for n in ns))
        if len(u) < 3:
            ndrop_degen += 1
            continue
        key = tuple(sorted(u))                  # 节点集(无序)比对, 与 QA 口径一致
        if key in existing_sets or key in seen:   # 与既有单元/自身重合 -> 剔除伪单元
            ndrop_dup += 1
            continue
        seen.add(key)
        kelems.append((5, list(u)))
print(f"PID5 elems: {len(kelems)} (degenerate dropped {ndrop_degen}, coincident dup dropped {ndrop_dup})")

# ---------- 6.5 连接报告(按区域): 拉带节点共节点到布带(PID2)的情况 ----------
region = collections.defaultdict(lambda: [0, 0, 0])   # tag -> [共节点数, 连接单元数, 总单元数]
for tag, es in t_elems.items():
    for ns in es:
        mapped = [gid_map2[n] for n in ns]
        conn = sum(1 for g in mapped if g in belt_set)
        region[tag][2] += 1
        if conn > 0:
            region[tag][1] += 1
        for n in ns:
            if gid_map2[n] in belt_set:
                region[tag][0] += 1
print("=== 拉带-布带连接(按区域) ===")
for tag in sorted(region):
    cn, ce, te = region[tag]
    print(f"  {tag:10s}: 共节点 {cn:4d}, 连接单元 {ce:4d}/{te:4d}")
tot_cn = sum(v[0] for v in region.values())
tot_ce = sum(v[1] for v in region.values())
print(f"  合计: 共节点 {tot_cn}, 连接单元 {tot_ce}/{sum(v[2] for v in region.values())}")

# ---------- 7. 合并进 K ----------
eid0 = 80464
lines_out = []
sec = None
inserted_nodes = False
inserted_elems = False
eid = eid0
for l in k_lines_raw:
    s = l.strip()
    if s.startswith("*"):
        sec = s.upper().split()[0]
        if sec == "*ELEMENT_SHELL" and not inserted_nodes:
            lines_out.append("$ ==== TAB PID5 new nodes (Y=-1, overlap merged to belt) ====")
            for gid, x, y, z in new_nodes:
                lines_out.append(f"{gid}, {x:.6f}, {y:.6f}, {z:.6f}")
            inserted_nodes = True
        if sec == "*PART" and not inserted_elems:
            lines_out.append("$ ==== TAB PID5 elements (eid continues from 80464) ====")
            lines_out.append("$#   eid     pid      n1      n2      n3      n4")
            for pid, ns in kelems:
                eid += 1
                row = f"{eid}, {pid}, {ns[0]}, {ns[1]}, {ns[2]}"
                if len(ns) == 4:
                    row += f", {ns[3]}"
                lines_out.append(row)
            inserted_elems = True
    lines_out.append(l)
final = []
part_done = False
for l in lines_out:
    if l.strip() == "*PART" and not part_done:
        final.append("*PART")
        final.append("tab        2mm shell")
        final.append("$#  pid     secid    mid")
        final.append("         5         1         1")
        part_done = True
    final.append(l)
open(KPATH, "w", encoding="utf-8", newline="\n").write("\n".join(final))
print(f"K updated: nodes +{len(new_nodes)}, elems +{len(kelems)} (eid {eid0+1}~{eid}), PART5 {'OK' if part_done else 'MISS'}")
