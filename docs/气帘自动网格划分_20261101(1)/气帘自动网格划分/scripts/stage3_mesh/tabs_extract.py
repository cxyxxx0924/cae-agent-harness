"""拉带外轮廓提取 v2 — 干净重写版
249 条碎线 → 空间聚类成区域 → 每区域 端点焊接+悬空端补线 → polygonize 全部环
BOSS: 主环=下片(矩形), 次大相邻上方环=上片(凸台帽檐) —— 双环法, 与 CAD 折弯线天然一致
CURVE/HORIZ: 主环=整体外轮廓
输出: out/tabs_polys.json
"""
import json, math, collections
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

# ---------- 读线 ----------
lines = {}
for raw in open("out/tabs_lines_pts.txt", encoding="utf-8"):
    if not raw.startswith("L "):
        continue
    head, _, tail = raw.strip().partition("|")
    f = head.split()
    lines[int(f[1])] = [tuple(map(float, s.split())) for s in tail.strip().split(";") if s.strip()]

LLEN = {lid: sum(math.dist(pts[i], pts[i+1]) for i in range(len(pts)-1))
        for lid, pts in lines.items()}

def densify(pts, step=2.0):
    out = [pts[0]]
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        d = math.dist(a, b)
        n = max(1, int(d / step))
        for k in range(1, n + 1):
            out.append((a[0] + (b[0]-a[0])*k/n, a[1] + (b[1]-a[1])*k/n))
    return out

dense = {lid: densify(pts, 2.0) for lid, pts in lines.items()}

# ---------- 1. 聚类成区域 ----------
parent = {lid: lid for lid in lines}
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[ra] = rb
cell_lines = collections.defaultdict(list)
for lid, pts in dense.items():
    for q in pts:
        cell_lines[(round(q[0] / 8), round(q[1] / 8))].append(lid)
for ls in cell_lines.values():
    for l in ls[1:]:
        union(ls[0], l)
groups = collections.defaultdict(list)
for lid in lines:
    groups[find(lid)].append(lid)
regions = []
for g in groups.values():
    max_len = max(LLEN[l] for l in g)
    if len(g) < 4 and max_len < 50:
        continue
    pts = [q for l in g for q in lines[l]]
    xs = [q[0] for q in pts]; zs = [q[1] for q in pts]
    r = {"lines": sorted(g), "x": (min(xs), max(xs)), "z": (min(zs), max(zs)),
         "cx": sum(xs)/len(xs), "cz": sum(zs)/len(zs)}
    if r["z"][0] < 1000:
        r["kind"] = "HORIZ"
    elif r["cx"] < 1200 and (r["x"][1]-r["x"][0]) > 100:
        r["kind"] = "CURVE"
    elif r["z"][0] > 1050:
        r["kind"] = "BOSS"
    else:
        r["kind"] = "CURVE"
    regions.append(r)
regions.sort(key=lambda r: ({"BOSS": 0, "CURVE": 1, "HORIZ": 2}[r["kind"]], r["cx"]))
print(f"区域数: {len(regions)}")
for i, r in enumerate(regions):
    print(f"  R{i} {r['kind']:5s} {len(r['lines']):3d}线 x[{r['x'][0]:.0f},{r['x'][1]:.0f}] z[{r['z'][0]:.0f},{r['z'][1]:.0f}]")

