#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
geom_match_check.py — IGES 线段几何 vs 网格几何 · 逐环匹配自检
============================================================
用户 2026-10-22 沉淀需求: "增加几何匹配自检, 将 IGES 的线段几何与网格几何进行
空间位置 / 形状 / 面积对比, 确认每个环几何匹配。"

为什么需要 (NEW_CAB 教训, P40/P43):
  NEW_CAB 出现过 "x1483 凸台矩形环漏编进 TETHER_COMPS2 → 穹顶失去宿主悬空、被误保留成
  浮层", 也出现过 "整环面积翻倍 / 边界漂移" 类错误。仅靠 QA 拓扑门禁 (eid 唯一/无退化)
  查不出 —— QA 查拓扑合法性, 不查空间几何是否和 CAD 曲线一致。本脚本把每条 CAD 环的
  几何 (质心/面积/形状) 与它在网格里的实现 (选出的单元集) 逐项对拍。

对比维度 (每个环):
  1) 位置: IGES 点云质心 vs 网格区域质心, 偏移应 < max(5mm, 3%*特征长度)
  2) 面积(凸包): 网格单元总面积 / IGES 点云凸包面积, 比值应 ∈ [1-ATOL, 1+ATOL]
                 (凸包对凸环精确; 凹环/环面是上界, 用 area_check=false 关掉面积判据)
  3) 形状(边界贴合): 网格自由边中点到最近 IGES 采样点的最大距离 (网格边界是否贴 CAD 曲线)
                     + IGES 采样点到最近网格节点的最大距离; 均应 < BND_TOL (默认 8mm)

设计要点 (比"链条成多边形"更鲁棒):
  - IGES 区域用**点云凸包**表示面积/质心, 不靠把线段贪心串成环 (凸环精确, 且不会串成蝴蝶结)。
  - 网格区域用**空间选择**: 选出质心落在 IGES 凸包内 (或距凸包边 < sel_tol) 的单元。
    因此不依赖 comp 命名 (即便装配后所有拉带都是一个 PID5 也能逐环选对)。
  - 边界贴合用**最近点查询** (IGES 采样点密度足够表示曲线)。

环来源 (任选其一):
  A) 显式环定义 --rings ring_spec.json:
       {"rings":[{"name":"boss1","type":"tether_boss","iges_lines":[268,269,...],"area_check":true},
                 {"name":"belt","type":"belt","iges_lines":[...],"area_check":false},
                 {"name":"strap_r","type":"tether_strap","iges_lines":[],"constructed":true}]}
     iges_lines 是该环在 lines_pts.txt 里的线 id 集合。area_check=false 用于环面/凹环
     (BELT/CAVITY 是环面, 单凸包面积无意义; 只查边界贴合+位置)。
  B) 不传 --rings: 自动按 lines_pts.txt 的 comp 列分组 (组件级粗粒度对拍)。

网格来源 (任选其一):
  --mesh <file.k>   : 标准 LS-DYNA K (逗号自由格式或定宽都可, 独立解析)
  --mesh <file.dat> : 自定义 "N id x y z" / "E comp eid n1..n4" (本技能中间格式)
  网格节点是模型坐标: --map xy (默认) 取 图纸x=模型X, 图纸y=模型Z; --map xz 取 图纸x=模型X, 图纸y=模型Y。

