# -*- coding: utf-8 -*-
"""
shape_gate_v3.py — 自动化形状对比门禁 v3（交付门径）
======================================================
输入：lines_pts_all.txt(原始分组曲线采样) + loops_v3.json(正确闭合环) + 网格 txt
对每个 PID 检查：
  A 充满度   : 期望区域内采样点被本 PID 网格覆盖比例          >= 0.995
  B 面积自洽 : 网格面积 / 期望区域面积                       0.90~1.10
  C 边界贴合 : 原始曲线点 -> 网格自由边界边 距离
               - cmax   绝对最大距离                        <= CMAX_LIMIT (0.5mm)
               - cratio 弦误差自适应比 dist/(DP_EPS+L^2/8R) <= 1.0
  D 反向贴合 : 网格自由边界节点 -> 原始曲线线段 距离          <= 0.5mm
v3 修正：
  1) 洞贴合检查改用**原始线采样点**(HOLES 线号)，不用闭合环——
     洞环两端点在气腔主边界上(1.4mm缺口)，桥接弦横切急弯会产生 0.66mm 伪差
  2) C 增加弦误差自适应判据：网格直边替代圆弧的固有矢高 = L^2/(8R)，
     R 由该边两端点+边上最远曲线点三点外接圆估计（自洽，无曲率模型）
  3) C/D 均只用**自由边界边**（比"所有单元边"更严、更正确）
输出 PASS/FAIL + JSON + 叠加渲染。全自动，无人工干预。
"""
import json, math, re, sys
from collections import defaultdict, Counter

import os
P = (os.environ.get('WORKDIR') or './cab3').rstrip('/') + '/'
MESHFILE = sys.argv[1] if len(sys.argv) > 1 else P + 'cab3_step1_v3_mesh.txt'
CMAX_LIMIT = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
DP_EPS = 0.2          # Douglas-Peucker 简化容差 -> 折线与原始曲线的固有偏差
TOL = 0.8
EPS = 0.01
GRID = 2.0

HOLES = [[681, 682, 683, 684, 685], [698, 699, 700, 701, 702], [710, 711, 712, 713, 714]]

# ================= 1. 原始曲线 =================
raw = {}
for ln in open(P + 'lines_pts_all.txt', encoding='utf-8', errors='replace'):
    if '|' not in ln:
        continue
    h, rest = ln.split('|', 1)
    p = h.split()
    if len(p) < 7:
        continue
    try:
        lid = int(p[1]); comp = p[0]
        sp = (float(p[3]), float(p[4])); ep = (float(p[5]), float(p[6]))
    except Exception:
        continue
    pts = []
    for s in rest.strip().split(';'):
        s = s.strip()
        if not s:
            continue
        a = s.split()
        if len(a) >= 2:
            try:
                pts.append((float(a[0]), float(a[1])))
            except Exception:
                pass
    if pts:
        raw[lid] = (sp, ep, pts, comp)

V3 = json.load(open(P + 'loops_v3.json'))
loops_old = json.load(open(P + 'cab3_loops.json'))
straps = json.load(open(P + 'tether_straps.json'))


def curve_pts_of(line_ids):
    out = []
    for lid in line_ids:
        if lid in raw:
            out.extend(raw[lid][2])
    return out


def poly_area(ch):
    a = 0.0
    for i in range(len(ch)):
        x1, y1 = ch[i]; x2, y2 = ch[(i + 1) % len(ch)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def point_in_poly(pt, poly):
    x, y = pt; inside = False; n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xin:
                inside = not inside
    return inside


def poly_in_poly(inner, outer):
    cx = sum(p[0] for p in inner) / len(inner)
    cy = sum(p[1] for p in inner) / len(inner)
    return point_in_poly((cx, cy), outer)


def spans_of(poly, y):
    xs = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]


