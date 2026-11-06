# -*- coding: utf-8 -*-
"""cab2 组装: step1(布带/气腔/缝线) + step2(拉带) -> Z 分层 -> LS-DYNA K
分层 (用户规范, 厚度轴 = Z; cab2 几何本身在 X-Y 平面 Z=0, 无需坐标变换):
  belt PID2 : Z0 单层
  cav  PID3 : Z+0.5 / Z-0.5 双层; 与 belt/seam 界面的边界节点收 Z0 (捏合)
  seam PID4 : Z0 单层
  tether PID5: Z-1; 与布带【外边界】节点 1-to-1 贪心捏合(共节点, 取 Z0)
输出: E:/work/AI_CAB/onekey/cab2_curtain_airbag.k
"""
import collections, math, os, sys

P = (os.environ.get("WORKDIR") or "E:/work/AI_CAB/onekey/work/cab2_skill").rstrip("/") + "/"
OUTDIR = os.environ.get("OUTDIR") or "E:/work/AI_CAB/onekey"
DECK = os.environ.get("DECK") or (OUTDIR + "/cab2_curtain_airbag.k")
Z_CAV = float(os.environ.get("Z_CAV") or 0.5)
Z_TAB = float(os.environ.get("Z_TAB") or -1.0)
TOL = float(os.environ.get("TAB_TOL") or 3.0)
EDGE_BAND = float(os.environ.get("EDGE_BAND") or 4.0)
TAB_OFFSET = 10_000_000


def load(path, nid_offset=0):
    nodes, els = {}, collections.defaultdict(list)
    for line in open(path, encoding="utf-8"):
        f = line.replace("{", " ").replace("}", " ").split()
        if not f:
            continue
        if f[0] == "N":
            nodes[int(f[1]) + nid_offset] = (float(f[2]), float(f[3]), float(f[4]))
        elif f[0] == "S":
            els[f[1]].append([int(x) + nid_offset for x in f[3:]])
    return nodes, els


import os
_S1 = os.environ.get("STEP1") or ""
if _S1 and not os.path.isabs(_S1):
    # STEP1 可能给 "cab2_step1_bl.txt"（相对 out/）或 "out/xxx.txt"（相对 WORKDIR）
    for _cand in (_S1, os.path.join(P, _S1), os.path.join(P, "out", os.path.basename(_S1))):
        if os.path.exists(_cand):
            _S1 = _cand
            break
    else:
        _S1 = os.path.join(P, "out", os.path.basename(_S1))
if not _S1:
    _cands = []
    _case = os.environ.get("CASE")
    if _case:
        _cands.append(f"{_case}_step1_bl.txt")
    _cands += ["cab2_step1_bl.txt", "cab2_step1_washer.txt", "cab2_step1_mesh.txt"]
    for _c in _cands:
        if os.path.exists(P + "out/" + _c):
            _S1 = P + "out/" + _c
            break
print("step1 源:", os.path.basename(_S1))
n1, e1 = load(_S1)

