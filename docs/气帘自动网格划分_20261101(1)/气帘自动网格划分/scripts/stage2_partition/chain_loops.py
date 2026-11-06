#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chain_loops.py — 通用「线→闭环」链接器（与项目/分区无关）
================================================================
输入: export_lines_pts.tcl 产出的 lines_pts.txt
     每行: <TAG> <line_id> <len> <sp_x> <sp_y> <sp_z> <ep_x> <ep_y> <ep_z> | "x y z";...

输出: loops.json
     { "<TAG>": { "loops":[{"lids":[..],"area":..,"perim":..,"bbox":[x0,x1,y0,y1],
                            "npts":..,"closed":true,"self":false}, ...],
                  "opens":[{"lids":[..],"L":..,"why":"..."}] },
        "__meta__": {...} }

算法
----
1. 端点按 TOL 距离聚成"节点"(空间哈希, O(n))。
2. 每 TAG 内建无向图: 节点=端点cluster, 边=线。度!=2 的节点是分叉/端点。
3. 沿图走链, 每次在候选线里选**方向最平滑**的那条(点积最大), 与"直线延伸"一致;
   回到起始节点即闭环。
4. 闭环按面积降序。开放链单独归类并给出原因(用于诊断缺口/未搭接)。

坐标系
------
PROJ 指定用哪两个轴做面积/长度计算(默认取点数波动最小的两轴 → 自动识别厚度轴)。
显式 --plane xy|xz|yz 可覆盖。

为什么要这一步
--------------
HyperMesh 的 `*surfacesplineonlinesloop` 要一组"首尾相接"的线。CAD 导入后线是散乱的,
且一条 comp 里常有多条互不相连的闭环(4 个缝线、N 个拉带)。自动成环后:
  · 每个闭环单独建面 → 不再依赖 comp 恰好只有 1 个环
  · 环的 lids 直接喂给 Tcl → 不再需要硬编码 line id
用法
----
  python chain_loops.py out/lines_pts.txt --out out/loops.json
  python chain_loops.py out/lines_pts.txt --tol 0.5 --plane xy