# ---------- 2. 环提取: 焊接 + 补线 + polygonize ----------
def region_rings(line_ids, bbox_area):
    ends = []
    for l in line_ids:
        p = lines[l]
        ends.append(p[0]); ends.append(p[-1])
    grid = collections.defaultdict(list)
    for i, q in enumerate(ends):
        grid[(round(q[0] / 1.0), round(q[1] / 1.0))].append(i)
    rep = list(range(len(ends)))
    def find2(x):
        while rep[x] != x: rep[x] = rep[rep[x]]; x = rep[x]
        return x
    for idxs in grid.values():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                if math.dist(ends[i], ends[j]) < 2.6:
                    ri, rj = find2(i), find2(j)
                    if ri != rj: rep[ri] = rj
    ge = collections.defaultdict(list)
    for i in range(len(ends)):
        ge[find2(i)].append(i)
    weld = {rr: (sum(ends[i][0] for i in ix)/len(ix), sum(ends[i][1] for i in ix)/len(ix))
            for rr, ix in ge.items()}
    endmap = {(round(q[0], 9), round(q[1], 9)): find2(i) for i, q in enumerate(ends)}
    def w(p):
        k = (round(p[0], 9), round(p[1], 9))
        return weld[endmap[k]] if k in endmap else p
    segs = []
    for l in line_ids:
        p = densify(lines[l], 2.0)
        if len(p) >= 2:
            p2 = [w(p[0])] + p[1:-1] + [w(p[-1])]
            for i in range(len(p2) - 1):
                if math.dist(p2[i], p2[i + 1]) > 1e-9:
                    segs.append((p2[i], p2[i + 1]))
    if not segs:
        return []
    best_rings = []
    for _it in range(8):
        ml = unary_union([LineString(q) for q in segs])
        polys = list(polygonize(ml))
        if polys:
            best = max(polys, key=lambda q: q.area)
            best_rings = sorted(polys, key=lambda q: -q.area)
            if best.area >= 0.22 * bbox_area:
                return best_rings
        cnt = collections.Counter()
        for a, b in segs:
            cnt[(round(a[0], 2), round(a[1], 2))] += 1
            cnt[(round(b[0], 2), round(b[1], 2))] += 1
        loose = [(x, y) for (x, y), c in cnt.items() if c == 1]
        if len(loose) < 2:
            break
        cand = None
        for i in range(len(loose)):
            for j in range(i + 1, len(loose)):
                d = math.dist(loose[i], loose[j])
                if cand is None or d < cand[0]:
                    cand = (d, loose[i], loose[j])
        if cand is None or cand[0] > 15:
            break
        segs.append((cand[1], cand[2]))
    return best_rings

# ---------- 3. 每区域: 主环 + 上片(BOSS 双环) ----------
from shapely.geometry import Polygon as _PGM