def merge(ss):
    ss = sorted(ss); out = []
    for a, b in ss:
        if out and a <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def diff(s1, s2):
    out = []
    for a, b in s1:
        cur = [(a, b)]
        for c, d in s2:
            nxt = []
            for ca, cb in cur:
                if d <= ca or c >= cb:
                    nxt.append((ca, cb)); continue
                if c > ca:
                    nxt.append((ca, min(c, cb)))
                if d < cb:
                    nxt.append((max(d, ca), cb))
            cur = nxt
        out += cur
    return out


def region_minus(base, holes):
    def spans(y):
        sb = merge(spans_of(base, y))
        for h in holes:
            sb = diff(sb, merge(spans_of(h, y)))
        return sb
    return spans


def sample_region(spans_fn, bbox, step=GRID):
    x0, x1, y0, y1 = bbox
    pts = []
    gy = y0 + step / 2
    while gy < y1:
        for a, b in spans_fn(gy):
            gx = a + step / 2
            while gx < b:
                pts.append((gx, gy)); gx += step
        gy += step
    return pts


# ================= 2. 环定义 =================
belt_poly = V3['belt']['pts']
cav_poly = V3['cavity']['pts']
hole_polys = [h['pts'] for h in V3['holes']]

rawl = {lid: (d[0], d[1], d[2]) for lid, d in raw.items()}


def orient_cyclic(order):
    seq = [(order[0], True)]
    prev_end = rawl[order[0]][1]
    for lid in order[1:]:
        sp, ep, _ = rawl[lid]
        d_sp = math.hypot(sp[0] - prev_end[0], sp[1] - prev_end[1])
        d_ep = math.hypot(ep[0] - prev_end[0], ep[1] - prev_end[1])
        if d_sp < 1e-6:
            fwd = True
        elif d_ep < 1e-6:
            fwd = False
        elif d_sp < TOL and d_ep < TOL:
            fwd = (d_sp <= d_ep)
        elif d_sp < TOL:
            fwd = True
        elif d_ep < TOL:
            fwd = False
        else:
            fwd = True
        seq.append((lid, fwd))
        prev_end = rawl[lid][1] if fwd else rawl[lid][0]
    return seq


def chain_from_seq(seq):
    chain = []
    for lid, fwd in seq:
        sp, ep, pts = rawl[lid]
        for pt in (pts if fwd else pts[::-1]):
            if chain and math.hypot(pt[0] - chain[-1][0], pt[1] - chain[-1][1]) < EPS:
                continue
            chain.append(pt)
    return chain


seam_chains = []
for sl in loops_old['seam']:
    ch = chain_from_seq(orient_cyclic(sl))
    if math.hypot(ch[-1][0] - ch[0][0], ch[-1][1] - ch[0][1]) < 1e-3:
        ch = ch[:-1]
    seam_chains.append(ch)

assert poly_in_poly(cav_poly, belt_poly), 'cavity 不在 belt 内!'
for i, s in enumerate(seam_chains):
    assert poly_in_poly(s, cav_poly), 'seam%d 不在 cavity 内!' % i
for i, h in enumerate(hole_polys):
    assert poly_in_poly(h, cav_poly), 'hole%d 不在 cavity 内!' % i
print('嵌套关系 OK: cavity in belt, seams/holes in cavity')


def poly_segs(poly):
    out = []
    n = len(poly)
    for i in range(n):
        out.append((poly[i], poly[(i + 1) % n]))
    return out


