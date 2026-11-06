"""2026 第一步组装: mesh txt → Y 分层 → LS-DYNA K (自由格式) + QA
分层约定 (用户规范):
  belt (PID2)  : Y0 单层
  cav  (PID3)  : Y-0.5 / Y+0.5 双层; 与 belt / seam 界面的边界节点收 Y0
  seam (PID4)  : Y0 单层
界面共节点 (裁切拓扑天然共享): cav 上下层共用边界节点 gid
"""
import collections, math, pathlib, os

P = pathlib.Path(os.environ.get("WORKDIR", r".")) / "out"
Y_CAV = 0.5

nodes = {}
elems = collections.defaultdict(list)   # tag -> list[[n...]]
for line in open(P / "step1_mesh_2026.txt", encoding="utf-8"):
    f = line.replace("{", " ").replace("}", " ").split()
    if not f:
        continue
    if f[0] == "N":
        nodes[int(f[1])] = (float(f[2]), float(f[3]), float(f[4]))
    elif f[0] == "S":
        elems[f[1]].append([int(x) for x in f[3:]])

# --- 界面节点: cav 边界(被 cav 与其他组共享的节点) ---
def nodes_of(tag):
    s = set()
    for ns in elems[tag]:
        s.update(ns)
    return s

cav_n = nodes_of("cav")
other_n = nodes_of("belt") | nodes_of("seam0") | nodes_of("seam1") | nodes_of("seam2") | nodes_of("seam3") | nodes_of("seam4")
cav_bnd = cav_n & other_n
print(f"cav 边界节点(收Y0): {len(cav_bnd)}  / cav 全部 {len(cav_n)}")

# --- K 文件节点: gid 重编号, cav 内部节点拆上下层, 边界节点单份 Y0 ---
gid_of = {}
knodes = []          # (gid, x, y, z)
next_gid = 1
for nid in sorted(nodes):
    gid_of[nid] = next_gid
    x, y, z = nodes[nid]
    knodes.append((next_gid, x, y, z))
    next_gid += 1
# cav 内部节点 → 上下层两份
cav_inner = sorted(cav_n - cav_bnd)
for nid in cav_inner:
    x, y, z = nodes[nid]
    knodes.append((next_gid, x, y - Y_CAV, z)); gid_of[("cavlo", nid)] = next_gid; next_gid += 1
    knodes.append((next_gid, x, y + Y_CAV, z)); gid_of[("cavhi", nid)] = next_gid; next_gid += 1
print(f"节点总数: 基础 {len(nodes)} + cav双层 {2*len(cav_inner)} = {len(knodes)}")

def g_of(nid, layer=None):
    if layer == "cavlo" and nid in cav_inner: return gid_of[("cavlo", nid)]
    if layer == "cavhi" and nid in cav_inner: return gid_of[("cavhi", nid)]
    return gid_of[nid]

# --- 单元 ---
kelems = []          # (pid, [gid...])
pid_map = {"belt": 2, "cav": 3, "seam0": 4, "seam1": 4, "seam2": 4, "seam3": 4, "seam4": 4}
nseen = set()
for tag in ["belt", "seam0", "seam1", "seam2", "seam3", "seam4", "cav"]:
    pid = pid_map[tag]
    for ns in elems[tag]:
        u = list(dict.fromkeys(ns))
        if len(u) < 3:
            continue
        if pid == 3:  # cav 双层 (退化三角也要双层)
            lo = [g_of(n, "cavlo") for n in u]
            hi = [g_of(n, "cavhi") for n in u]
            # 全边界元素(所有节点都在界面上)只写一份, 避免重复
            if all(n in cav_bnd for n in u):
                kelems.append((pid, lo))
            else:
                kelems.append((pid, lo))
                kelems.append((pid, hi))
        else:
            kelems.append((pid, [g_of(n) for n in u]))
print(f"单元总数: {len(kelems)}")