# ---------- blmesh 路径专用: 气腔边界节点按坐标并入布带/缝线 ----------
# blmesh 与相邻面 automesh 是两次独立生成 -> 交线上节点位置相同但 ID 两套。
# 不合并则 cav∩belt=0, 下游 cav_bnd(Z0 收口判据) 失效 -> 气腔上下层各自开口,
# 且界面处出现"悬挂节点"式不连续。命令层 *equivalence* 在 hmbatch 下无效,
# 因此在这一层按坐标哈希合并。
MERGE_TOL = float(os.environ.get("MERGE_TOL") or 0.0)
if MERGE_TOL > 0 and "cav" in e1:
    host_tags = ["belt"] + [t for t in e1 if t.startswith("seam")]
    host_n = set()
    for t in host_tags:
        for ns in e1[t]:
            host_n.update(ns)
    Q = 1.0 / MERGE_TOL
    grid = collections.defaultdict(list)
    for nid in host_n:
        x, y, _ = n1[nid]
        grid[(int(x * Q), int(y * Q))].append(nid)
    cav_n_raw = set()
    for ns in e1["cav"]:
        cav_n_raw.update(ns)
    remap = {}
    for nid in cav_n_raw:
        if nid in host_n:
            continue
        x, y, _ = n1[nid]
        gx, gy = int(x * Q), int(y * Q)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for h in grid.get((gx + dx, gy + dy), ()):
                    hx, hy, _ = n1[h]
                    d = math.hypot(hx - x, hy - y)
                    if d <= MERGE_TOL and (best is None or d < best[0]):
                        best = (d, h)
        if best:
            remap[nid] = best[1]
    e1["cav"] = [[remap.get(n, n) for n in ns] for ns in e1["cav"]]
    for nid in remap:
        n1.pop(nid, None)
    still = {n for ns in e1["cav"] for n in ns} - host_n
    print(f"气腔↔布带/缝线 坐标合并 tol={MERGE_TOL}: 合并 {len(remap)} 个节点"
          f"  (气腔边界原始 {len(cav_n_raw)})")
    # 边界对齐诊断: 气腔剩余节点里, 距最近布带/缝线节点 <3mm 的 = 本该重合却没合上
    near_but_not = 0
    for nid in still:
        x, y, _ = n1[nid]
        gx, gy = int(x * Q), int(y * Q)
        dmin = None
        r = max(2, int(3.0 / MERGE_TOL))
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for h in grid.get((gx + dx, gy + dy), ()):
                    d = math.hypot(n1[h][0] - x, n1[h][1] - y)
                    if dmin is None or d < dmin:
                        dmin = d
        if dmin is not None and dmin <= 3.0:
            near_but_not += 1
    print(f"   边界对齐: 气腔剩 {len(still)} 节点, 其中距界面 <3mm 未合并 = {near_but_not}"
          f"  ({100.0*near_but_not/max(1,len(still)):.2f}%)")
# ---- 拉带网格输入（案例无关命名 + 缺件必须响）----
# cab2 事故：out/ 被清空后 step2b 侧条文件不存在，只打一行 WARN 就继续，
# 结果整块侧拉带（2354mm²）静默丢失，五项门禁全 PASS。见 references/04 P49。
CASE = os.environ.get("CASE") or "cab2"
REQUIRE = set((os.environ.get("REQUIRE_PARTS") or "").lower().replace(",", " ").split())


def _find(spec, *alts):
    """spec 绝对路径直接用；否则依次在 out/ 下按 spec、alts 的 basename 找。"""
    for c in (spec,) + alts:
        if not c:
            continue
        p = c if os.path.isabs(c) else os.path.join(P, "out", os.path.basename(c))
        if os.path.exists(p):
            return p
    return None


_S2spec = os.environ.get("STEP2") or f"{CASE}_step2_tether.txt"
_S2 = _find(_S2spec)
if _S2 is None:
    raise SystemExit(
        f"缺主拉带网格 out/{os.path.basename(_S2spec)}\n"
        f"  → 用 STEP2= 指定；或先跑 ⑤ 拉带阶段。\n"
        f"  → 该案例确实没有拉带时才设 SKIP_TETHER=1。")
n2, e2 = load(_S2, TAB_OFFSET)
print(f"   主拉带: {_S2}")

_S3spec = os.environ.get("STEP2B") or f"{CASE}_step2b_side.txt"
_S3 = _find(_S3spec, f"{CASE}_step2b_side2.txt")
n3, e3 = ({}, collections.defaultdict(list))
if _S3 is not None:
    n3, e3 = load(_S3, TAB_OFFSET + 20_000_000)
    print(f"   侧面拉带: {_S3}")
elif "side" in REQUIRE:
    raise SystemExit(
        f"缺侧面拉带网格 out/{os.path.basename(_S3spec)}，但 case.json 的 parts 声明需要 side。\n"
        f"  → 先跑 stage2_partition/tether_side_outline.py + gen_side_tab_full_outline.py，\n"
        f"    再把 STEP2B=<导出的 txt> 传给本脚本。整块丢不会让任何其它门禁报警（P49）。")
else:
    print("WARN 缺侧面拉带网格, 本次不含"
          "（若案例存在侧条，这就是整块丢 —— 请设 STEP2B= 重跑）")
nodes = dict(n1); nodes.update(n2); nodes.update(n3)
elems = collections.defaultdict(list)
for k, v in e1.items():
    elems[k] += v
for k, v in e2.items():
    elems[k] += v
for k, v in e3.items():
    elems["tether" if k == "side" else k] += v
print(f"读入: step1 nodes={len(n1)}  step2 nodes={len(n2)}  step2b nodes={len(n3)}  合计 {len(nodes)}")
for t in sorted(elems):
    print(f"   [{t}] {len(elems[t])} 单元")


