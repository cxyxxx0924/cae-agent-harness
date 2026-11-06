#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
checks.py — auto_gate 自动校验模块（案例无关，规则读 gate_rules.json）

每个 check_* 返回 result dict:
  {"name", "status": PASS/WARN/FAIL, "summary", "metrics", "detail":[...], "figures":[...]}

反假阳性口径已固化(沉淀自 cab1 实战):
  * 环几何匹配: 逐 CAD 线拆解 —— 环整体 boundary 偏差若仅由少数"局部特征线"
    (如充气口领圈)驱动, 且这些线的点已被网格节点在 cover_tol 内覆盖, 则降级 WARN。
  * 拉带连接: tether∩cavity 共节点若同时属于 belt 且 |Y|<=interface_y_tol,
    属"拉带经布带穿过皮带腔界面"正常拓扑, 不计误连。
"""
import math
import os
from collections import defaultdict, deque

import kio
from svgfig import Figure, PALETTE, bar_svg


# ---------------- CAD 线解析 ----------------

def parse_cad_lines(path):
    """lines_pts_2d.txt: 'TAG lid len sx sz ex ez | x z;x z;...'
    返回 {tag: {lid: [(x,z),...]}}"""
    out = defaultdict(lambda: defaultdict(list))
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            if "|" not in ln:
                continue
            head, poly = ln.split("|", 1)
            toks = head.split()
            if len(toks) < 2:
                continue
            tag, lid = toks[0], toks[1]
            for tok in poly.split(";"):
                v = tok.split()
                if len(v) >= 2:
                    try:
                        out[tag][lid].append((float(v[0]), float(v[1])))
                    except ValueError:
                        pass
    return {t: dict(v) for t, v in out.items()}


# ---------------- 几何 helper ----------------

def convex_hull(pts):
    """Andrew monotone chain. 返回 hull 多边形(顺时针/逆时针)。"""
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
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


def poly_area(poly):
    if len(poly) < 3:
        return 0.0
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i+1) % len(poly)]
        s += x1*y2 - x2*y1
    return abs(s) / 2.0


def poly_perim(poly):
    if len(poly) < 2:
        return 0.0
    return sum(math.hypot(poly[i][0]-poly[(i+1)%len(poly)][0],
                          poly[i][1]-poly[(i+1)%len(poly)][1]) for i in range(len(poly)))


def centroid(pts):
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))


def _in_quad(x, y, q):
    """凸四边形符号法内含测试(容差内视作边上)。"""
    sign = 0
    n = len(q)
    for i in range(n):
        x1, y1 = q[i]; x2, y2 = q[(i + 1) % n]
        cr = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        if abs(cr) < 1e-9:
            continue
        s = 1 if cr > 0 else -1
        if sign == 0:
            sign = s
        elif s != sign:
            return False
    return True


def point_in_quads(pt, quads):
    """quads: [(bbox, poly)]; bbox=(xmin,ymin,xmax,ymax) 预滤。"""
    x, y = pt
    for (bb, poly) in quads:
        if bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]:
            if _in_quad(x, y, poly):
                return True
    return False


def build_quads(elems_by_pid, nodes):
    """pid -> [(bbox, poly_xy)]"""
    out = {}
    for pid, els in elems_by_pid.items():
        qs = []
        for ns in els:
            nn = [n for n in ns if n != 0 and n in nodes]
            if len(nn) < 3:
                continue
            poly = [(nodes[n][0], nodes[n][2]) for n in nn]
            xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
            qs.append(((min(xs), min(ys), max(xs), max(ys)), poly))
        out[pid] = qs
    return out


# ---------------- 1) 拓扑门禁 ----------------

def check_topology(K, rules, case):
    r = rules["topology"]
    nodes = K["nodes"]; elems = K["elems"]
    detail = []; status = "PASS"; metrics = {}

    # 重复节点(同坐标)
    if r["forbid_dup_nodes"]:
        seen = {}; dup = 0
        coord = defaultdict(list)
        for nid, c in nodes.items():
            key = (round(c[0], 4), round(c[1], 4), round(c[2], 4))
            coord[key].append(nid)
        dup = sum(len(v)-1 for v in coord.values() if len(v) > 1)
        metrics["dup_nodes"] = dup
        detail.append(("重复节点(同坐标)", dup, "PASS" if dup == 0 else "FAIL"))
        if dup: status = "FAIL"

    # 重复单元(同节点拓扑)
    if r["forbid_dup_elems"]:
        sig = defaultdict(int)
        for pid, els in elems.items():
            for ns in els:
                nn = tuple(sorted(n for n in ns if n != 0))
                sig[nn] += 1
        dup = sum(v-1 for v in sig.values() if v > 1)
        metrics["dup_elems"] = dup
        detail.append(("重复单元(同拓扑)", dup, "PASS" if dup == 0 else "FAIL"))
        if dup: status = "FAIL"

    # 孤儿节点(定义但无单元引用) —— clean_kfile 应已清除; 此处复检
    used = set()
    for pid, els in elems.items():
        for ns in els:
            used.update(n for n in ns if n != 0)
    orphans = set(nodes) - used
    metrics["orphan_nodes"] = len(orphans)
    detail.append(("孤儿节点(无单元引用)", len(orphans), "PASS" if not orphans else "FAIL"))
    if orphans: status = "FAIL"

    # 引用完整性(元素节点都在)
    miss = sum(1 for pid, els in elems.items() for ns in els for n in ns if n != 0 and n not in nodes)
    metrics["missing_node_refs"] = miss
    detail.append(("缺失节点引用", miss, "PASS" if miss == 0 else "FAIL"))
    if miss: status = "FAIL"

    # 最小边
    med = kio.min_edge_by_pid(elems, nodes)
    metrics["min_edge_by_pid"] = {p: round(v[0], 3) for p, v in med.items()}
    short = {p: 0 for p in elems}
    for pid, els in elems.items():
        c = 0
        for ns in els:
            nn = [n for n in ns if n != 0]
            for i in range(len(nn)):
                a, b = nn[i], nn[(i+1) % len(nn)]
                if a in nodes and b in nodes:
                    d = math.dist(nodes[a], nodes[b])
                    if d < r["min_edge_mm"]:
                        c += 1
        short[pid] = c
    metrics["short_edges_by_pid"] = short
    any_short = any(v > 0 for v in short.values())
    st = "FAIL" if (any_short and r["min_edge_hard_fail"]) else ("WARN" if any_short else "PASS")
    detail.append((f"最小边 <{r['min_edge_mm']}mm", dict(short), st))
    if st == "FAIL": status = "FAIL"
    elif st == "WARN" and status == "PASS": status = "WARN"

    # 连通性
    comp = kio.connectivity(elems)
    metrics["components_by_pid"] = comp
    detail.append(("每 PID 连通分量", comp, "INFO"))

    # 自由边
    fe = kio.free_edges_by_pid(elems)
    metrics["free_edges_by_pid"] = fe
    detail.append(("每 PID 自由边", fe, "INFO"))

    summ = f"节点 {len(nodes)} | 单元 {sum(len(e) for e in elems.values())} | PID {sorted(elems)} | 重复节点 {metrics.get('dup_nodes',0)} / 重复单元 {metrics.get('dup_elems',0)}"
    return {"name": "拓扑门禁", "status": status, "summary": summ,
            "metrics": metrics, "detail": detail, "figures": []}


# ---------------- 2) Y 分层核验 ----------------

def check_layers(K, rules, case):
    tol = rules["layers"]["y_match_tol"]
    itol = rules["layers"]["interface_collapse_tol"]
    scheme = case["pid_scheme"]; layers = case["layers"]
    nodes = K["nodes"]; elems = K["elems"]
    detail = []; status = "PASS"; metrics = {}
    np_ = kio.node_pids(elems)  # 节点 -> 所属 pid 集合(识别界面共节点)

    def nodes_of(pid):
        s = set()
        for ns in elems.get(pid, []):
            s.update(n for n in ns if n != 0)
        return s

    role_pid = {v: k for k, v in scheme.items()}  # pid -> role
    for pid, role in role_pid.items():
        if role not in layers:
            continue
        ns = nodes_of(pid)
        if not ns:
            continue
        ys = defaultdict(int)
        for n in ns:
            ys[round(nodes[n][1], 2)] += 1
        metrics[f"pid{pid}_{role}_y"] = dict(sorted(ys.items()))
        expect = layers[role]
        if isinstance(expect, (int, float)):
            expects = [float(expect)]
        else:
            expects = [float(e) for e in expect]
        # 每个节点 Y 应落在某个 expect(±tol) 或界面塌缩(|Y|<=itol 且期望双层);
        # 跨角色共节点(界面)可取搭档角色的 Y, 不强制(如拉带接布带 -> Y0)
        bad = 0; iface = 0
        for n in ns:
            y = nodes[n][1]
            if any(abs(y - e) <= tol for e in expects):
                continue
            if len(expects) > 1 and abs(y) <= itol:
                continue
            if len(np_.get(n, ())) > 1:  # 跨角色界面节点
                iface += 1
                continue
            bad += 1
        st = "PASS" if bad == 0 else "FAIL"
        detail.append((f"{role}(PID{pid}) Y 分层 期望{expects}",
                       f"越界 {bad} | 界面共节点 {iface}(豁免)", st))
        if bad: status = "FAIL"

    # 气腔双层专项(若配置)
    if "cavity" in scheme and "cavity" in layers and isinstance(layers["cavity"], list):
        pid = scheme["cavity"]
        ns = nodes_of(pid)
        ycount = defaultdict(int)
        for n in ns:
            ycount[round(nodes[n][1], 2)] += 1
        has_up = any(y > tol for y in ycount)
        has_dn = any(y < -tol for y in ycount)
        has_bnd = any(abs(y) <= itol for y in ycount)
        metrics["cavity_double_layer"] = {"up": has_up, "dn": has_dn, "boundary_y0": has_bnd}
        st = "PASS" if (has_up and has_dn) else "FAIL"
        detail.append(("气腔双层(Y±) + 界面收Y0",
                       f"上{has_up} 下{has_dn} 边界{has_bnd}", st))
        if not (has_up and has_dn): status = "FAIL"

    return {"name": "Y分层核验", "status": status, "summary": "各角色 Y 位置符合案例配置",
            "metrics": metrics, "detail": detail, "figures": []}


# ---------------- 3) 环面积 + 节点路程(周长) ----------------

def check_ring_area_perimeter(K, rules, case, cad, figdir):
    rp = rules["ring_area_perimeter"]
    nodes = K["nodes"]; elems = K["elems"]; scheme = case["pid_scheme"]
    cad_tag = case.get("cad_tag", {})
    rows = []; detail = []; status = "PASS"; metrics = {}; figs = []
    overlays = []

    for role, pid in scheme.items():
        if role not in cad_tag:
            continue
        tag = cad_tag[role]
        cad_pts = [p for lines in cad.get(tag, {}).values() for p in lines]
        ns = set()
        for e in elems.get(pid, []):
            ns.update(n for n in e if n != 0)
        mesh_xy = [(nodes[n][0], nodes[n][2]) for n in ns if n in nodes]
        if not cad_pts or not mesh_xy:
            continue
        cad_hull = convex_hull(cad_pts)
        mesh_hull = convex_hull(mesh_xy)
        a_cad = poly_area(cad_hull); a_mesh = poly_area(mesh_hull)
        area_ratio = a_mesh / a_cad if a_cad else 0.0
        # 节点路程(周长): 用凸包周长(对闭合环如气腔/缝线亦有定义; 与面积同基准)
        p_cad = poly_perim(cad_hull)
        p_mesh = poly_perim(mesh_hull)
        perim_ratio = p_mesh / p_cad if p_cad else 0.0
        a_ok = rp["area_ratio_min"] <= area_ratio <= rp["area_ratio_max"]
        p_ok = rp["perimeter_ratio_min"] <= perim_ratio <= rp["perimeter_ratio_max"]
        st = "PASS" if (a_ok and p_ok) else "WARN"
        if status == "PASS" and st != "PASS":
            status = "WARN"
        metrics[role] = {"area_cad": round(a_cad, 1), "area_mesh": round(a_mesh, 1),
                         "area_ratio": round(area_ratio, 4),
                         "perim_cad": round(p_cad, 1), "perim_mesh": round(p_mesh, 1),
                         "perim_ratio": round(perim_ratio, 4)}
        detail.append((f"{role}", f"面积比 {area_ratio:.3f} | 周长比 {perim_ratio:.3f}", st))
        rows.append((f"{role} 面积比", area_ratio, rp["area_ratio_min"], rp["area_ratio_max"],
                     PALETTE.get(role, PALETTE["mesh"]), ""))
        rows.append((f"{role} 周长比", perim_ratio, rp["perimeter_ratio_min"], rp["perimeter_ratio_max"],
                     PALETTE.get(role, PALETTE["mesh"]), ""))
        overlays.append((role, cad_hull, mesh_hull))

    # 图1: 面积/周长比 bar
    if rows:
        figs.append(bar_svg("环面积 / 节点路程(周长) 自洽", "网格 vs CAD (合格区=规则带)",
                            rows, os.path.join(figdir, "gate_ring_area_perim.svg"), unit="x"))
    # 图2: 环脚印叠加(CAD hull vs mesh hull)
    if overlays:
        f = Figure(title="环脚印叠加 (CAD 凸包 vs 网格凸包)", subtitle="面积自洽目检")
        for role, ch, mh in overlays:
            if ch: f.polyline(ch + [ch[0]], color=PALETTE["cad"], width=1.2, tag=f"{role} CAD" if role == overlays[0][0] else None)
            if mh: f.polyline(mh + [mh[0]], color=PALETTE.get(role, PALETTE["mesh"]), width=1.2, dash="3,2",
                              tag=f"{role} mesh" if role == overlays[0][0] else None)
        # legend 全部
        for role, ch, mh in overlays:
            f.legend.append((PALETTE["cad"], f"{role} CAD", "line"))
            f.legend.append((PALETTE.get(role, PALETTE["mesh"]), f"{role} mesh", "line"))
        figs.append(f.save(os.path.join(figdir, "gate_ring_footprint.svg")))

    return {"name": "环面积/节点路程", "status": status,
            "summary": "各环面积比/周长比落入合格带", "metrics": metrics,
            "detail": detail, "figures": figs}


# ---------------- 4) 环几何匹配(逐线拆解, 反假阳性) ----------------

def check_ring_geometry(K, rules, case, cad, figdir):
    rg = rules["ring_geom"]; plb = rg["per_line_breakdown"]
    main_tol = rg["boundary_dev_main_mm"]
    nodes = K["nodes"]; elems = K["elems"]; scheme = case["pid_scheme"]
    cad_tag = case.get("cad_tag", {})
    use = kio.edge_use_map(elems)
    np_ = kio.node_pids(elems)
    all_quads = build_quads(elems, nodes)
    all_xy = {pid: [(nodes[n][0], nodes[n][2]) for e in els for n in e if n != 0 and n in nodes]
              for pid, els in elems.items()}
    detail = []; status = "PASS"; metrics = {}; figs = []

    for role, pid in scheme.items():
        if role not in cad_tag:
            continue
        tag = cad_tag[role]
        lines = cad.get(tag, {})
        if not lines:
            continue
        all_nodes = set()
        for e in elems.get(pid, []):
            all_nodes.update(n for n in e if n != 0)
        node_xy = [(nodes[n][0], nodes[n][2]) for n in all_nodes if n in nodes]
        # 自由边节点(外边界); 无则退化为全部节点
        fe_nodes = set()
        for e in elems.get(pid, []):
            nn = [n for n in e if n != 0]
            for i in range(len(nn)):
                a, b = nn[i], nn[(i+1) % len(nn)]
                if use.get((a, b) if a < b else (b, a), 0) == 1:
                    fe_nodes.add(a); fe_nodes.add(b)
        bnd_xy = [(nodes[n][0], nodes[n][2]) for n in fe_nodes if n in nodes] or node_xy
        own_quads = all_quads.get(pid, [])
        other_quads = [q for opid, qs in all_quads.items() if opid != pid for q in qs]
        other_xy = [p for opid, pts in all_xy.items() if opid != pid for p in pts]

        def nearest(px, pz, arr):
            best = 1e18
            for (x, z) in arr:
                d = (px-x)**2 + (pz-z)**2
                if d < best: best = d
            return math.sqrt(best)

        def cover_dist(px, pz, quads, xy):
            if point_in_quads((px, pz), quads):
                return 0.0
            return nearest(px, pz, xy)

        real_fail_lines = []; warn_lines = []; crosspid_lines = []
        worst_overall = 0.0; worst_at = None
        for lid, pts in lines.items():
            w_bnd = 0.0; wpt = None; hot = []
            for (x, z) in pts:
                db = nearest(x, z, bnd_xy)
                if db > w_bnd: w_bnd = db; wpt = (x, z)
                if db > main_tol: hot.append((x, z))
            worst_overall = max(worst_overall, w_bnd)
            if wpt and w_bnd == worst_overall: worst_at = wpt
            if w_bnd > main_tol and plb["enabled"]:
                # 高偏差线三级判定: 自有 fabric(局部特征) / 他 PID fabric(跨PID/接口/错标) / 真缺口
                own_cov = max((cover_dist(x, z, own_quads, node_xy) for (x, z) in hot), default=1e18)
                if own_cov <= plb["cover_tol_mm"]:
                    warn_lines.append((lid, round(w_bnd, 2), round(own_cov, 2), "own"))
                else:
                    oth_cov = max((cover_dist(x, z, other_quads, other_xy) for (x, z) in hot), default=1e18)
                    if oth_cov <= plb["cover_tol_mm"]:
                        crosspid_lines.append((lid, round(w_bnd, 2), round(oth_cov, 2)))
                    else:
                        real_fail_lines.append((lid, round(w_bnd, 2), round(oth_cov, 2)))
        # 判定
        if real_fail_lines:
            st = "FAIL"; status = "FAIL"
        elif warn_lines or crosspid_lines:
            st = "WARN"
            if status == "PASS": status = "WARN"
        else:
            st = "PASS"
        metrics[role] = {"worst_boundary_mm": round(worst_overall, 2),
                         "worst_at": [round(worst_at[0], 1), round(worst_at[1], 1)] if worst_at else None,
                         "real_fail_lines": real_fail_lines,
                         "local_feature_warn_lines": warn_lines,
                         "crosspid_warn_lines": crosspid_lines}
        msg = f"主边界最差 {worst_overall:.2f}mm"
        if warn_lines: msg += f" | 局部特征线(自有 fabric) WARN {len(warn_lines)}"
        if crosspid_lines: msg += f" | 跨 PID 覆盖线 WARN {len(crosspid_lines)}(核对应属他 PID/接口)"
        if real_fail_lines: msg += f" | 真缺口线 FAIL {len(real_fail_lines)}"
        detail.append((f"{role} 边界贴合(CAD→网格自由边)", msg, st))

        # 图: CAD vs 网格边界叠加 + 最差标注
        f = Figure(title=f"{role} 几何匹配 (CAD vs 网格边界)", subtitle=f"最差 {worst_overall:.2f}mm @ {worst_at}")
        for lid, pts in lines.items():
            f.polyline(pts, color=PALETTE["cad"], width=1.0, opacity=0.8)
        f.points(node_xy, color=PALETTE["mesh"], r=0.7, opacity=0.5)
        if worst_at:
            f.marker(worst_at[0], worst_at[1], color=PALETTE["fail"], label=f"{worst_overall:.1f}mm")
        f.legend = [(PALETTE["cad"], "IGES 曲线", "line"), (PALETTE["mesh"], "网格节点", "dot")]
        figs.append(f.save(os.path.join(figdir, f"gate_geom_{role}.svg")))

    return {"name": "环几何匹配", "status": status,
            "summary": "IGES 曲线 vs 网格边界(逐线拆解, 局部特征线降级)",
            "metrics": metrics, "detail": detail, "figures": figs}


# ---------------- 5) 拉带连接(反假阳性) ----------------

def check_tether(K, rules, case, figdir):
    tr = rules["tether"]
    scheme = case["pid_scheme"]
    belt = scheme.get("belt"); cav = scheme.get("cavity")
    seam = scheme.get("seam"); teth = scheme.get("tether")
    if teth is None:
        return {"name": "拉带连接", "status": "PASS", "summary": "无拉带角色", "metrics": {}, "detail": [], "figures": []}
    nodes = K["nodes"]; elems = K["elems"]; np_ = kio.node_pids(elems)
    itol = tr["interface_y_tol"]
    detail = []; status = "PASS"; metrics = {}; figs = []

    def nodes_of(pid):
        s = set()
        for e in elems.get(pid, []):
            s.update(n for n in e if n != 0)
        return s
    teth_nodes = nodes_of(teth)
    belt_nodes = nodes_of(belt) if belt else set()
    seam_nodes = nodes_of(seam) if seam else set()
    cav_nodes = nodes_of(cav) if cav else set()

    # 正确连接: tether ∩ belt
    ok_belt = teth_nodes & belt_nodes
    # 禁止: tether ∩ seam
    bad_seam = teth_nodes & seam_nodes
    # 反假阳性: tether ∩ cavity 拆分
    teth_cav = teth_nodes & cav_nodes
    benign_cav = []; real_cav = []
    for n in teth_cav:
        y = nodes[n][1] if n in nodes else 0.0
        if tr["belt_cavity_interface_benign"] and (belt and n in belt_nodes) and abs(y) <= itol:
            benign_cav.append(n)
        else:
            real_cav.append(n)

    metrics["shared_belt"] = len(ok_belt)
    metrics["shared_seam_forbid"] = len(bad_seam)
    metrics["shared_cav_total"] = len(teth_cav)
    metrics["shared_cav_benign_interface"] = len(benign_cav)
    metrics["shared_cav_real_misconnect"] = len(real_cav)

    if len(bad_seam) > 0:
        status = "FAIL"
        detail.append((f"拉带误连缝线(PID{seam})", f"{len(bad_seam)} 节点", "FAIL"))
    else:
        detail.append((f"拉带误连缝线(PID{seam})", "0 节点", "PASS"))
    if len(real_cav) > 0:
        status = "FAIL"
        detail.append((f"拉带真误连气腔(|Y|>{itol}, 非皮带界面)", f"{len(real_cav)} 节点", "FAIL"))
    else:
        detail.append((f"拉带∩气腔(经皮带界面, 良性)", f"{len(benign_cav)} 节点 (真误连 {len(real_cav)})", "PASS"))
    st_b = "PASS" if len(ok_belt) >= tr["min_shared_belt_nodes"] else "FAIL"
    if st_b == "FAIL": status = "FAIL"
    detail.append((f"拉带↔布带共节点(正确连接)", f"{len(ok_belt)} 节点", st_b))

    # 每连通组分是否都接布带
    comp = kio.connectivity({teth: elems.get(teth, [])})
    metrics["tether_components"] = comp.get(teth, 0)

    # 图: 拉带连接特写(X-Z), 标共节点
    f = Figure(title="拉带↔布带 连接特写", subtitle=f"共节点 {len(ok_belt)} | 皮带腔界面(良性) {len(benign_cav)} | 真误连 {len(real_cav)}")
    f.points([(nodes[n][0], nodes[n][2]) for n in teth_nodes if n in nodes], color=PALETTE["tether"], r=1.2, opacity=0.7, tag="拉带节点")
    f.points([(nodes[n][0], nodes[n][2]) for n in ok_belt if n in nodes], color=PALETTE["ok"], r=2.4, tag="拉带∩布带(正确)")
    if benign_cav:
        f.points([(nodes[n][0], nodes[n][2]) for n in benign_cav if n in nodes], color=PALETTE["warn"], r=2.4, tag="皮带腔界面(良性)")
    if real_cav:
        f.points([(nodes[n][0], nodes[n][2]) for n in real_cav if n in nodes], color=PALETTE["fail"], r=3.2, tag="真误连气腔")
    figs.append(f.save(os.path.join(figdir, "gate_tether_conn.svg")))

    return {"name": "拉带连接", "status": status,
            "summary": f"接布带 {len(ok_belt)} | 误连缝线 {len(bad_seam)} | 真误连气腔 {len(real_cav)} (皮带腔界面良性 {len(benign_cav)})",
            "metrics": metrics, "detail": detail, "figures": figs}


# ---------------- 汇总 ----------------

def overall_status(results):
    if any(r["status"] == "FAIL" for r in results):
        return "FAIL"
    if any(r["status"] == "WARN" for r in results):
        return "WARN"
    return "PASS"
