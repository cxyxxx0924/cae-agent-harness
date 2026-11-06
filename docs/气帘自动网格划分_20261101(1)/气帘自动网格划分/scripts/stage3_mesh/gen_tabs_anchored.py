# -*- coding: utf-8 -*-
"""gen_tabs_anchored.py — 锚固边受约束的拉带网格生成器

两种模式
--------
`polyline`（默认，方案 A · 显式节点序列）
    沿锚固链**逐点**建一条折线（顶点 = 每个锚固点），用它把拉带面切成两半。
    折线在锚固点处自然打断了共享边：每段恰好 5mm → automesh 每段只放 1 个单元
    → 网格节点**必然落在锚固点上**，与 automesh 的均分无关。
    好处：① 节点位置不再受块宽约束，不必为凑整除而留窄条；
         ② 只切一刀（不再有两条竖切弦线），凸台顶角的 0.3mm 窄条消失；
         ③ 锚固链是圆弧（如 cab2 块3）时折线自动跟随，不再有均分累积偏差。

`triple`（旧方案 · 三刀切）
    过链两端沿法向各一刀 + 沿链方向过锚固线一刀，中间块宽度 = 锚固段长度。
    依赖 automesh 把中间块均分成 5mm，因此链端点距离轮廓必须 < 1mm，
    否则留 0.3~0.9mm 窄条（v4 实测最短 0.317mm）。保留作对照。

用法
----
  python gen_tabs_anchored.py --polys tether_full.json --anchors anchors.json \
        --model cab2.hm --out tabs_anchored.tcl --export tabs_anchored_export.txt \
        [--mode polyline|triple] [--zetab -1.0] [--size 5.0]
"""
import argparse
import json
import math


def norm(v):
    L = math.hypot(v[0], v[1])
    return (v[0] / L, v[1] / L) if L > 1e-12 else (1.0, 0.0)


def bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def center(pts):
    x0, y0, x1, y1 = bbox(pts)
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def match(polys, anchors):
    """每条锚固链配一个凸台: bbox 中心最近"""
    out = {}
    for ai, a in enumerate(anchors):
        ca = center(a["chain"])
        best, bd = None, 1e18
        for pi, poly in enumerate(polys):
            d = math.dist(ca, center(poly["pts"]))
            if d < bd:
                bd, best = d, pi
        out[ai] = (best, bd)
    return out


def point_in_poly(pt, poly):
    x, y = pt[0], pt[1]
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i][0], poly[i][1]
        x2, y2 = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def trim_chain(chain, poly, eps=0.6, ext=2.5):
    """只保留落在凸台面内的锚固点，并把"贴着轮廓"的端点外推到凸台边界。

    为什么要裁: 链端点若在面外 1.5~4.7mm, 竖切线切不到面, 中间锚固块被轮廓
    截短, 间距从 5.00 变成 4.73, 累积偏差 1.57mm。

    为什么要外推: 端点距轮廓只剩 0.2~0.5mm 时, 竖切线切出一条薄条,
    automesh 在薄条里生成退化单元, 组装时两个拉带节点争同一个布带节点,
    输的那个留在 Z=-1, 拉出 60~78° 扭转片。

    为什么阈值只有 0.6mm: 外推会整体平移锚固点。阈值放到 2.5mm 时块0 端点
    (距边界 1.47mm) 被推走, 6 个锚固点只剩 3 个能配上布带节点。
    """
    def dmin(p):
        best = 1e18
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            vx, vy = b[0] - a[0], b[1] - a[1]
            wx, wy = p[0] - a[0], p[1] - a[1]
            L2 = vx * vx + vy * vy
            t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
            best = min(best, math.hypot(wx - t * vx, wy - t * vy))
        return best

    keep = [p for p in chain if point_in_poly(p, poly)]
    if len(keep) < 2:
        keep = [p for p in chain if dmin(p) <= eps]
        if len(keep) < 2:
            keep = list(chain)
    if len(keep) < 2:
        return keep

    d = norm((keep[-1][0] - keep[0][0], keep[-1][1] - keep[0][1]))

    def push_out(p, dirv):
        NEAR = 0.6
        if dmin(p) > NEAR:
            return p
        lo, hi = 0.0, ext
        if point_in_poly((p[0] + dirv[0] * hi, p[1] + dirv[1] * hi), poly):
            return p
        for _ in range(24):
            mid = (lo + hi) / 2
            q = (p[0] + dirv[0] * mid, p[1] + dirv[1] * mid)
            if point_in_poly(q, poly):
                lo = mid
            else:
                hi = mid
        return (p[0] + dirv[0] * lo, p[1] + dirv[1] * lo)

    keep = list(keep)
    keep[0] = push_out(keep[0], (-d[0], -d[1]))
    keep[-1] = push_out(keep[-1], (d[0], d[1]))
    return keep