def boss_split(r):
    """肩部折弯分位 (用户 2026-10-21 确认):
    上片 = 凸台柱 + 穹顶 (凸台状), 下片 = 矩形, 分界 = 两侧膝点连线 (上下片共节点边)
    返回 (dn_ring, up_ring) 或 None
    膝点 = 外轮廓线上 |x-cx| 跨越 (矩形半宽-8) 的转变顶点对中靠柱侧者, z 在上半区
    """
    lb = max(r["lines"], key=lambda l: LLEN[l])
    bp = lines[lb][:]
    closed = bp[0] == bp[-1]
    if closed:
        bp = bp[:-1]
    xs = [q[0] for q in bp]; zs = [q[1] for q in bp]
    cx = sum(xs) / len(xs); zmin = min(zs); H = max(zs) - zmin
    if H < 60:
        return None
    rect_half = max(abs(q[0] - cx) for q in bp if q[1] < zmin + 0.3 * H)
    thr = rect_half - 8
    n = len(bp); knees = []
    for i in range(n):
        a = bp[i]; b = bp[(i + 1) % n]
        oa = abs(a[0] - cx); ob = abs(b[0] - cx)
        if (oa - thr) * (ob - thr) < 0 and min(a[1], b[1]) > zmin + 0.35 * H:
            knees.append((i if oa < ob else (i + 1) % n, a if oa < ob else b))
    if len(knees) != 2:
        return None
    (i1, k1), (i2, k2) = knees
    if i1 > i2:
        (i1, k1), (i2, k2) = (i2, k2), (i1, k1)
    pA = bp[i1:i2 + 1]                 # k1 顺向到 k2
    pB = (bp[i2:] + bp[:i1 + 1])       # k2 环回到 k1 (开线时经两端点)
    if max(q[1] for q in pA) > max(q[1] for q in pB):
        top, bot = pA, pB
    else:
        top, bot = pB, pA
    if min(q[1] for q in top) < min(q[1] for q in bot):
        return None                    # 路径交叉, 分位失败
    dn_ring = bot[:]
    up_ring = top[:]
    # 上片并入穹顶 (z 最高且明显高出外轮廓的线)
    zmax_b = max(q[1] for q in bp)
    dome = None
    for l in r["lines"]:
        if l == lb or LLEN[l] < 50:
            continue
        zm = max(q[1] for q in lines[l])
        if zm > zmax_b + 5 and (dome is None or zm > max(q[1] for q in lines[dome])):
            dome = l
    dome_ok = False
    if dome is not None:
        dp = lines[dome][:]
        if dp[0] == dp[-1]:
            dp = dp[:-1]
        dbot = min(q[1] for q in dp)
        ztop = max(q[1] for q in up_ring)
        if ztop < dbot - 0.5:
            # 柱顶低于穹顶底 (R4 型, 中隔锯齿带): 柱向上延伸到穹顶底使其连通
            up_ring = [(q[0], dbot) if abs(q[1] - ztop) < 0.6 else q for q in up_ring]
        col = _PGM(up_ring + [up_ring[0]]).buffer(0)
        dom = _PGM(dp + [dp[0]]).buffer(0)
        if not col.is_empty and not dom.is_empty:
            u = col.union(dom)
            if u.geom_type == "MultiPolygon":
                u = max(u.geoms, key=lambda g: g.area)
            # 穹顶需"实质性"接入: 面积明显增大(>=基柱帽 1.4 倍)且顶部高出 -> 否则视为穹顶被拆段
            if u.area >= col.area * 1.4 and max(q[1] for q in u.exterior.coords) > ztop + 5:
                er = list(u.exterior.coords)
                if er[0] == er[-1]:
                    er = er[:-1]
                up_ring = er
                dome_ok = True
    if not dome_ok:
        # 兜底 (用户 2026-10-21): 穹顶被拆成多段短线(BOSS3 型), 单条穹顶线退化/接入失败
        #   -> 取全部高出基柱顶的源点凸包, 与基柱帽合并 (凸包近似圆顶, 保住上半部分不丢失)
        hi_pts = [q for l in r["lines"] if l != lb and max(q[1] for q in lines[l]) > zmax_b + 2
                  for q in lines[l]]
        if hi_pts:
            from shapely.geometry import MultiPoint
            hull = MultiPoint(hi_pts).convex_hull
            col = _PGM(up_ring + [up_ring[0]]).buffer(0)
            if not col.is_empty:
                u = col.union(hull)
                if u.geom_type == "MultiPolygon":
                    u = max(u.geoms, key=lambda g: g.area)
                er = list(u.exterior.coords)
                if er[0] == er[-1]:
                    er = er[:-1]
                up_ring = er
    return dn_ring, up_ring

