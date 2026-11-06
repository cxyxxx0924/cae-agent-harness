# -*- coding: utf-8 -*-
"""blmesh 前置 washer vs 后插排 washer —— 定量并排对比
输入两个 K:  old = cab2_curtain_airbag.k (automesh + add_washer W=2.5)
             new = cab2_curtain_airbag_bl.k (blmesh_2d2 4.0 前置)
输出: 单元数 / 三角形 / 质量分布 / 最短边 / washer 带宽分布 / 界面共节点
"""
import collections, math, os, sys

OLD = "E:/work/AI_CAB/onekey/cab2_curtain_airbag.k"
NEW = "E:/work/AI_CAB/onekey/cab2_curtain_airbag_bl.k"
REF = "E:/work/AI_CAB/ref-Output/Model_update/5P-BAG_004.key"


def read_k(path):
    nodes, els = {}, []
    sec = None
    with open(path, encoding="ascii", errors="ignore") as f:
        for line in f:
            if line.startswith("*"):
                sec = line.strip().upper()
                continue
            if not line.strip() or line.lstrip().startswith("$"):
                continue
            f8 = line.split(",")
            if sec == "*NODE":
                if len(f8) >= 4:
                    nodes[int(f8[0])] = (float(f8[1]), float(f8[2]), float(f8[3]))
            elif sec == "*ELEMENT_SHELL":
                v = [int(x) for x in f8 if x.strip()]
                if len(v) >= 5:
                    els.append((v[1], [x for x in v[2:] if x > 0]))
    return nodes, els


def read_ref(path):
    nodes, els = {}, []
    with open(path, encoding="ascii", errors="ignore") as f:
        for line in f:
            if len(line) < 56:
                continue
            try:
                nid = int(line[0:8])
            except ValueError:
                continue
            try:
                x, y, z = float(line[8:24]), float(line[24:40]), float(line[40:56])
            except ValueError:
                continue
            if nid in nodes:
                continue
            nodes[nid] = (x, y, z)
    # 单元行: 8 列整数字段, 第 2 列 = pid
    with open(path, encoding="ascii", errors="ignore") as f:
        for line in f:
            if len(line) < 40 or line.startswith("*") or line.startswith("$"):
                continue
            toks = line.split()
            if len(toks) not in (5, 6):
                continue
            try:
                v = [int(t) for t in toks]
            except ValueError:
                continue
            if v[0] not in nodes and all(t in nodes for t in v[2:]):
                els.append((v[1], v[2:]))
    return nodes, els