"""
import argparse, json, math
from collections import defaultdict


# ---------------------------------------------------------------- 解析
def parse_lines(path):
    """-> {lid: dict(tag, sp, ep, pts, L)}"""
    raw = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            if "|" not in ln:
                continue
            h, rest = ln.split("|", 1)
            p = h.split()
            if len(p) < 7:
                continue
            try:
                tag, lid = p[0], int(p[1])
                L = float(p[2]) if p[2] != "-" else 0.0
                sp = (float(p[3]), float(p[4]), float(p[5]))
                ep = (float(p[6]), float(p[7]), float(p[8]))
            except Exception:
                continue
            pts = []
            for s in rest.strip().split(";"):
                a = s.split()
                if len(a) >= 3:
                    try:
                        pts.append((float(a[0]), float(a[1]), float(a[2])))
                    except Exception:
                        pass
            if not pts:
                pts = [sp, ep]
            raw[lid] = dict(tag=tag, sp=sp, ep=ep, pts=pts, L=L)
    return raw


# ---------------------------------------------------------------- 投影
def pick_axes(raw):
    """厚度轴 = 点数分布最集中的那根轴(所有线都接近同一平面)。返回 (i,j, 轴名)。"""
    ext = []
    for k in range(3):
        vals = [q[k] for d in raw.values() for q in d["pts"]]
        ext.append((max(vals) - min(vals)) if vals else 0.0)
    thin = min(range(3), key=lambda k: ext[k])
    pair = [k for k in range(3) if k != thin]
    name = "".join("xyz"[k] for k in pair)
    return pair[0], pair[1], name, ext


# ---------------------------------------------------------------- 端点聚类
class Cluster:
    __slots__ = ("pts", "grid", "tol", "cell")

    def __init__(self, tol):
        self.pts, self.grid, self.tol, self.cell = [], defaultdict(list), tol, tol * 2

    def get(self, p):
        k = (int(math.floor(p[0] / self.cell)), int(math.floor(p[1] / self.cell)))
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for ci in self.grid.get((k[0] + di, k[1] + dj), []):
                    q = self.pts[ci]
                    if math.hypot(p[0] - q[0], p[1] - q[1]) <= self.tol and \
                       abs(p[2] - q[2]) <= self.tol:
                        return ci
        ci = len(self.pts)
        self.pts.append(p)
        self.grid[k].append(ci)
        return ci


def dir_at(raw, end_c, lid, cluster, n=6):
    """线在 cluster 处的"离开方向"(单位向量, 3D)。"""
    d = raw[lid]["pts"]
    a, b = end_c[lid]
    if a == cluster:
        seg = d[:min(n, len(d))]
        v = (seg[-1][0] - seg[0][0], seg[-1][1] - seg[0][1], seg[-1][2] - seg[0][2])
    else:
        seg = d[-min(n, len(d)):]
        v = (seg[0][0] - seg[-1][0], seg[0][1] - seg[-1][1], seg[0][2] - seg[-1][2])
    nn = math.sqrt(sum(x * x for x in v))
    return tuple(x / nn for x in v) if nn > 1e-12 else (0.0, 0.0, 0.0)


def poly_area(pts, ia, ib):
    A = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i][ia], pts[i][ib]
        x2, y2 = pts[(i + 1) % len(pts)][ia], pts[(i + 1) % len(pts)][ib]
        A += x1 * y2 - x2 * y1
    return abs(A) / 2.0


def stitch(loop_lids, raw, end_c):
    """把环内各线的点串按走向拼成一条闭合折线。"""
    pts = []
    for lid in loop_lids:
        seg = raw[lid]["pts"]
        if not pts:
            pts.extend(seg)
            continue
        d0 = math.dist((pts[-1][0], pts[-1][1], pts[-1][2]), seg[0])
        d1 = math.dist((pts[-1][0], pts[-1][1], pts[-1][2]), seg[-1])
        if d1 < d0:
            seg = seg[::-1]
        pts.extend(seg[1:])
    return pts


# ---------------------------------------------------------------- 主逻辑
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lines", help="lines_pts.txt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tol", type=float, default=0.8, help="端点合并容差 mm")
    ap.add_argument("--plane", default=None, choices=["auto", "xy", "xz", "yz"])
    ap.add_argument("--min-area", type=float, default=1.0, help="小于此面积不算闭环")
    ap.add_argument("--min-len", type=float, default=1.0, help="短于此长度的线忽略")
    a = ap.parse_args()

    raw = parse_lines(a.lines)
    if not raw:
        raise SystemExit("没有解析到线，检查 lines_pts.txt 格式")
    if a.min_len > 0:
        raw = {k: v for k, v in raw.items() if v["L"] >= a.min_len or len(v["pts"]) > 2}

    if a.plane in (None, "auto"):
        ia, ib, pname, ext = pick_axes(raw)
    else:
        ia, ib = "xyz".index(a.plane[0]), "xyz".index(a.plane[1])
        _, _, _, ext = pick_axes(raw)
        pname = a.plane

    bycomp = defaultdict(list)
    for lid, d in raw.items():
        bycomp[d["tag"]].append(lid)
    for c in bycomp:
        bycomp[c].sort()

    cl = Cluster(a.tol)
    end_c = {}
    for lid, d in raw.items():
        end_c[lid] = (cl.get(d["sp"]), cl.get(d["ep"]))

    results = {}
    for tag in sorted(bycomp):
        lids = bycomp[tag]
        adj = defaultdict(list)
        deg = defaultdict(int)
        for lid in lids:
            x, y = end_c[lid]
            adj[x].append(lid)
            adj[y].append(lid)
            deg[x] += 1
            deg[y] += 1
        used, loops, opens = set(), [], []
        selfclosed = [l for l in lids if end_c[l][0] == end_c[l][1]]
        for lid0 in lids:
            if lid0 in used:
                continue
            a0, b0 = end_c[lid0]
            if a0 == b0:
                used.add(lid0)
                loops.append(dict(lids=[lid0], self=True))
                continue
            chain, used, origin = [lid0], used | {lid0}, a0
            cur, cur_cluster = lid0, b0
            closed = False
            for _ in range(20000):
                if cur_cluster == origin and len(chain) > 1:
                    closed = True
                    break
                cands = [l for l in adj[cur_cluster] if l != cur and l not in used]
                if not cands:
                    break
                vin = dir_at(raw, end_c, cur, cur_cluster)
                best, bs = None, -2.0
                for l in cands:
                    vout = dir_at(raw, end_c, l, cur_cluster)
                    s = sum(p * q for p, q in zip(vin, vout))
                    if s > bs:
                        bs, best = s, l
                used.add(best)
                chain.append(best)
                x, y = end_c[best]
                cur_cluster = y if x == cur_cluster else x
                cur = best
            (loops if closed else opens).append(dict(lids=chain, self=False))

        out_loops = []
        for r in loops:
            pts = stitch(r["lids"], raw, end_c)
            if len(pts) < 3:
                continue
            ar = poly_area(pts, ia, ib)
            if ar < a.min_area:
                continue
            xs = [q[ia] for q in pts]
            ys = [q[ib] for q in pts]
            out_loops.append(dict(
                lids=r["lids"], self=r["self"],
                area=round(ar, 2),
                perim=round(sum(raw[l]["L"] for l in r["lids"]), 2),
                bbox=[round(min(xs), 2), round(max(xs), 2), round(min(ys), 2), round(max(ys), 2)],
                npts=len(pts)))
        out_loops.sort(key=lambda d: -d["area"])

        out_opens = []
        for o in opens:
            L = sum(raw[l]["L"] for l in o["lids"])
            ends = [end_c[o["lids"][0]][0], end_c[o["lids"][-1]][1]]
            gap = math.dist(cl.pts[ends[0]], cl.pts[ends[1]])
            out_opens.append(dict(lids=o["lids"], L=round(L, 2),
                                  gap=round(gap, 2),
                                  degree=["%d" % deg[e] for e in end_c[o["lids"][0]]]))
        out_opens.sort(key=lambda d: -d["L"])
        results[tag] = dict(loops=out_loops, opens=out_opens,
                            nlines=len(lids),
                            total_len=round(sum(raw[l]["L"] for l in lids), 2))

    results["__meta__"] = dict(source=a.lines, tol=a.tol, plane=pname,
                               extent=[round(x, 2) for x in ext],
                               thin_axis="xyz"[min(range(3), key=lambda k: ext[k])])

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)

    print(f"=== chain_loops  TOL={a.tol}mm  平面={pname}  厚度轴={results['__meta__']['thin_axis']} ===")
    for tag in sorted(k for k in results if k != "__meta__"):
        r = results[tag]
        print(f"\n[{tag}] lines={r['nlines']} 总长={r['total_len']:.0f}mm  "
              f"闭环={len(r['loops'])} 开链={len(r['opens'])}")
        for i, lp in enumerate(r["loops"][:12]):
            print(f"   loop{i:02d} nl={len(lp['lids']):3d} area={lp['area']:11.1f} "
                  f"perim={lp['perim']:9.1f} bbox=[{lp['bbox'][0]:8.1f},{lp['bbox'][1]:8.1f}]"
                  f"[{lp['bbox'][2]:8.1f},{lp['bbox'][3]:8.1f}]")
        if len(r["loops"]) > 12:
            print(f"   ... 其余 {len(r['loops'])-12} 个")
        for o in r["opens"][:5]:
            print(f"   OPEN nl={len(o['lids']):3d} L={o['L']:9.1f} 缺口={o['gap']:6.2f}mm "
                  f"lids={o['lids'][:6]}")
    print(f"\n-> {a.out}")


if __name__ == "__main__":
    main()