results = []
for i, r in enumerate(regions):
    bw = r["x"][1] - r["x"][0]; bh = r["z"][1] - r["z"][0]
    dn_up = boss_split(r) if r["kind"] == "BOSS" else None
    if dn_up is not None:
        dn_ring, up_ring = dn_up
        main = _PGM(dn_ring + [dn_ring[0]]).buffer(0)
        up_poly = _PGM(up_ring + [up_ring[0]]).buffer(0)
        if main.area >= 100 and not up_poly.is_empty:
            r["area"] = main.area
            r["poly"] = dn_ring
            r["_poly"] = main
            r["dn"] = dn_ring
            r["up"] = up_ring
            print(f"  R{i} boss c={r['cx']:.0f} 肩部分位: 下片{len(dn_ring)}点 {main.area:.0f}mm2 + 上片{len(up_ring)}点 {up_poly.area:.0f}mm2")
            results.append(r)
            continue
        print(f"  R{i} boss c={r['cx']:.0f} 肩部分位失败 (主环 {main.area:.0f}mm2) -> 走旧路径")
    rings = region_rings(r["lines"], bw * bh)
    if not rings:
        print(f"  R{i} {r['kind']}: 无闭环!")
        continue
    main = rings[0]
    if main.area < 100:
        print(f"  R{i} {r['kind']} 主环 {main.area:.0f}mm2 <100 -> 细节, 剔除")
        continue
    if r["kind"] == "HORIZ":
        # 用户 2026-10-21 (左区长拉带): 啮合点在拉带末端, 粘合线垂直布带长度方向
        #   -> 参考模型 R8(PID8) 实证: 拉带体右端是【竖直边】, 末端 3 个共节点成竖直粘合线
        # 几何构造 (CAD L305 实证 + 参考模型实证):
        #   ① 主轮廓线 = 区域最长线 (L305: x946.9-1105.1, z947.4-956.9, 闭合成环)
        #      = 干净拉带体; CAD 右端是斜切倒角 -> 末端 10mm 带补直成竖直边(垂直布带 X 向)
        #   ② 其余密集装饰线 (扇形接口 L195-304 + 锯齿 L308 + 缝线 L306/307 + 挂刺 L309):
        #      缓冲并集 -> 填洞 -> 开运算(±2 净零): 4mm 厚装饰带(锯齿/缝线/挂刺)被腐蚀掉,
        #      只剩实体扇形接口 (x908-960)
        #      铁律: 开运算必须 ±2 净零; 旧代码 +2/-2.5/+2.5 净 +2, 整体外鼓 2mm(带宽 9.5->13.5)
        #   ③ ① ∪ ②: 扇形接口与拉带体在 x947-959 重叠, 并集自然连通
        #   ④ 主轮廓构造失败(最长线不成环/面积异常) -> 回退旧缓冲路径
        from shapely.geometry import Polygon as _PGS
        def _solid(g):
            if g.geom_type == "Polygon":
                return _PGS(g.exterior)
            return unary_union([_PGS(p.exterior) for p in g.geoms])
        lb = max(r["lines"], key=lambda l: LLEN[l])
        bp = lines[lb][:]
        if bp[0] == bp[-1]:
            bp = bp[:-1]
        bp = bp + [bp[0]]
        strap = _PGS(bp).buffer(0)
        main_new = None
        if (not strap.is_empty and strap.geom_type == "Polygon" and strap.is_valid
                and strap.area > 500 and (strap.bounds[2] - strap.bounds[0]) > 100):
            sx0, sz0, sx1, sz1 = strap.bounds
            # 右端斜切 -> 竖直末端边 (末端边竖直 = 粘合线垂直布带长度方向)
            strap_v = strap.union(_PGS([(sx1 - 10, sz0), (sx1, sz0),
                                        (sx1, sz1), (sx1 - 10, sz1)]).buffer(0))
            u = unary_union([LineString(densify(lines[l], 4.0))
                             for l in r["lines"] if l != lb]).buffer(2.0)
            u = _solid(u)                      # 填洞 (扇形接口内部空腔变实心)
            p2 = u.buffer(-2.0)                # 开运算 ±2 净零: 去 4mm 厚装饰带, 不鼓量
            if p2.geom_type == "MultiPolygon":
                p2 = max(p2.geoms, key=lambda g: g.area)
            if not p2.is_empty and p2.area > 300:
                main_new = strap_v.union(p2)
                if main_new.geom_type == "MultiPolygon":
                    main_new = max(main_new.geoms, key=lambda g: g.area)
                print(f"  R{i} HORIZ 主轮廓构造: 拉带体{strap_v.area:.0f}(末端竖边 x={sx1:.1f})"
                      f" + 扇形接口{p2.area:.0f} = {main_new.area:.0f}mm2")
            else:
                main_new = strap_v
                print(f"  R{i} HORIZ 主轮廓构造: 仅拉带体{main_new.area:.0f}"
                      f"(末端竖边 x={sx1:.1f}), 扇形接口过小剔除")
        if main_new is not None:
            main = main_new
        else:
            # 兜底: 全线缓冲并集取外环 (旧路径)
            u = unary_union([LineString(densify(lines[l], 4.0)) for l in r["lines"]]).buffer(2.0)
            u = _solid(u)
            p2 = u.buffer(-2.5).buffer(2.5)
            if p2.geom_type == "MultiPolygon":
                p2 = max(p2.geoms, key=lambda g: g.area)
            if not p2.is_empty and p2.area > 0.6 * u.area:
                main = p2
                print(f"  R{i} HORIZ 缓冲并集外环(兜底路径): {main.area:.0f}mm2")
    r["area"] = main.area
    # HORIZ(左长拉带): 扇形接口是 110 条密集扇贝弧的包络近似, 其 <3mm 微锯齿在 5mm 网格下
    #   必然产出 <3mm 单元边(公司规范 2.2 硬条款: 最小单元尺寸 >3mm) -> 容差放到 2.0
    #   (连接关键几何不受影响: 末端竖边/带体直边都是 90 度角, simplify 不移动顶点)
    simp = main.simplify(2.0 if r["kind"] == "HORIZ" else 0.4)
    ring = list(simp.exterior.coords)
    if ring[0] == ring[-1]: ring = ring[:-1]
    r["poly"] = ring
    r["_poly"] = main
    # 上片: 次大相邻上方环 (BOSS 帽檐)
    up = None
    mx0, mx1 = min(q[0] for q in ring), max(q[0] for q in ring)
    my0 = main.representative_point().y
    for cand_p in rings[1:]:
        if not (200 < cand_p.area < 1000):
            continue
        cc = cand_p.representative_point()
        if cc.y > my0 + 2 and mx0 - 5 <= cc.x <= mx1 + 5:
            if up is None or cand_p.area > up.area:
                up = cand_p
    if r["kind"] == "BOSS" and up is None:
        # 兜底: 帽檐带 U 形线 (全部点在下片顶边之上, 两端开口大) 闭合底边成环
        # 典型: R4 的 L129, 底边缺口 46mm 超过常规桥接上限 15mm
        from shapely.geometry import Polygon as _PG2
        dn_top = max(q[1] for q in ring)
        best = None
        for l in r["lines"]:
            p = lines[l]
            if LLEN[l] < 30:
                continue
            if min(q[1] for q in p) < dn_top - 3:
                continue
            gap = math.dist(p[0], p[-1])
            if gap < 20 or gap > 90:
                continue
            pg = _PG2(p + [p[0]]).buffer(0)
            if pg.is_empty or pg.geom_type != "Polygon":
                continue
            if not (200 < pg.area < 1200):
                continue
            if best is None or pg.area > best.area:
                best = pg
        if best is not None:
            up = best
            print(f"  R{i} boss 帽檐兜底: U形线闭合 {up.area:.0f}mm2")
    if r["kind"] == "BOSS" and up is not None:
        ur = list(up.simplify(0.4).exterior.coords)
        if ur[0] == ur[-1]: ur = ur[:-1]
        r["up"] = ur
        r["dn"] = ring
        print(f"  R{i} boss c={r['cx']:.0f} 双环: 下片{len(ring)}点 {main.area:.0f}mm2 + 上片{len(ur)}点 {up.area:.0f}mm2")
    else:
        if r["kind"] == "BOSS":
            print(f"  R{i} boss c={r['cx']:.0f} 无独立帽檐环 -> 整体单片")
        else:
            print(f"  R{i} {r['kind']} c={r['cx']:.0f} 单环 {len(ring)}点 {main.area:.0f}mm2")
    results.append(r)

# ---------- 4. 内环剔除 + 输出 ----------
kept = []
for r in results:
    c = r["_poly"].representative_point()
    inside = any(o is not r and o["_poly"].contains(c) for o in results)
    if inside:
        print(f"  剔除内环: c=({r['cx']:.0f},{r['cz']:.0f}) 面积 {r['area']:.0f}")
        continue
    kept.append(r)
results = kept
out = []
for r in results:
    rec = {"kind": r["kind"], "cx": r["cx"], "cz": r["cz"], "area": r["area"],
           "outer": r["poly"], "lines": r["lines"]}
    if "up" in r:
        rec["up"] = r["up"]; rec["dn"] = r["dn"]
    out.append(rec)
json.dump(out, open("out/tabs_polys.json", "w"), indent=1)
print(f"\n输出 out/tabs_polys.json: {len(out)} 区域")