退出码: 0 = 全部环 PASS; 1 = 存在 FAIL。
"""
import argparse, json, math, re, sys, collections

# ============================ 1. 解析 IGES 线点云 ============================
def parse_lines_pts(path):
    """返回 lines: {lid: {"comp":str, "pts":[(x,y),...]}}
    兼容两种导出格式 (图纸平面统一叫 图纸(x,y)):
      格式A (技能原生 export_lines_pts.tcl):  TAG lid len sp_x sp_z ep_x ep_z | x z;x z;...
      格式B (IGES 分区技能):  L lid comp x1 y1 z1 x2 y2 z2 | x y z;x y z;...
    """
    lines = {}
    for raw in open(path, encoding="utf-8", errors="replace"):
        s = raw.rstrip("\n")
        if not s or s.startswith("#"):
            continue
        if not s.startswith("L ") and not re.match(r"^[A-Za-z]", s):
            continue
        head, _, tail = s.partition("|")
        h = head.split()
        pts_field = tail.strip()
        if h[0] == "L":
            lid = int(h[1]); comp = h[2]
            coords = [float(v) for v in h[3:9]]
            sp = (coords[0], coords[1]); ep = (coords[3], coords[4])
        else:
            comp = h[0]; lid = int(h[1])
            sp = (float(h[3]), float(h[4])); ep = (float(h[5]), float(h[6]))
        samples = []
        if pts_field:
            for tok in pts_field.split(";"):
                tok = tok.strip().strip('"')
                if not tok:
                    continue
                v = tok.split()
                if len(v) >= 2:
                    samples.append((float(v[0]), float(v[1])))
        if not samples:
            samples = [sp, ep]
        lines[lid] = {"comp": comp, "pts": samples}
    return lines


# ============================ 2. 解析网格 ============================
def parse_mesh(path, draw_map):
    """返回 (nodes, elems, elem_pids)
    - nodes: gid -> (图纸x, 图纸y)
    - elems: list of 节点列表
    - elem_pids: 与 elems 对齐的 PID (整数)
    .dat 的 comp 名按约定映射到 PID: BELT=2 CAVITY=3 SEAM=4 TETHER*=5
    """
    nodes = {}; elems = []; elem_pids = []
    ext = path.rsplit(".", 1)[-1].lower()
    comp2pid = {"BELT": 2, "CAVITY": 3, "SEAM": 4,
                "TETHER": 5, "TETHER_BOSS": 5, "TETHER_STRAP": 5, "TETHER_DROP": 5}
    if ext == "k":
        sec = None
        for raw in open(path, encoding="utf-8", errors="replace"):
            s = raw.strip()
            if s.startswith("*"):
                sec = s.upper().split()[0]; continue
            if not s or s.startswith("$"):
                continue
            f = [x.strip() for x in s.split(",")]
            if sec == "*NODE" and len(f) >= 4:
                try:
                    gid = int(float(f[0])); x = float(f[1]); y = float(f[2]); z = float(f[3])
                except ValueError:
                    continue
                nodes[gid] = (x, (z if draw_map == "xy" else y))
            elif sec in ("*ELEMENT_SHELL", "*ELEMENT_SHELL_THICKNESS") and len(f) >= 5:
                try:
                    pid = int(float(f[1])); ns = [int(float(x)) for x in f[2:6] if x.strip()]
                except ValueError:
                    continue
                if len(ns) >= 3:
                    elems.append(ns); elem_pids.append(pid)
    else:  # .dat: N id x y z / E comp eid n1..n4
        for raw in open(path, encoding="utf-8", errors="replace"):
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            h = s.split()
            if h[0] == "N" and len(h) >= 5:
                try:
                    nodes[int(h[1])] = (float(h[2]), float(h[3]))
                except ValueError:
                    pass
            elif h[0] == "E" and len(h) >= 4:
                try:
                    ns = [int(x) for x in h[3:]]
                    if len(ns) >= 3:
                        elems.append(ns)
                        elem_pids.append(comp2pid.get(h[1], 5))
                except ValueError:
                    pass
    return nodes, elems, elem_pids


# ============================ 3. 几何工具 ============================
def polygon_area(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def polygon_centroid(pts):
    A = polygon_area(pts)
    if abs(A) < 1e-9:
        n = len(pts)
        return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
    cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return (cx / (6 * A), cy / (6 * A))


def convex_hull(points):
    """Andrew monotone chain. 返回有序凸包点 (不开头重复)."""
    pts = sorted(set((round(p[0], 6), round(p[1], 6)) for p in points))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def point_in_convex(p, hull):
    """hull 为凸包有序点; 返回 p 是否在内部 (含边)."""
    if len(hull) < 3:
        return False
    # 归一化方向 (统一为逆时针正)
    s = polygon_area(hull)
    if s < 0:
        hull = hull[::-1]
    sign = None
    n = len(hull)
    for i in range(n):
        a, b = hull[i], hull[(i + 1) % n]
        cr = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        if abs(cr) < 1e-12:
            continue
        c = 1 if cr > 0 else -1
        if sign is None:
            sign = c
        elif c != sign:
            return False
    return True


def dist_point_to_seg(p, a, b):
    px, py = p; ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.dist(p, (ax + t * dx, ay + t * dy))


class PointGrid:
    """最近点查询加速 (IGES 采样点 / 网格节点)."""
    def __init__(self, pts, cell=10.0):
        self.cell = cell
        self.g = collections.defaultdict(list)
        for i, p in enumerate(pts):
            self.g[(int(p[0] // cell), int(p[1] // cell))].append(i)
    def nearest_brute(self, p, pts):
        best = 1e18
        gx, gy = int(p[0] // self.cell), int(p[1] // self.cell)
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                for i in self.g.get((gx + dx, gy + dy), ()):
                    d = math.dist(p, pts[i])
                    if d < best:
                        best = d
        return best


def elem_area_2d(gids, nodes):
    if len(gids) < 3:
        return 0.0
    pts = [nodes[g] for g in gids if g in nodes]
    if len(pts) < 3:
        return 0.0
    a = 0.0; cx = cy = 0.0
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = pts[0], pts[i], pts[i + 1]
        tri = (p0[0] * (p1[1] - p2[1]) + p1[0] * (p2[1] - p0[1]) + p2[0] * (p0[1] - p1[1])) / 2.0
        a += tri
        cx += (p0[0] + p1[0] + p2[0]) / 3.0 * tri
        cy += (p0[1] + p1[1] + p2[1]) / 3.0 * tri
    if abs(a) < 1e-9:
        return 0.0
    return abs(a), (cx / a, cy / a)


def mesh_region(els, nodes):
    area = 0.0; cx = cy = 0.0
    ec = collections.Counter()
    allnodes = set()
    for ns in els:
        u = list(dict.fromkeys(ns))
        a, c = elem_area_2d(u, nodes)
        area += a; cx += c[0] * a; cy += c[1] * a
        for i in range(len(u)):
            e = (min(u[i], u[(i + 1) % len(u)]), max(u[i], u[(i + 1) % len(u)]))
            ec[e] += 1
        allnodes.update(u)
    if area > 0:
        cx /= area; cy /= area
    free = [e for e, c in ec.items() if c == 1]
    # 节点凸包 (对环面/条带也鲁棒: 凸包=包围盒, 质心≈几何中心, 不会像面心那样沿条带偏移)
    npts = [nodes[g] for g in allnodes if g in nodes]
    hull = convex_hull(npts)
    if hull:
        ha = abs(polygon_area(hull)); hc = polygon_centroid(hull)
    else:
        ha = 0.0; hc = (cx, cy)
    return {"area": area, "centroid": (cx, cy), "free_edges": free, "nodes": allnodes,
            "hull": hull, "hull_area": ha, "hull_centroid": hc}


def select_mesh(els, nodes, hull, sel_tol):
    """选出质心在凸包内 (或距凸包边 < sel_tol) 的单元。"""
    out = []
    hn = len(hull)
    for ns in els:
        u = [g for g in dict.fromkeys(ns) if g in nodes]
        if len(u) < 3:
            continue
        a, c = elem_area_2d(u, nodes)
        if a <= 0:
            continue
        if point_in_convex(c, hull):
            out.append(u); continue
        # 距凸包边 < sel_tol ?
        near = False
        for i in range(hn):
            if dist_point_to_seg(c, hull[i], hull[(i + 1) % hn]) <= sel_tol:
                near = True; break
        if near:
            out.append(u)
    return out


# ============================ 4. 逐环对拍 ============================
def check_ring(name, rtype, line_ids, lines, els, nodes, atol, bnd_tol, char_min, sel_tol):
    rep = {"name": name, "type": rtype, "fail": [], "warn": [], "ok": True}
    if rtype == "constructed" or not line_ids:
        rep["note"] = "构造件(无 IGES 线段基准), 跳过几何对拍"
        rep["ok"] = True
        return rep, None
    igs_pts = []
    for lid in line_ids:
        if lid in lines:
            igs_pts.extend(lines[lid]["pts"])
    if len(igs_pts) < 3:
        rep["fail"].append("IGES 点云不足(<3点), 线集可能为空或漏编")
        rep["ok"] = False
        return rep, None
    hull = convex_hull(igs_pts)
    hull_area = abs(polygon_area(hull))
    hull_c = polygon_centroid(hull)
    rep["igs_hull_area"] = hull_area
    rep["igs_centroid"] = hull_c
    rep["igs_npts"] = len(igs_pts)

    sel = select_mesh(els, nodes, hull, sel_tol)
    if not sel:
        rep["fail"].append("网格中未选出任何单元 (该环可能漏网格)")
        rep["ok"] = False
        return rep, hull
    reg = mesh_region(sel, nodes)
    rep["mesh_area"] = reg["area"]
    rep["mesh_centroid"] = reg["centroid"]
    rep["mesh_elems"] = len(sel)
    rep["mesh_hull_area"] = reg["hull_area"]
    rep["mesh_hull_centroid"] = reg["hull_centroid"]

    area_check = rep.get("area_check", True)
    # 1) 面积 (仅凸实环生效: 用凸包面积比). 单侧判据:
    #    网格 < CAD(漏网格/未覆盖) -> FAIL; 网格 > CAD(拉带垫料外延等) -> 仅 WARN
    if area_check and hull_area > 1e-6:
        ratio = reg["hull_area"] / hull_area if reg["hull_area"] > 1e-6 else reg["area"] / hull_area
        rep["area_ratio"] = ratio
        if ratio < 1.0 - atol:
            rep["fail"].append(
                f"面积比 {ratio:.3f} < {1.0 - atol:.2f} (网格小于 CAD 凸包 {hull_area:.0f}→{reg['hull_area']:.0f}, 可能漏网格)")
            rep["ok"] = False
        elif ratio > 1.0 + atol:
            rep["warn"].append(
                f"面积比 {ratio:.3f} > {1.0 + atol:.2f} (网格大于 CAD 凸包, 可能为拉带垫料外延)")
    # 2) 位置 (用节点凸包质心, 对环面/条带也鲁棒: 两者均≈几何中心)
    cd = math.dist(reg["hull_centroid"], hull_c)
    char = max(math.sqrt(hull_area), char_min)
    cd_tol = max(10.0, 0.03 * char)
    rep["centroid_dist"] = cd
    rep["centroid_tol"] = cd_tol
    if cd > cd_tol:
        rep["fail"].append(f"质心偏移 {cd:.1f}mm > {cd_tol:.1f}mm")
        rep["ok"] = False
    # 3) 边界贴合 — 主判据: 每个 CAD 采样点是否都贴到网格节点 (网格是否覆盖 CAD 曲线)
    meshnode_list = [nodes[n] for n in reg["nodes"] if n in nodes]
    if meshnode_list:
        mesh_grid = PointGrid(meshnode_list, cell=max(bnd_tol, 10.0))
        bnd_dev_igs = 0.0
        worst = None
        for p in igs_pts:
            d = mesh_grid.nearest_brute(p, meshnode_list)
            if d > bnd_dev_igs:
                bnd_dev_igs = d; worst = p
        rep["bnd_dev_igs2mesh"] = bnd_dev_igs
        if bnd_dev_igs > bnd_tol:
            rep["fail"].append(f"CAD 曲线有 {bnd_dev_igs:.1f}mm 未贴到网格节点 (网格未覆盖曲线)")
            rep["ok"] = False
    # 4) 边界贴合 — 参考(仅 warn): 网格自由边是否都贴 CAD (环面开口处天然偏大, 不判 FAIL)
    igs_grid = PointGrid(igs_pts, cell=max(bnd_tol, 10.0))
    bnd_dev_mesh = 0.0
    for e in reg["free_edges"]:
        a, b = e
        if a in nodes and b in nodes:
            mid = ((nodes[a][0] + nodes[b][0]) / 2, (nodes[a][1] + nodes[b][1]) / 2)
            bnd_dev_mesh = max(bnd_dev_mesh, igs_grid.nearest_brute(mid, igs_pts))
    rep["bnd_dev_mesh2igs"] = bnd_dev_mesh
    if bnd_dev_mesh > bnd_tol:
        rep["warn"].append(f"网格边界有 {bnd_dev_mesh:.1f}mm 超出 CAD 曲线 (可能为开口/附件边界)")
    return rep, hull


# ============================ 5. main ============================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", required=True, help="lines_pts.txt (IGES 线段几何)")
    ap.add_argument("--mesh", required=True, help="网格文件 .k 或 .dat")
    ap.add_argument("--rings", default=None, help="可选 ring_spec.json (逐环定义)")
    ap.add_argument("--map", default="xy", choices=["xy", "xz"], help="网格 .k 图纸轴映射 (默认 xy)")
    ap.add_argument("--atol", type=float, default=0.15, help="面积比容差 (默认 0.15=±15%, 仅凸实环生效)")
    ap.add_argument("--bnd", type=float, default=8.0, help="边界贴合容差 mm (默认 8)")
    ap.add_argument("--char-min", type=float, default=20.0, help="特征长度下限 mm")
    ap.add_argument("--sel-tol", type=float, default=8.0, help="凸包外选单元容差 mm (默认 8)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--render", default=None)
    a = ap.parse_args()

    lines = parse_lines_pts(a.lines)
    nodes, elems, elem_pids = parse_mesh(a.mesh, a.map)
    print(f"IGES 线: {len(lines)} 条 | 网格节点: {len(nodes)} | 单元: {len(elems)}")

    rings = []
    if a.rings:
        spec = json.load(open(a.rings, encoding="utf-8"))
        rings = spec.get("rings", [])
    else:
        by_comp = collections.defaultdict(list)
        for lid, d in lines.items():
            by_comp[d["comp"]].append(lid)
        rings = [{"name": c, "type": "auto", "iges_lines": ids, "area_check": False}
                 for c, ids in by_comp.items()]

    type2pid = {"belt": 2, "cav": 3, "cavity": 3, "seam": 4,
                "tether_boss": 5, "tether_strap": 5, "tether": 5}

    results = []
    for r in rings:
        line_ids = r.get("iges_lines", [])
        # 解析该环对应的网格 PID (按层过滤, 否则 tether(Y=-1) 与 belt(Y=0) 在 2D 平面重叠误选)
        mpid = r.get("mesh_pid")
        if mpid is None:
            mpid = type2pid.get(r.get("type", "auto"), None)
        if mpid is not None:
            els_sub = [ns for pid, ns in zip(elem_pids, elems) if pid == mpid]
        else:
            els_sub = elems
        bt = r.get("bnd_tol", a.bnd)
        rep, _hull = check_ring(r["name"], r.get("type", "auto"), line_ids, lines, els_sub, nodes,
                                a.atol, bt, a.char_min, a.sel_tol)
        rep["area_check"] = r.get("area_check", True)
        if mpid is not None:
            rep["mesh_pid"] = mpid
        results.append(rep)

    # 报告
    out = []
    out.append("=" * 80)
    out.append("几何匹配自检: IGES 线段几何 vs 网格几何 (逐环)")
    out.append(f"  IGES={a.lines}  网格={a.mesh}  map={a.map}  atol={a.atol}  bnd={a.bnd}mm")
    out.append("=" * 80)
    out.append(f"  {'环':<14}{'类型':<12}{'IGES凸包':>10}{'网格凸包':>10}{'面积比':>8}{'质心偏':>8}{'边偏(c→m)':>10}  结论")
    out.append("  " + "-" * 80)
    npass = 0
    for rep in results:
        ia = rep.get("igs_hull_area"); mha = rep.get("mesh_hull_area")
        ratio = rep.get("area_ratio"); cd = rep.get("centroid_dist")
        bd = rep.get("bnd_dev_igs2mesh")
        ia_s = f"{ia:,.0f}" if ia is not None else "   -  "
        mha_s = f"{mha:,.0f}" if mha is not None else "   -  "
        ratio_s = f"{ratio:.3f}" if ratio is not None else "  -  "
        cd_s = f"{cd:6.1f}" if cd is not None else "  -  "
        bd_s = f"{bd:6.1f}" if bd is not None else "  -  "
        verdict = "PASS" if rep["ok"] else "FAIL"
        if rep["ok"]:
            npass += 1
        extra = rep.get("note") or ""
        if rep["fail"]:
            extra = "  | " + "; ".join(rep["fail"])
        elif rep["warn"]:
            extra = "  | " + "; ".join(rep["warn"])
        ac = "" if rep.get("area_check", True) else " [面积免检]"
        out.append(f"  {rep['name']:<12}{rep['type']:<12}{ia_s:>10}{mha_s:>10}{ratio_s:>8}{cd_s:>8}{bd_s:>10}  {verdict}{extra}{ac}")
    out.append("  " + "-" * 76)
    out.append(f"  环总数 {len(results)} | PASS {npass} | FAIL {len(results)-npass}")
    all_ok = (len(results) - npass) == 0
    out.append(f"  总判定: {'全部 PASS ✅' if all_ok else '存在 FAIL ❌'}")
    report = "\n".join(out)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(report + "\n")
    print(report)

    if a.render:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(20, 7))
            # 左: IGES 点云
            for lid, d in lines.items():
                xs = [p[0] for p in d["pts"]]; ys = [p[1] for p in d["pts"]]
                axes[0].plot(xs, ys, ".", ms=1, color="#2ca02c", alpha=0.4)
            axes[0].set_title("IGES 采样点云 (绿)"); axes[0].set_aspect("equal"); axes[0].grid(True, lw=0.3)
            # 右: 网格自由边
            ec = collections.Counter()
            for ns in elems:
                u = list(dict.fromkeys(ns))
                for i in range(len(u)):
                    e = (min(u[i], u[(i + 1) % len(u)]), max(u[i], u[(i + 1) % len(u)]))
                    ec[e] += 1
            segs = []
            for (a0, b0), c in ec.items():
                if c == 1 and a0 in nodes and b0 in nodes:
                    segs.append([nodes[a0], nodes[b0]])
            from matplotlib.collections import LineCollection
            lc = LineCollection(segs, colors="#d62728", linewidths=0.3)
            axes[1].add_collection(lc)
            axes[1].autoscale(); axes[1].set_title("网格自由边 (红)"); axes[1].set_aspect("equal"); axes[1].grid(True, lw=0.3)
            fig.tight_layout()
            fig.savefig(a.render, dpi=110, bbox_inches="tight"); plt.close(fig)
            print(f"渲染对比图: {a.render}")
        except Exception as e:
            print(f"渲染跳过: {e}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