def drop_needles(ch, eps=0.05):
    """剔除'去而又回'的零面积针状突出: A ->(直线)-> A。
    链式追随时若下一条线起点与更早点重合会产生此伪迹(面积为零, 网格也会忽略它)。
    仅在 精确重复点 + 子路径共线 时剔除, 不影响真实几何。"""
    ch = list(ch)
    while True:
        first = {}
        hit = None
        for i, p in enumerate(ch):
            k = (round(p[0], 2), round(p[1], 2))
            if k in first:
                j = first[k]
                if j < i - 1:
                    sub = ch[j:i + 1]
                    d0 = (sub[1][0] - sub[0][0], sub[1][1] - sub[0][1])
                    L0 = math.hypot(*d0)
                    if L0 > 1e-9:
                        u = (d0[0] / L0, d0[1] / L0)
                        ok = True
                        for a, b in zip(sub, sub[1:]):
                            d = (b[0] - a[0], b[1] - a[1])
                            L = math.hypot(*d)
                            if L < 1e-9:
                                continue
                            # 同向或反向(往复)都算共线
                            if abs(abs(d[0] / L * u[0] + d[1] / L * u[1]) - 1.0) > 1e-3:
                                ok = False; break
                        if ok:
                            hit = (j, i)
                            break
            else:
                first[k] = i
        if hit is None:
            return ch
        j, i = hit
        del ch[j + 1:i + 1]


def comp_segs(line_ids):
    out = []
    for lid in line_ids:
        if lid not in raw:
            continue
        pts = raw[lid][2]
        for i in range(len(pts) - 1):
            out.append((pts[i], pts[i + 1]))
    return out


hole_segs = []
for h in hole_polys:
    hole_segs.extend(poly_segs(h))

RINGS = []
RINGS.append(dict(name='belt', pid=2, tag='belt', poly=belt_poly,
                  expected=region_minus(belt_poly, [cav_poly]),
                  area=poly_area(belt_poly) - poly_area(cav_poly),
                  cpts=curve_pts_of(V3['belt']['lines']),
                  bnd_tags=['belt', 'cav'],
                  dsegs=comp_segs(V3['belt']['lines']) + comp_segs(V3['cavity']['lines'])))
RINGS.append(dict(name='cavity', pid=3, tag='cav', poly=cav_poly,
                  expected=region_minus(cav_poly, seam_chains + hole_polys),
                  area=(poly_area(cav_poly) - sum(poly_area(s) for s in seam_chains)
                        - sum(poly_area(h) for h in hole_polys)),
                  cpts=curve_pts_of(V3['cavity']['lines']),
                  bnd_tags=['cav', 'belt'],
                  dsegs=(comp_segs(V3['cavity']['lines'])
                         + sum((comp_segs(s) for s in loops_old['seam']), [])
                         + hole_segs)))
for i, s in enumerate(seam_chains):
    RINGS.append(dict(name='seam%d' % i, pid=4, tag='seam%d' % i, poly=s,
                      expected=region_minus(s, []), area=poly_area(s),
                      cpts=curve_pts_of(loops_old['seam'][i]),
                      bnd_tags=['seam%d' % i],
                      dsegs=comp_segs(loops_old['seam'][i]) + comp_segs(V3['cavity']['lines'])))
for i, S in enumerate(straps):
    ch = drop_needles([tuple(p) for p in S['chain']])
    RINGS.append(dict(name='tether%d' % i, pid=5, tag='tether%d' % i, poly=ch,
                      expected=region_minus(ch, []), area=poly_area(ch),
                      cpts=ch, bnd_tags=['tether%d' % i], dsegs=poly_segs(ch)))

# ================= 3. 网格 =================
def load_mesh(fn, tagmap):
    out = {}
    nodes_all = {}
    for ln in open(fn, encoding='utf-8', errors='replace'):
        p = ln.split()
        if not p:
            continue
        if p[0] == 'S':
            t = tagmap(p[1])
            if t is None:
                continue
            nds = [int(x) for x in p[3:]]
            out.setdefault(t, ({}, []))[1].append((int(p[2]), nds))
        elif p[0] == 'N':
            m = re.search(r'\{([^}]*)\}', ln)
            if m:
                v = m.group(1).split()
                nodes_all[int(p[1])] = (float(v[0]), float(v[1]))
            elif len(p) >= 4:
                nodes_all[int(p[1])] = (float(p[2]), float(p[3]))
    for t in out:
        need = {x for _, nds in out[t][1] for x in nds}
        out[t] = ({n: nodes_all[n] for n in need if n in nodes_all}, out[t][1])
    return out