def nodes_of(*tags):
    s = set()
    for t in tags:
        for ns in elems.get(t, []):
            s.update(ns)
    return s


CAV_TAGS = ["cav"] + (["cav_washer"] if "cav_washer" in elems else [])
belt_n = nodes_of("belt")
cav_n = nodes_of(*CAV_TAGS)
seam_tags = [t for t in elems if t.startswith("seam")]
seam_n = nodes_of(*seam_tags)
tab_n = nodes_of("tether")


# ---------- 自由边节点 ----------
def free_edge_nodes(tag):
    tags = tag if isinstance(tag, (list, tuple)) else [tag]
    ec = collections.Counter()
    for ns in [x for t in tags for x in elems[t]]:
        u = list(dict.fromkeys(ns))
        for i in range(len(u)):
            a, b = u[i], u[(i + 1) % len(u)]
            ec[(min(a, b), max(a, b))] += 1
    return {n for (a, b), c in ec.items() if c == 1 for n in (a, b)}


# 气腔边界 = 与布带/缝线共节点的界面 + 自身自由边(颈部收口段, CAD 上 L2 环有一段 86mm 断口,
# 由 L1 沿 196 补齐, 该段不与布带共节点 -> 必须自行捏合, 否则上下两层各自开口会漏气)
cav_free = free_edge_nodes(CAV_TAGS)
cav_bnd = (cav_n & (belt_n | seam_n)) | cav_free
cav_inner = cav_n - cav_bnd
print(f"cav 边界(收 Z0)={len(cav_bnd)} (界面 {len(cav_n & (belt_n | seam_n))} + 自由边 {len(cav_free)})"
      f"  内部(拆上下层)={len(cav_inner)}")

# ---------- 布带外边界节点 (L1 边) = 自由边节点且不与 cav 共享 ----------
belt_free = free_edge_nodes("belt")
belt_outer = belt_free - cav_n
print(f"belt 自由边节点={len(belt_free)}  其中外边界(L1)={len(belt_outer)}  内边界(与cav共享)={len(belt_free)-len(belt_outer)}")