# ---------------------------------------------------------------- 方案 A
def anchor_polyline(chain, poly, margin=1.25):
    """按锚固点逐点建折线，两端沿端段方向延伸出凸台外。

    折线顶点正好落在每个锚固点上 —— 这就是"显式节点序列"：
    切完之后共享边被顶点打断成若干 5mm 短段，automesh 对每段只放 1 个单元，
    节点就必须落在顶点上。不需要 fixed node，也不依赖均分整除。
    """
    x0, y0, x1, y1 = bbox(poly)
    D = math.hypot(x1 - x0, y1 - y0) * margin
    ch = [tuple(p) for p in chain]
    d0 = norm((ch[0][0] - ch[1][0], ch[0][1] - ch[1][1]))
    d1 = norm((ch[-1][0] - ch[-2][0], ch[-1][1] - ch[-2][1]))
    head = (ch[0][0] + d0[0] * D, ch[0][1] + d0[1] * D)
    tail = (ch[-1][0] + d1[0] * D, ch[-1][1] + d1[1] * D)
    return [head] + ch + [tail]


def offset_polyline(pts, off):
    """把折线整体沿法向平移 off（左法向为正）。用于生成锚固带的外侧边。"""
    out = []
    n = len(pts)
    for i, p in enumerate(pts):
        if i == 0:
            t = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
        elif i == n - 1:
            t = (pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
        else:
            t = (pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1])
        t = norm(t)
        out.append((p[0] - t[1] * off, p[1] + t[0] * off))
    return out