def metrics(nodes, els, pid=None):
    """返回 dict: 单元数/三角/最短边/最小角/Jacobian 近似/长宽比"""
    nq = nt = 0
    amin = 1e9
    emin = 1e9
    jac = []
    asp = []
    for p, ns in els:
        if pid is not None and p != pid:
            continue
        pts = [nodes[n] for n in ns if n in nodes]
        if len(pts) < 3:
            continue
        if len(ns) == 3:
            nt += 1
        else:
            nq += 1
        m = len(pts)
        for i in range(m):
            a, b = pts[i], pts[(i + 1) % m]
            d = math.dist(a, b)
            emin = min(emin, d)
        # 最小内角 (只算 XY 投影, 板件)
        for i in range(m):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % m]
            u = (b[0] - a[0], b[1] - a[1])
            v = (c[0] - b[0], c[1] - b[1])
            nu = math.hypot(*u); nv = math.hypot(*v)
            if nu < 1e-12 or nv < 1e-12:
                amin = 0.0
                continue
            cosv = max(-1, min(1, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
            amin = min(amin, math.degrees(math.acos(cosv)))
        if m == 4:
            # 长宽比: 最大边/最小边
            L = [math.dist(pts[i], pts[(i + 1) % m]) for i in range(m)]
            asp.append(max(L) / max(min(L), 1e-9))
            # Jacobian: 对边中点的两条向量叉积 / 边长平方积 (0..1)
            mx1 = ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
            mx2 = ((pts[2][0] + pts[3][0]) / 2, (pts[2][1] + pts[3][1]) / 2)
            my1 = ((pts[1][0] + pts[2][0]) / 2, (pts[1][1] + pts[2][1]) / 2)
            my2 = ((pts[3][0] + pts[0][0]) / 2, (pts[3][1] + pts[0][1]) / 2)
            ax = (mx2[0] - mx1[0], mx2[1] - mx1[1])
            ay = (my2[0] - my1[0], my2[1] - my1[1])
            cr = abs(ax[0] * ay[1] - ax[1] * ay[0])
            den = math.hypot(*ax) * math.hypot(*ay)
            jac.append(cr / den if den > 1e-12 else 0.0)
    return dict(nq=nq, nt=nt, emin=emin, amin=amin, jac=jac, asp=asp)


def pct(a, q):
    if not a:
        return float("nan")
    a = sorted(a)
    return a[min(len(a) - 1, int(q * len(a)))]


def band(nodes, els, pid=3):
    """washer 带宽: 气腔 Z=0 节点 -> 最近 Z!=0 节点的平面距离 (参考模型的量法)"""
    z0, zi = [], []
    for n, (x, y, z) in nodes.items():
        if abs(z) < 1e-9:
            z0.append(n)
        elif abs(abs(z) - 0.5) < 0.4:
            zi.append(n)
    used = set()
    for p, ns in els:
        if p == pid:
            used.update(ns)
    z0 = [n for n in z0 if n in used]
    Q = 1.0 / 6.0
    grid = collections.defaultdict(list)
    for n in zi:
        x, y, _ = nodes[n]
        grid[(int(x * Q), int(y * Q))].append(n)
    out = []
    for n in z0:
        x, y, _ = nodes[n]
        gx, gy = int(x * Q), int(y * Q)
        best = None
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                for h in grid.get((gx + dx, gy + dy), ()):
                    d = math.hypot(nodes[h][0] - x, nodes[h][1] - y)
                    if [n, h] and d > 1e-9 and (best is None or d < best):
                        best = d
        if best is not None:
            out.append(best)
    return out


def iface(nodes, els):
    m = collections.defaultdict(set)
    for p, ns in els:
        m[p].update(ns)
    return m


def main():
    res = {}
    for name, path in (("old", OLD), ("new", NEW)):
        nodes, els = read_k(path)
        m = metrics(nodes, els)
        mb = metrics(nodes, els, pid=3)
        bd = band(nodes, els)
        im = iface(nodes, els)
        res[name] = (nodes, els, m, mb, bd, im)
        print(f"\n===== {name} =====  ({os.path.basename(path)})")
        print(f"  节点 {len(nodes)}  单元 {len(els)}")
        print(f"  三角 {m['nt']} ({100.0*m['nt']/len(els):.2f}%)  最短边 {m['emin']:.3f}mm  最小内角 {m['amin']:.1f}deg")
        print(f"  Jacobian  p5={pct(m['jac'],0.05):.3f} p50={pct(m['jac'],0.5):.3f}  <0.6 占 {100.0*sum(1 for j in m['jac'] if j<0.6)/max(1,len(m['jac'])):.2f}%")
        print(f"  aspect    p50={pct(m['asp'],0.5):.2f} p95={pct(m['asp'],0.95):.2f}  >5 占 {100.0*sum(1 for j in m['asp'] if j>5)/max(1,len(m['asp'])):.2f}%")
        print(f"  [PID3] 单元 {mb['nq']+mb['nt']} 三角 {mb['nt']} 最短边 {mb['emin']:.3f} 最小角 {mb['amin']:.1f}")
        if bd:
            print(f"  washer 带宽 (Z0->最近Z0.5 平面距离): n={len(bd)} p10={pct(bd,0.10):.2f} p50={pct(bd,0.50):.2f} p90={pct(bd,0.90):.2f} min={min(bd):.2f} max={max(bd):.2f}")
        print(f"  界面: cav&belt={len(im[3]&im[2])} cav&seam={len(im[3]&im[4])} tab&belt={len(im[5]&im[2])} tab&cav={len(im[5]&im[3])}")

    if os.path.exists(REF):
        nodes, els = read_ref(REF)
        m = metrics(nodes, els)
        print(f"\n===== REF 5P-BAG_004 =====  节点 {len(nodes)} 单元 {len(els)}")
        print(f"  三角 {m['nt']} ({100.0*m['nt']/max(1,len(els)):.2f}%)  最短边 {m['emin']:.3f}  最小角 {m['amin']:.1f}")
        print(f"  Jacobian p5={pct(m['jac'],0.05):.3f} p50={pct(m['jac'],0.5):.3f}  <0.6 占 {100.0*sum(1 for j in m['jac'] if j<0.6)/max(1,len(m['jac'])):.2f}%")
        print(f"  aspect   p50={pct(m['asp'],0.5):.2f} p95={pct(m['asp'],0.95):.2f}")


if __name__ == "__main__":
    main()