# ---------- 拉带连接: 只连布带外边界, 1-to-1 贪心 ----------
tab_perim = free_edge_nodes("tether")
GRID = 2.0
grid = collections.defaultdict(list)
for nid in belt_outer:
    x, y, _ = nodes[nid]
    grid[(int(x // GRID), int(y // GRID))].append(nid)


def cand(x, y):
    out = []
    gx, gy = int(x // GRID), int(y // GRID)
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            for nid in grid.get((gx + dx, gy + dy), []):
                bx, by, _ = nodes[nid]
                d = math.hypot(bx - x, by - y)
                if d <= TOL:
                    out.append((d, nid))
    out.sort()
    return out


# 每块拉带只取"最靠近布带的一圈" (自由边节点中, 位于最大连接 y 的 EDGE_BAND 带内)
# 先按连通块分组(靠 id 连续性不可靠) -> 用单元连通分量
comp = {}
cid = 0
adj = collections.defaultdict(set)
tab_elems = elems["tether"]
for i, ns in enumerate(tab_elems):
    for n in ns:
        adj[n].add(i)
seen_n = set()
tab_groups = []
for n in tab_n:
    if n in seen_n:
        continue
    stack = [n]; grp = set()
    while stack:
        q = stack.pop()
        if q in grp:
            continue
        grp.add(q)
        for ei in adj[q]:
            for m in tab_elems[ei]:
                if m not in grp:
                    stack.append(m)
    seen_n |= grp
    tab_groups.append(grp)
print(f"拉带连通块: {len(tab_groups)} 块")

conn_nodes = set()
grp_anchor = {}
for gi, grp in enumerate(tab_groups):
    # 连接带 = 凸台"整片节点"(不只边界)中靠近布带自由边(L1)者;
    # 上一版只取边界节点 -> 颈部与布带顶边相交处边界上仅 2 个点 -> 只有 24 个共节点。
    # 完整凸台的颈部(Y 367~418)整段压在布带上, 其内部一排节点才够"一层网格节点"。
    near = [n for n in grp if cand(*nodes[n][:2])]
    grp_anchor[gi] = len(near)
    if not near:
        print("   WARN 某块拉带无近邻布带节点")
        continue
    conn_nodes |= set(near)
print(f"拉带连接边节点(外边界近邻): {len(conn_nodes)}  按块: {sorted(grp_anchor.values())}")

# ---------- 补充: 落在布带足迹"内部"的拉带边界节点 = 根部锚固排 ----------
# 侧面拉带的 CAD 轮廓从 X=1572.4 起, 它在布带内部叠压 47.8mm。
# 参考模型 5P-BAG_004 同构做法: 拉带根部有一排 Y=0 节点与布带【内部】节点共用(缝线),
# 其余下落到拉带自己的平面。旧版只按"布带外自由边近邻"找连接点, 找不到内部锚固排,
# 于是侧面拉带的缝接位置退到了布带端面 X=1620.2 —— 位置就错了。
SNAP_IN = float(os.environ.get("SNAP_INSIDE_TOL") or 3.0)
inner_pick = []
if SNAP_IN > 0 and "tether" in elems:
    # 布带足迹栅格 (2mm)
    FP = 2.0
    fp = set()
    for nid in belt_n:
        x, y, _ = nodes[nid]
        fp.add((int(x // FP), int(y // FP)))
    def in_belt(x, y):
        gx, gy = int(x // FP), int(y // FP)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (gx + dx, gy + dy) in fp:
                    return True
        return False
    bgrid = collections.defaultdict(list)
    for nid in belt_n:
        # 排除布带-气腔界面节点: 它们已与气腔共节点, 拉带再挂上去会变成 tether∩cav > 0,
        # 参考模型明确要求 tether∩cav = 0 (拉带只连布带)。
        if nid in cav_n:
            continue
        x, y, _ = nodes[nid]
        bgrid[(int(x // FP), int(y // FP))].append(nid)
    def cand_inner(x, y):
        gx, gy = int(x // FP), int(y // FP)
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for nid in bgrid.get((gx + dx, gy + dy), ()):
                    d = math.hypot(nodes[nid][0] - x, nodes[nid][1] - y)
                    if d <= SNAP_IN:
                        out.append((d, nid))
        out.sort()
        return out
    inner_pick = []
    # 只对"外边界近邻那一轮没取到足够锚点"的块启用内部锚固。
    # 判据: 该块锚点数 < WEAK_MIN(=8, 约一排)。凸台交叉布带时 pass A 已给出整排(≈10),
    # 不该再被内部锚固二次焊接 -> 否则推挤节点最多 3mm, 把拉带单元压歪。
    WEAK_MIN = int(os.environ.get("WEAK_ANCHOR_MIN") or 8)
    weak = {gi for gi, c in grp_anchor.items() if c < WEAK_MIN}
    for gi in sorted(weak):
        for nid in sorted(tab_groups[gi] & tab_perim):
            if nid in conn_nodes:
                continue
            x, y, _ = nodes[nid]
            if not in_belt(x, y):
                continue
            c = cand_inner(x, y)
            if c:
                inner_pick.append((nid, c))
    if inner_pick:
        print(f"弱锚块 {len(weak)} 个 -> 布带内部锚固排候选 {len(inner_pick)} 个节点 (tol={SNAP_IN}mm)")

triples = []
for n in conn_nodes:
    for d, b in cand(*nodes[n][:2]):
        triples.append((d, n, b))
if SNAP_IN > 0 and "tether" in elems:
    for n, c in inner_pick:
        for d, b in c:
            triples.append((d, n, b))
triples.sort()
used_t, used_b = set(), set()
snap = {}
for d, n, b in triples:
    if n in used_t or b in used_b:
        continue
    snap[n] = b
    used_t.add(n); used_b.add(b)
_n_out = sum(1 for n in snap if cand(*nodes[n][:2]))
print(f"1-to-1 捏合: {len(snap)} 个  (外边界近邻 {_n_out} + 布带内部锚固排 {len(snap)-_n_out})"
      f"  最大位移 {max([d for d, n, b in triples if n in snap] or [0]):.2f}mm")

# ---------- gid 分配 ----------
# 顺序: ① 平面主体节点(除拉带未捏合者) 收 Z0  ② cav 内部节点拆 Z±0.5  ③ 拉带独立节点 Z-1
gid = {}
knodes = []
ng = 1
for nid in sorted(nodes):
    if nid in tab_n and nid not in snap:
        continue                       # 拉带独立节点留到 ③
    if nid in snap:
        continue                       # 捏合节点复用布带 gid
    if nid in cav_inner:
        continue                       # 气腔内部节点只以 hi/lo 两层存在, 不留 Z0 悬空节点
    gid[nid] = ng
    x, y, _ = nodes[nid]
    knodes.append((ng, x, y, 0.0))
    ng += 1
for nid in snap:                       # 拉带捏合节点 = 布带节点 gid (Z0)
    gid[nid] = gid[snap[nid]]
cav_lo, cav_hi = {}, {}
for nid in sorted(cav_inner):
    x, y, _ = nodes[nid]
    knodes.append((ng, x, y, Z_CAV)); cav_hi[nid] = ng; ng += 1
    knodes.append((ng, x, y, -Z_CAV)); cav_lo[nid] = ng; ng += 1
tab_new = 0
for nid in sorted(tab_n):
    if nid in snap:
        continue
    x, y, _ = nodes[nid]
    gid[nid] = ng
    knodes.append((ng, x, y, Z_TAB))
    ng += 1
    tab_new += 1
print(f"K 节点: 主体+层 {ng-1-tab_new} + 拉带独立 {tab_new} = {len(knodes)}  (拉带捏合复用 {len(snap)})")


def g_of(nid, layer=None):
    if layer == "hi" and nid in cav_hi:
        return cav_hi[nid]
    if layer == "lo" and nid in cav_lo:
        return cav_lo[nid]
    return gid[nid]


# ---------- 单元 ----------
kp_pre = {g: (x, y, z) for g, x, y, z in knodes}


def plan_area(ns):
    a = 0.0
    for i in range(len(ns)):
        j = (i + 1) % len(ns)
        p, q = kp_pre[ns[i]], kp_pre[ns[j]]
        a += p[0] * q[1] - q[0] * p[1]
    return a / 2


pid_map = {"belt": 2, "cav": 3, "tether": 5, "cav_washer": 3}
for t in seam_tags:
    pid_map[t] = 4
kelems = []
ndeg = ndup = 0
seen = set()
for tag in ["belt"] + seam_tags + CAV_TAGS + ["tether"]:
    pid = pid_map[tag]
    for ns in elems[tag]:
        u = list(dict.fromkeys(ns))
        if len(u) < 3:
            ndeg += 1
            continue
        if pid == 3:
            lo = [g_of(n, "lo") for n in u]
            hi = [g_of(n, "hi") for n in u]
            if all(n in cav_bnd for n in u):
                rows = [lo]
            else:
                rows = [hi, lo[::-1]]
        else:
            r0 = [g_of(n) for n in u]
            if plan_area(r0) < 0:     # 绕向统一(平面单层面法向一致)
                r0 = r0[::-1]
            rows = [r0]
        for r in rows:
            key = (pid, tuple(sorted(r)))
            if key in seen:
                ndup += 1
                continue
            seen.add(key)
            kelems.append((pid, r))
print(f"单元: {len(kelems)} (退化剔除 {ndeg}, 重复剔除 {ndup})")

# ---------- 写 K ----------
os.makedirs(os.path.dirname(DECK), exist_ok=True)
cnt = collections.Counter(p for p, _ in kelems)
# 强制 ASCII 写盘: LS-DYNA / HyperMesh 读 K 文件时非 ASCII 字节会致异常,
# 用 ascii 编码写 -> 一旦注释里混入中文立刻抛错, 而不是交付后才发现。
with open(DECK, "w", encoding="ascii", newline="\n") as f:
    f.write("$ =====================================================================\n")
    f.write("$ cab2 curtain airbag mesh  (HyperMesh 2026 trim-topology pipeline)\n")
    f.write("$   PID2 = belt   (Z0 single layer)\n")
    f.write("$   PID3 = cavity (Z+0.5 / Z-0.5 double layer, boundary pinched to Z0)\n")
    f.write("$   PID4 = seam   (Z0 single layer, 4 panels)\n")
    f.write("$   PID5 = tether (Z-1, merged 1:1 to belt outer-edge nodes at Z0)\n")
    f.write("$ geometry: cab2.hm (X-Y plane, thickness along Z; no coordinate transform)\n")
    f.write("$ NOTE: MAT is a PLACEHOLDER. Replace with your MAT_FABRIC/*AIRBAG set\n")
    f.write("$       (reference model uses MAT_FABRIC mid 84450005, t=0.3mm).\n")
    f.write("$ =====================================================================\n")
    f.write("*KEYWORD\n*TITLE\n cab2 curtain airbag mesh\n")
    f.write("*NODE\n$#   nid               x               y               z\n")
    for g, x, y, z in knodes:
        f.write(f"{g}, {x:.6f}, {y:.6f}, {z:.6f}\n")
    f.write("*ELEMENT_SHELL\n$#   eid     pid      n1      n2      n3      n4\n")
    eid = 1
    for pid, ns in kelems:
        row = f"{eid}, {pid}, {ns[0]}, {ns[1]}, {ns[2]}"
        if len(ns) == 4:
            row += f", {ns[3]}"
        f.write(row + "\n")
        eid += 1
    parts = [(2, "belt"), (3, "cavity"), (4, "seam"), (5, "tether")]
    for pid, nm in parts:
        f.write(f"*PART\n{nm}\n$#     pid     secid       mid\n{pid:10d}{1:10d}{1:10d}\n")
    f.write("*SECTION_SHELL\n$#   secid   elform      shrf       nip     propt       qr     icomp\n")
    f.write(f"{1:10d}{9:10d}{0.83333:10.5f}{1.0:10.1f}{1.0:10.1f}{0.0:10.1f}{1:10d}\n")
    f.write("$#      t1        t2        t3        t4       nloc     marea      idof\n")
    f.write(f"{0.3:10.3f}{0.3:10.3f}{0.3:10.3f}{0.3:10.3f}{0.0:10.1f}{0.0:10.1f}\n")
    f.write("$ ---------------------------------------------------------------------\n")
    f.write("$ MAT_FABRIC core params taken from reference model 5P-BAG_004 (MAT.K mid 84450005)\n")
    f.write("$   ro = 1.1E-6 kg/mm^3 (1100 kg/m^3), EA = EB = 0.18 N/mm (warp / weft)\n")
    f.write("$   Curve / failure cards (original referenced LCID -19/-20) are zeroed here to\n")
    f.write("$   avoid dangling curve references. Fill in failure strain / strain-rate /\n")
    f.write("$   permeability per project spec before production use.\n")
    f.write("*MAT_FABRIC\n")
    f.write("$#     mid        ro        ea        eb        ec      prba      prca      prcb\n")
    f.write(f"{1:10d}{1.1e-6:10.2E}{0.18:10.4f}{0.18:10.4f}{0.0:10.4f}{0.0:10.4f}{0.0:10.4f}{0.0:10.4f}\n")
    for _ in range(5):
        f.write("".join(f"{0.0:10.4f}" for _ in range(8)) + "\n")
    f.write("*END\n")
print(f"\nK 文件: {DECK}  ({os.path.getsize(DECK)/1e6:.2f} MB)")
print("PID 单元数:", dict(sorted(cnt.items())))

# ---------- QA 摘要 ----------
kp = {g: (x, y, z) for g, x, y, z in knodes}


def zstat(pid):
    zs = collections.Counter()
    for p, ns in kelems:
        if p != pid:
            continue
        for n in ns:
            zs[round(kp[n][2], 3)] += 1
    return dict(sorted(zs.items()))


def normal_z(ns):
    """单元法向的 Z 分量 (Newell 法: 对全部顶点求和, 凹四边形成立;
    只看前三个点在凹角处会给出反向的假信号)"""
    nz = 0.0
    m = len(ns)
    for i in range(m):
        a, b = kp[ns[i]], kp[ns[(i + 1) % m]]
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return nz


print("\n=== QA ===")
for pid in sorted(cnt):
    print(f"PID{pid}: {cnt[pid]} 单元, Z分布 {zstat(pid)}")


# 界面共节点
def elem_nodes(pid):
    s = set()
    for p, ns in kelems:
        if p == pid:
            s.update(ns)
    return s


b2, c3, s4, t5 = elem_nodes(2), elem_nodes(3), elem_nodes(4), elem_nodes(5)
print(f"界面共节点: cav∩belt={len(c3 & b2)}  seam∩cav={len(s4 & c3)}  tether∩belt={len(t5 & b2)}  tether∩cav={len(t5 & c3)}")

# ---- 法向一致性: 按层期望 (上层 +Z 朝外 / 下层 -Z 朝外), 不是按 2D 投影符号 ----
# LS-DYNA 壳单元法向 = 节点序右手法则; 封闭气腔上层应指 +Z, 下层应指 -Z。
print("\n-- 法向一致性 (按层期望, 非2D投影) --")
bad_norm = collections.Counter()
layer_norm = collections.defaultdict(collections.Counter)
for pid, ns in kelems:
    nz = normal_z(ns)
    zs_ = [kp[n][2] for n in ns]
    zavg = sum(zs_) / len(zs_)
    if pid == 3 and abs(zavg) > 1e-6:
        # 期望: 平均 z>0 的单元法向 +Z, z<0 的单元法向 -Z
        sign_expect = 1 if zavg > 0 else -1
        layer_norm["cav_up" if zavg > 0 else "cav_dn"][("+" if nz > 0 else "-")] += 1
        if nz * sign_expect <= 0:
            bad_norm[pid] += 1
    else:
        layer_norm[f"pid{pid}"][("+" if nz > 0 else "-")] += 1
        if nz <= 0:
            bad_norm[pid] += 1          # 平面层统一期望 +Z
for k in sorted(layer_norm):
    print(f"   {k}: {dict(layer_norm[k])}")
for pid in sorted(cnt):
    st = "OK" if bad_norm[pid] == 0 else f"<-- {bad_norm[pid]} 个法向反了"
    print(f"   PID{pid}: 法向异常 {bad_norm[pid]}  {st}")

# ---- 自由边分类: 界面边(两侧有单元) vs 真实边界 ----
print("\n-- 自由边分类 (每 PID 只看本 PID 内部边使用次数) --")
iface_pids = {2: {3, 4}, 3: {2, 4, 5}, 4: {3}, 5: {2, 3}}


def edge_use(nslist):
    ec = collections.Counter()
    for ns in nslist:
        u = list(dict.fromkeys(ns))
        for i in range(len(u)):
            a, b = u[i], u[(i + 1) % len(u)]
            ec[(min(a, b), max(a, b))] += 1
    return ec


for pid in sorted(cnt):
    nslist = [ns for p, ns in kelems if p == pid]
    ec = edge_use(nslist)
    free = [e for e, c in ec.items() if c == 1]
    # 该边上任一节点被别的 PID 引用 => 界面边(共节点侧), 否则为真实开放边界
    other = set()
    for p, ns in kelems:
        if p != pid and p in iface_pids.get(pid, set()):
            other.update(ns)
    real = [e for e in free if e[0] not in other and e[1] not in other]
    print(f"   PID{pid}: 自由边 {len(free)}  = 界面侧 {len(free)-len(real)} + 真实边界 {len(real)}")

# ---- 面积: 用真实单元面积 (非 2D 投影), 与 CAD 环面积对比 ----
print("\n-- 面积自洽 (3D 单元面积和, 双层气腔按几何面积计) --")
area = collections.defaultdict(float)


def tri_area3(p0, p1, p2):
    ux, uy, uz = p1[0]-p0[0], p1[1]-p0[1], p1[2]-p0[2]
    vx, vy, vz = p2[0]-p0[0], p2[1]-p0[1], p2[2]-p0[2]
    cx = uy*vz - uz*vy
    cy = uz*vx - ux*vz
    cz = ux*vy - uy*vx
    return 0.5 * math.sqrt(cx*cx + cy*cy + cz*cz)


for pid, ns in kelems:
    p = [kp[n] for n in ns]
    if len(p) == 3:
        area[pid] += tri_area3(p[0], p[1], p[2])
    else:
        area[pid] += tri_area3(p[0], p[1], p[2]) + tri_area3(p[0], p[2], p[3])
for pid in sorted(area):
    note = "  (=双层, 单面需 /2)" if pid == 3 else ""
    print(f"   PID{pid}: {area[pid]:.0f} mm²{note}")
if area[3]:
    print(f"   PID3 上层单面 ≈ {area[3]/2:.0f} mm²")

# ---- 单元尺度 & 单元质量最小项 ----
print("\n-- 单元尺寸 --")
for pid in sorted(cnt):
    el = 0.0
    mn = 1e9
    for p, ns in kelems:
        if p != pid:
            continue
        u = list(dict.fromkeys(ns))
        for i in range(len(u)):
            a, b = u[i], u[(i + 1) % len(u)]
            d = math.dist(kp[a], kp[b])
            mn = min(mn, d)
        el += 1
    print(f"   PID{pid}: 最短边 {mn:.3f} mm")