# ---------------------------------------------------------------- 旧方案
def cut_lines(chain, poly, margin=1.25):
    """三条切线 (x0,y0,x1,y1): P0 处法向 / Pn 处法向 / 过中点沿链方向"""
    p0, pn = chain[0], chain[-1]
    d = norm((pn[0] - p0[0], pn[1] - p0[1]))
    n = (-d[1], d[0])
    x0, y0, x1, y1 = bbox(poly)
    L = math.hypot(x1 - x0, y1 - y0) * margin

    def thru(p, dv):
        return (p[0] - dv[0] * L, p[1] - dv[1] * L, p[0] + dv[0] * L, p[1] + dv[1] * L)

    mid = ((p0[0] + pn[0]) / 2, (p0[1] + pn[1]) / 2)
    return [thru(p0, n), thru(pn, n), thru(mid, d)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--polys", required=True)
    ap.add_argument("--anchors", required=True)
    ap.add_argument("--model", default="cab2.hm")
    ap.add_argument("--out", default="tabs_anchored.tcl")
    ap.add_argument("--export", default="tabs_anchored_export.txt")
    ap.add_argument("--mode", default="band", choices=["hybrid", "band", "polyline", "triple"],
                    help="band=折线+锚固带(默认) / polyline=只折线 / triple=旧三刀切")
    ap.add_argument("--band", type=float, default=5.0,
                    help="band 模式下游带厚度（=网格尺寸，保证带内正好一排单元）")
    ap.add_argument("--zetab", type=float, default=-1.0)
    ap.add_argument("--size", type=float, default=5.0)
    a = ap.parse_args()

    polys = json.load(open(a.polys, encoding="utf-8"))
    anchors = json.load(open(a.anchors, encoding="utf-8"))
    mm = match(polys, anchors)
    print(f"凸台 {len(polys)} 个, 锚固链 {len(anchors)} 条, 模式 {a.mode}")

    Z, MS = a.zetab, a.size
    lines = []
    A = lines.append

    A(f"# tabs_anchored.tcl — 拉带网格 (锚固边受布带约束, mode={a.mode})")
    A("foreach _kv {{LsDyna Keyword971_R16.0} {OptiStruct} {HyperMesh}} {")
    A("  if {![catch {eval hm_framework loaduserprofile $_kv}]} {")
    A("    if {[string length [hm_info templatefilename]] > 0} { break }")
    A("  }")
    A("}")
    A('if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }')
    A(f'set fo [open "$P/out/{a.export}" w]')
    A('set rep [open "$P/out/tabs_anchored_report.txt" w]')
    A("proc log {m} { upvar #0 rep rep; puts $rep $m; flush $rep }")
    A(f'*readfile "$P/input/{a.model}"')
    A('log "readfile done"')
    # 注意: elementorder / setedgedensitylink 必须在 *readfile 之后!
    A("*elementorder 1")
    A("*setedgedensitylinkwithaspectratio -1")
    A("set allnodes {}")

    nid = [0]
    coord_map = {}

    def emit(x, y, z):
        """建节点并返回【Tcl 变量名】。必须用 hm_entitymaxid 接真实 id。"""
        nid[0] += 1
        var = f"n{nid[0]}"
        A(f"*createnode {x:.5f} {y:.5f} {z:.5f} 0 0 0")
        A(f"set {var} [hm_entitymaxid nodes]")
        return var

    for ai, (pi, dist) in sorted(mm.items()):
        poly = polys[pi]["pts"]
        chain_raw = anchors[ai]["chain"]
        chain = trim_chain(chain_raw, poly)
        tag = f"tab{ai}"
        print(f"  链{ai} -> 凸台{pi}  (中心距 {dist:.1f}mm, {len(poly)} 顶点, 链 {len(chain)} 点)")

        ids = []
        for x, y in poly:
            k = (round(x, 4), round(y, 4))
            if k not in coord_map:
                coord_map[k] = emit(x, y, Z)
            ids.append(coord_map[k])

        n = len(ids)
        A(f"# ===== {tag} =====")
        line_vars = {}
        A(f"set L_{tag} [list]")
        for i in range(n):
            u, v = ids[i], ids[(i + 1) % n]
            key = (min(u, v), max(u, v))
            if key in line_vars:
                A(f"lappend L_{tag} ${line_vars[key]}")
            else:
                var = f"l_{tag}_{i}"
                A(f"*createlist nodes 1 ${u} ${v}")
                A("catch {*linecreatefromnodes 1 0 150 5 179}")
                A(f"set {var} [hm_entitymaxid lines]")
                A(f"lappend L_{tag} ${var}")
                line_vars[key] = var

        A(f"set sid_{tag} 0")
        A(f"if {{[llength $L_{tag}] >= 3}} {{")
        A(f"  *createmark lines 1 [lindex $L_{tag} 0]")
        A(f"  foreach ln [lrange $L_{tag} 1 end] {{ *appendmark lines 1 $ln }}")
        A("  set i0 [hm_entitymaxid surfaces]")
        A("  set r [catch {*surfacesplineonlinesloop 1 1 0 1} e]")
        A("  *createmark surfaces 1 all")
        A(f"  foreach s [hm_getmark surfaces 1] {{ if {{$s > $i0}} {{ set sid_{tag} $s }} }}")
        A(f'  if {{$sid_{tag} == 0}} {{ log "{tag}: SPLINE FAIL r=$r e=$e" }}')
        A("}")

        if a.mode in ("polyline", "band", "hybrid"):
            pts = anchor_polyline(chain, poly)
            cuts = [pts]
            if a.mode == "band":
                cuts = [offset_polyline(pts, a.band), pts, offset_polyline(pts, -a.band)]
            A(f"set cut_{tag} [list]")
            if a.mode == "hybrid":
                # 锚固线用折线（顶点=锚固点，圆弧链也跟得住）+ 两条竖切做出等宽锚固带
                prev = None
                for (x, y) in pts:
                    cur = emit(x, y, Z)
                    if prev is not None:
                        A(f"*createlist nodes 1 ${prev} ${cur}")
                        A("catch {*linecreatefromnodes 1 0 150 5 179}")
                        A(f"lappend cut_{tag} [hm_entitymaxid lines]")
                    prev = cur
                for (x0, y0, x1, y1) in cut_lines(chain, poly)[:2]:
                    m1 = emit(x0, y0, Z)
                    m2 = emit(x1, y1, Z)
                    A(f"*createlist nodes 1 ${m1} ${m2}")
                    A("catch {*linecreatefromnodes 1 0 150 5 179}")
                    A(f"lappend cut_{tag} [hm_entitymaxid lines]")
            else:
                prev = None
                for seq in cuts:
                    prev = None
                    for (x, y) in seq:
                        cur = emit(x, y, Z)
                        if prev is not None:
                            A(f"*createlist nodes 1 ${prev} ${cur}")
                            A("catch {*linecreatefromnodes 1 0 150 5 179}")
                            A(f"lappend cut_{tag} [hm_entitymaxid lines]")
                        prev = cur
        else:
            A(f"set cut_{tag} [list]")
            for (x0, y0, x1, y1) in cut_lines(chain, poly):
                m1 = emit(x0, y0, Z)
                m2 = emit(x1, y1, Z)
                A(f"*createlist nodes 1 ${m1} ${m2}")
                A("catch {*linecreatefromnodes 1 0 150 5 179}")
                A(f"lappend cut_{tag} [hm_entitymaxid lines]")

        A(f"if {{$sid_{tag} != 0}} {{")
        A(f"  set mb_{tag} [hm_entitymaxid surfaces]")
        A(f"  *createmark surfaces 1 $sid_{tag}")
        A(f"  *createmark lines 2 [lindex $cut_{tag} 0]")
        A(f"  foreach l [lrange $cut_{tag} 1 end] {{ *appendmark lines 2 $l }}")
        A("  set rc [catch {*surfacemarksplitwithlines 1 2 0 13 0} ec]")
        A(f'  log "{tag}: 切分 r=$rc e=$ec"')
        A(f"  set tgt [list $sid_{tag}]")
        A("  *createmark surfaces 1 all")
        A(f"  foreach s [hm_getmark surfaces 1] {{ if {{$s > $mb_{tag}}} {{ lappend tgt $s }} }}")
        A("  set ne 0")
        A("  foreach s $tgt {")
        A("    *createmark surfaces 1 $s")
        A(f"    catch {{*interactiveremeshsurf 1 {MS} 2 2 2 1 1}}")
        A("    catch {*automesh 0 2 2}")
        A("    catch {*storemeshtodatabase 1}")
        A('    *createmark elems 1 "by surface" $s')
        A("    set es [hm_getmark elems 1]")
        A("    incr ne [llength $es]")
        A("    foreach el $es {")
        A("      set nds [hm_getentityarray elems $el nodes]")
        A(f'      puts $fo "S tether $el $nds"')
        A("      foreach nd $nds { lappend allnodes $nd }")
        A("    }")
        A("  }")
        A(f'  log "{tag}: 面数=[llength $tgt] 单元=$ne"')
        A("}")

    A("")
    A("# ===== 导出节点 =====")
    A("foreach nd [lsort -integer -unique $allnodes] {")
    A('  puts $fo "N $nd [hm_nodevalue $nd]"')
    A("}")
    A("close $fo")
    A('log "TABS DONE"')
    A("close $rep")
    A('puts "__HW_DONE__"')

    open(a.out, "w", encoding="utf-8").write("\n".join(lines))
    print(f"写出 {a.out}: {len(mm)} 片, {nid[0]} 个几何节点")


if __name__ == "__main__":
    main()