m1 = load_mesh(MESHFILE,
               lambda t: {'seam0': 'seam0', 'seam1': 'seam1', 'seam2': 'seam2',
                          'cav': 'cav', 'belt': 'belt'}.get(t))
try:
    m2 = load_mesh(P + 'tether_mesh.txt', lambda t: t if t.startswith('tether') else None)
except Exception:
    m2 = {}
MESH = dict(m1); MESH.update(m2)
for tag, (nd, el) in MESH.items():
    print("mesh %-8s nodes=%4d elems=%4d" % (tag, len(nd), len(el)))

# ================= 4. 几何工具 =================
def dist_pt_seg(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-18:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def circumradius(a, b, c):
    ax, ay = a; bx, by = b; cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return 1e9
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    return math.hypot(ux - ax, uy - ay)


class SegGrid:
    def __init__(self, segs, cell=8.0):
        self.segs = segs; self.cell = cell
        self.grid = defaultdict(list)
        for i, (a, b) in enumerate(segs):
            xs = [a[0], b[0]]; ys = [a[1], b[1]]
            for ix in range(int(min(xs) // cell), int(max(xs) // cell) + 1):
                for iy in range(int(min(ys) // cell), int(max(ys) // cell) + 1):
                    self.grid[(ix, iy)].append(i)

    def nearest(self, p, cap=60.0):
        cx, cy = int(p[0] // self.cell), int(p[1] // self.cell)
        r = 1
        best = 1e9
        while r * self.cell <= cap + self.cell:
            for ix in range(cx - r, cx + r + 1):
                for iy in range(cy - r, cy + r + 1):
                    for i in self.grid.get((ix, iy), ()):
                        a, b = self.segs[i]
                        d = dist_pt_seg(p, a, b)
                        if d < best:
                            best = d
            if best <= (r - 1) * self.cell:
                break
            r += 1
        return best


class PtGrid:
    """曲线点空间索引"""
    def __init__(self, pts, cell=4.0):
        self.pts = pts; self.cell = cell
        self.grid = defaultdict(list)
        for i, p in enumerate(pts):
            self.grid[(int(p[0] // cell), int(p[1] // cell))].append(i)

    def near(self, p, radius):
        r = int(radius // self.cell) + 1
        cx, cy = int(p[0] // self.cell), int(p[1] // self.cell)
        out = []
        for ix in range(cx - r, cx + r + 1):
            for iy in range(cy - r, cy + r + 1):
                for i in self.grid.get((ix, iy), ()):
                    q = self.pts[i]
                    if (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 <= radius * radius:
                        out.append(q)
        return out


def tri_of(nds, nodes):
    pts = [nodes[n] for n in nds if n in nodes]
    if len(pts) < 3:
        return []
    if len(pts) == 4:
        return [(pts[0], pts[1], pts[2]), (pts[0], pts[2], pts[3])]
    return [(pts[0], pts[1], pts[2])]


def pt_in_tri(p, a, b, c):
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1 = sign(p, a, b); d2 = sign(p, b, c); d3 = sign(p, c, a)
    neg = (d1 <= 0) or (d2 <= 0) or (d3 <= 0)
    pos = (d1 >= 0) or (d2 >= 0) or (d3 >= 0)
    return not (neg and pos)


class MeshIdx:
    def __init__(self, nodes, elems, cell=6.0):
        self.tris = []; self.nodes = nodes
        self.grid = defaultdict(list); self.cell = cell
        for eid, nds in elems:
            for t in tri_of(nds, nodes):
                self.tris.append(t)
                xs = [p[0] for p in t]; ys = [p[1] for p in t]
                for i in range(int(min(xs) // cell), int(max(xs) // cell) + 1):
                    for j in range(int(min(ys) // cell), int(max(ys) // cell) + 1):
                        self.grid[(i, j)].append(len(self.tris) - 1)

    def covered(self, p, tol=0.05):
        ci, cj = int(p[0] // self.cell), int(p[1] // self.cell)
        cand = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                cand.extend(self.grid.get((ci + di, cj + dj), []))
        for ti in cand:
            if pt_in_tri(p, *self.tris[ti]):
                return True
        if tol > 0:
            for ti in cand:
                t = self.tris[ti]
                for i in range(3):
                    if dist_pt_seg(p, t[i], t[(i + 1) % 3]) <= tol:
                        return True
        return False


def boundary_edges(nodes, elems):
    c = Counter()
    for eid, nds in elems:
        k = len(nds)
        for i in range(k):
            a, b = nds[i], nds[(i + 1) % k]
            c[(min(a, b), max(a, b))] += 1
    return [e for e, v in c.items() if v == 1]


IDX = {tag: MeshIdx(nd, el) for tag, (nd, el) in MESH.items()}
FREE = {tag: [(nd[a], nd[b]) for a, b in boundary_edges(nd, el)]
        for tag, (nd, el) in MESH.items()}
for tag, es in FREE.items():
    print("free bnd edges %-8s = %d" % (tag, len(es)))

# 全局曲线点云（用于弦误差自适应）
ALL_CURVE = []
for R in RINGS:
    ALL_CURVE.extend(R['cpts'])
for hl in HOLES:
    ALL_CURVE.extend(curve_pts_of(hl))
seen = set(); AC = []
for p in ALL_CURVE:
    k = (round(p[0], 2), round(p[1], 2))
    if k in seen:
        continue
    seen.add(k); AC.append(p)
PG = PtGrid(AC)
print("原始曲线点(去重):", len(AC))


def chord_allowed(edge, pg):
    """网格边 edge 替代圆弧的固有矢高 L^2/(8R)，R 由边两端点+边上最远曲线点估计"""
    a, b = edge
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 1e-6:
        return DP_EPS
    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    cand = []
    for q in pg.near((mx, my), L * 0.75 + 1.0):
        ax, ay = a; bx, by = b; px, py = q
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = ((px - ax) * dx + (py - ay) * dy) / L2
        if -0.02 <= t <= 1.02 and dist_pt_seg(q, a, b) < 3.0:
            cand.append(q)
    if len(cand) < 3:
        return DP_EPS
    qmax = max(cand, key=lambda q: dist_pt_seg(q, a, b))
    if dist_pt_seg(qmax, a, b) < 0.05:
        return DP_EPS
    R = circumradius(a, qmax, b)
    if R > 1e6:
        return DP_EPS
    return DP_EPS + L * L / (8.0 * R)


# ================= 5. 检查 =================
report = []
print("\n" + "=" * 118)
print("%-10s %9s %9s %7s %8s %8s %8s %8s %8s %7s" % (
    "ring", "期望面积", "网格面积", "面积比", "A充满", "C绝对", "C自适应", "D反向", "", "判定"))
print("-" * 118)
fails = []


def self_int(ch):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    n = len(ch); bad = 0
    for a in range(n):
        for b in range(a + 2, n):
            if a == 0 and b == n - 1:
                continue
            p1, p2 = ch[a], ch[(a + 1) % n]; p3, p4 = ch[b], ch[(b + 1) % n]
            o1, o2, o3, o4 = o(p1, p2, p3), o(p1, p2, p4), o(p3, p4, p1), o(p3, p4, p2)
            if o1 * o2 < 0 and o3 * o4 < 0:
                bad += 1
    return bad


for R in RINGS:
    nm = R['name']; tag = R['tag']
    idx = IDX.get(tag)
    si = self_int(R['poly'])
    if si:
        print("%-10s 环自交 %d 处" % (nm, si)); fails.append('%s:selfint%d' % (nm, si)); continue
    if idx is None or not idx.tris:
        print("%-10s NO MESH" % nm); fails.append(nm + ':no-mesh'); continue
    mesh_area = 0.0
    for t in idx.tris:
        mesh_area += abs((t[1][0] - t[0][0]) * (t[2][1] - t[0][1]) -
                         (t[2][0] - t[0][0]) * (t[1][1] - t[0][1])) / 2.0
    xs = [p[0] for p in R['poly']]; ys = [p[1] for p in R['poly']]
    pts = sample_region(R['expected'], (min(xs), max(xs), min(ys), max(ys)))
    cov = sum(1 for p in pts if idx.covered(p, tol=0.05))
    cover = cov / len(pts) if pts else 0.0
    # C 边界贴合（自由边界边）
    bedges = []
    for t in R['bnd_tags']:
        bedges.extend(FREE.get(t, []))
    cmax = 0.0; cworst = None; cratio = 0.0; rworst = None
    for p in R['cpts']:
        best = 1e9; be = None
        for a, b in bedges:
            d = dist_pt_seg(p, a, b)
            if d < best:
                best = d; be = (a, b)
            if best < 1e-4:
                break
        if best > cmax:
            cmax = best; cworst = p
        al = chord_allowed(be, PG)
        if al > 1e-9 and best / al > cratio:
            cratio = best / al; rworst = p
    # D 反向贴合
    bnodes = set()
    for a, b in boundary_edges(*MESH[tag]):
        bnodes.add(a); bnodes.add(b)
    sg = SegGrid(R['dsegs'])
    dmax = 0.0; dworst = None
    nd0 = MESH[tag][0]
    for n in bnodes:
        if n not in nd0:
            continue
        best = sg.nearest(nd0[n])
        if best > dmax:
            dmax = best; dworst = nd0[n]
    ratio = mesh_area / R['area'] if R['area'] > 0 else 0.0
    ok = (cover >= 0.995) and (0.90 <= ratio <= 1.10) and \
         (cmax <= CMAX_LIMIT) and (cratio <= 1.0) and (dmax <= 0.5)
    print("%-10s %9.0f %9.0f %7.4f %8.4f %8.3f %8.3f %8.3f %8s %7s" % (
        nm, R['area'], mesh_area, ratio, cover, cmax, cratio, dmax, '', 'PASS' if ok else 'FAIL'))
    report.append(dict(name=nm, area=R['area'], mesh=mesh_area, ratio=ratio,
                       cover=cover, cmax=cmax, cratio=cratio, dmax=dmax, pass_=ok,
                       cworst=cworst, rworst=rworst, dworst=dworst))
    if not ok:
        fails.append('%s: cov=%.4f ratio=%.3f C=%.3f Cr=%.3f D=%.3f' % (
            nm, cover, ratio, cmax, cratio, dmax))

# 洞贴合: 用原始线采样点(不含桥接弦)
if 'cav' in FREE:
    hmax = 0.0; hworst = None; hratio = 0.0
    for hi, hl in enumerate(HOLES):
        for p in curve_pts_of(hl):
            best = 1e9; be = None
            for a, b in FREE['cav']:
                d = dist_pt_seg(p, a, b)
                if d < best:
                    best = d; be = (a, b)
                if best < 1e-4:
                    break
            if best > hmax:
                hmax = best; hworst = p
            al = chord_allowed(be, PG)
            if al > 1e-9 and best / al > hratio:
                hratio = best / al
    ok = (hmax <= CMAX_LIMIT) and (hratio <= 1.0)
    print("%-10s %9s %9s %7s %8s %8.3f %8.3f %8s %8s %7s" % (
        'holes(3)', '-', '-', '-', '-', hmax, hratio, '-', '', 'PASS' if ok else 'FAIL'))
    report.append(dict(name='holes', cmax=hmax, cratio=hratio, pass_=ok, cworst=hworst))
    if not ok:
        fails.append('holes: C=%.3f Cr=%.3f' % (hmax, hratio))

print("-" * 118)
print("ALL PASS" if not fails else "FAIL(%d): %s" % (len(fails), fails))
json.dump(report, open(P + 'shape_gate_v3_report.json', 'w'), indent=1)
print("saved shape_gate_v3_report.json")
import sys as _sys
_sys.exit(0 if not fails else 1)