# --- 写 K (自由格式) ---
import os as _os
DECK = _os.environ.get("DECK", "airbag_step1_2026.k")
kpath = P / DECK
with open(kpath, "w", encoding="utf-8", newline="\n") as f:
    f.write("$ LS-DYNA keyword deck - airbag curtain step1 (2026 pipeline)\n")
    f.write("$ belt PID2 Y0 / cav PID3 Y+/-0.5 (bnd Y0) / seam PID4 Y0\n")
    f.write("*KEYWORD\n*TITLE\n airbag curtain step1 three-ring mesh (HM2026 trim topology)\n")
    f.write("*NODE\n")
    f.write("$#   nid               x               y               z\n")
    for gid, x, y, z in knodes:
        f.write(f"{gid}, {x:.6f}, {y:.6f}, {z:.6f}\n")
    # 铁律: *ELEMENT_SHELL 字段顺序 = eid, pid, n1, n2, n3[, n4]
    # 漏写 eid 会让 pid 被读成 eid -> 全表 ID 重复 + 幽灵 part -> 读取器卡死
    f.write("*ELEMENT_SHELL\n")
    f.write("$#   eid     pid      n1      n2      n3      n4\n")
    eid = 1
    for pid, ns in kelems:
        assert len(ns) in (3, 4), f"bad elem node count {len(ns)}"
        row = f"{eid}, {pid}, {ns[0]}, {ns[1]}, {ns[2]}"
        if len(ns) == 4:
            row += f", {ns[3]}"
        f.write(row + "\n")
        eid += 1
    f.write("*PART\nbelt      2mm shell\n$#  pid     secid    mid\n         2         1         1\n")
    f.write("*PART\ncav       2mm shell\n$#  pid     secid    mid\n         3         1         1\n")
    f.write("*PART\nseam      2mm shell\n$#  pid     secid    mid\n         4         1         1\n")
    f.write("*SECTION_SHELL\n$#  secid   elform     shrf      nip\n         1         2       1.0      2.0\n")
    f.write("*MAT_ELASTIC\n$#   mid      ro         e     pr\n         1  1.00E-09  210000.0      0.3\n")
    f.write("*END\n")
print(f"单元 ID 范围: 1 ~ {eid-1} (唯一递增)")

# pre_tabs 干净基底副本（拉带组装前快照，run_pipeline 幂等重跑机制）
import shutil as _sh
_pre = P / (kpath.stem + "_pre_tabs.k")
_sh.copyfile(kpath, _pre)
print(f"pre_tabs 基底副本: {_pre.name}")

# --- QA ---
print("\n=== QA ===")
kp = {g: (x, y, z) for g, x, y, z in knodes}
# 边计数 (按 pid)
for pid in (2, 3, 4):
    es = [ns for p, ns in kelems if p == pid]
    ec = collections.Counter()
    nds = set()
    for ns in es:
        u = list(dict.fromkeys(ns))
        nds.update(u)
        for i in range(len(u)):
            a, b = u[i], u[(i + 1) % len(u)]
            ec[(min(a, b), max(a, b))] += 1
    bnd_edges = sum(1 for c in ec.values() if c == 1)
    area = 0.0
    for ns in es:
        u = list(dict.fromkeys(ns))
        if len(u) >= 3:
            for i in range(1, len(u) - 1):
                a, b, c = kp[u[0]], kp[u[i]], kp[u[i + 1]]
                area += abs((b[0]-a[0])*(c[2]-a[2]) - (c[0]-a[0])*(b[2]-a[2])) / 2
    ys = collections.Counter(round(kp[g][1], 3) for g in nds)
    print(f"PID{pid}: elems={len(es)} nodes={len(nds)} 单层面积={area/ (2 if pid==3 else 1):.0f} "
          f"边界边={bnd_edges} Y分布={dict(sorted(ys.items()))}")
# cav 上下层共节点检查: 边界节点单份 → 两层共享
bndg = {gid_of[n] for n in cav_bnd}
print(f"cav 上下层共享边界 gid 数: {len(bndg)}")
# 重复单元
seen = set(); ndup = 0
for pid, ns in kelems:
    k = (pid, tuple(sorted(ns)))
    if k in seen:
        ndup += 1
    seen.add(k)
print(f"重复单元: {ndup}")
print(f"K 文件: {kpath}  ({kpath.stat().st_size/1e6:.2f} MB)")
