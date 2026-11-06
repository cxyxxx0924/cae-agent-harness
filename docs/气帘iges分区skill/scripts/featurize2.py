# -*- coding: utf-8 -*-
"""特征 v2：面向「气帘视觉/功能/连贯性」语义的跨图不变特征集。

设计原则（与 v1 的关键差异）
--------------------------------
v1 的问题（LODO 实测）：用了 cx_n/cy_n/sin_ang/cos_ang 等**绝对位置**、用**凸包距离**当"离边界多远"、
线段长度按**最大线长**归一。结果：同图 100% 拟合、跨图掉到 70~82%（不如"全猜 TETHER"）。
原因：① 位置特征让树背布局；② 细长气帘上 82% 的线都贴凸包，凸包距离无判别力；③ 尺度归一分母受个别超长线支配。

v2 换成三条**有物理含义、可跨图比较**的量：
1. **轮廓内向深度 depth**：把全部线栅格化 → 形态学闭运算 → 填洞，得到"布片实体轮廓"；
   用距离变换取每条线各采样点的内向深度。布带环贴轮廓 → depth≈0；气腔环内缩 → 小正值；
   缝线在腔体深处 → 大正值。彻底替代凸包距离。
2. **局部密集度 dens**：某线中点邻域（半径按图幅固定比例）内其它线的条数/总长。
   充气口/安装件是一堆极短线段挤在一起 → dens 极高；长轮廓线 dens 低。
3. **尺度无关线长**：len/中位线长、len/图幅对角线。中位数比最大值稳健得多。

另外：闭合性、切向连续邻居数、长宽比、符号簇规模（只把"短线"互相焊接，得到符号级连通块）。
不保留任何绝对位置特征。

接口与 v1 一致：compute_features(workdir) -> (meta, feats)；feats[lid] 为 dict。
"""
import os, json, math
from collections import defaultdict, deque

import numpy as np
from scipy import ndimage

WELD_FRAC = 0.004          # 端点焊接容差 = 图幅对角线 × 该比例
LONG_FRAC = 0.03           # "长线"阈值（相对中位线长）
RASTER_N = 1200            # 栅格长边像素
DENS_RADIUS_FRAC = 0.02    # 密集度邻域半径（相对栅格长边）


# ---------------------------------------------------------------- 基础几何
def load_lines(workdir):
    out = os.path.join(workdir, "out")
    lines = {}
    with open(os.path.join(out, "lines_pts.txt"), encoding="utf-8", errors="ignore") as fh:
        for ln in fh:
            if not ln.startswith("L "):
                continue
            head, _, tail = ln.strip().partition("|")
            f = head.split()
            try:
                lid = int(f[1])
            except Exception:
                continue
            pts = []
            for s in tail.strip().split(";"):
                c = s.split()
                if len(c) >= 3:
                    try:
                        pts.append((float(c[0]), float(c[1]), float(c[2])))
                    except ValueError:
                        pass
            if len(pts) >= 2:
                lines[lid] = {"pts": pts, "s": pts[0], "e": pts[-1]}
    return lines


def detect_plane(lines):
    zs = [p[2] for d in lines.values() for p in d["pts"]]
    ys = [p[1] for d in lines.values() for p in d["pts"]]
    return (max(zs) - min(zs)) > 1.0 and (max(ys) - min(ys)) < 1.0


def project(use_z, p):
    return (p[0], p[2]) if use_z else (p[0], p[1])


def seglen(P):
    return sum(math.hypot(P[i + 1][0] - P[i][0], P[i + 1][1] - P[i][1]) for i in range(len(P) - 1))


def tangent(P, at_start):
    if at_start:
        a, b = P[0], P[min(3, len(P) - 1)]
    else:
        a, b = P[max(0, len(P) - 4)], P[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-9 else (0.0, 0.0)


# ---------------------------------------------------------------- 轮廓栅格
def build_silhouette(P2, N, bbox, pad=0.02):
    """返回 (sil, dt_in, dt_out, to_px)；sil 为"布片实体"布尔图。"""
    x0, x1, y0, y1 = bbox
    dx, dy = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    D = math.hypot(dx, dy)
    m = pad * D
    x0, x1, y0, y1 = x0 - m, x1 + m, y0 - m, y1 + m
    dx, dy = x1 - x0, y1 - y0
    sc = (N - 1) / max(dx, dy)

    def to_px(p):
        return ((p[0] - x0) * sc, (p[1] - y0) * sc)

    img = np.zeros((N, N), dtype=bool)
    for P in P2.values():
        for i in range(len(P) - 1):
            ax, ay = to_px(P[i]); bx, by = to_px(P[i + 1])
            n = int(max(abs(bx - ax), abs(by - ay))) + 1
            xs = np.linspace(ax, bx, n).round().astype(int)
            ys = np.linspace(ay, by, n).round().astype(int)
            ok = (xs >= 0) & (xs < N) & (ys >= 0) & (ys < N)
            img[ys[ok], xs[ok]] = True

    r = max(3, int(round(0.006 * N)))
    dil = ndimage.binary_dilation(img, iterations=r)
    filled = ndimage.binary_fill_holes(dil)
    sil = ndimage.binary_erosion(filled, iterations=r)
    if sil.sum() < 0.02 * N * N:          # 轮廓闭合失败 → 退化用膨胀版
        sil = filled
    dt_in = ndimage.distance_transform_edt(sil).astype(np.float32)
    dt_out = ndimage.distance_transform_edt(~sil).astype(np.float32)
    return sil, dt_in, dt_out, to_px


def sample_depth(dt_in, dt_out, to_px, P, N):
    """沿折线采样，返回 (内向深度列表, 外向距离列表)，单位 px。"""
    ins, outs = [], []
    for i in range(len(P) - 1):
        ax, ay = to_px(P[i]); bx, by = to_px(P[i + 1])
        n = int(max(abs(bx - ax), abs(by - ay))) + 1
        for t in np.linspace(0, 1, min(n, 40)):
            x = ax + (bx - ax) * t; y = ay + (by - ay) * t
            xi = int(round(x)); yi = int(round(y))
            if 0 <= xi < N and 0 <= yi < N:
                ins.append(float(dt_in[yi, xi])); outs.append(float(dt_out[yi, xi]))
    return ins, outs


# ---------------------------------------------------------------- 主流程
def compute_features(workdir, verbose=False):
    lines = load_lines(workdir)
    use_z = detect_plane(lines)
    P2 = {lid: [project(use_z, p) for p in d["pts"]] for lid, d in lines.items()}
    ids = sorted(P2)

    allp = [p for P in P2.values() for p in P]
    x0, x1 = min(p[0] for p in allp), max(p[0] for p in allp)
    y0, y1 = min(p[1] for p in allp), max(p[1] for p in allp)
    D = math.hypot(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0

    L = {lid: seglen(P2[lid]) for lid in ids}
    lens = sorted(L.values())
    med_len = lens[len(lens) // 2] if lens else 1.0
    med_len = max(med_len, 1e-9)
    WELD = max(WELD_FRAC * D, 1e-6)

    sil, dt_in, dt_out, to_px = build_silhouette(P2, RASTER_N, (x0, x1, y0, y1))

    # ---- 端点焊接 + 切线连续性
    nodes = {}
    def gn(p):
        for k, v in nodes.items():
            if abs(k[0] - p[0]) < WELD and abs(k[1] - p[1]) < WELD:
                return v
        v = len(nodes); nodes[p] = v; return v

    ep = {}
    for lid in ids:
        ep[(lid, "s")] = gn(P2[lid][0]); ep[(lid, "e")] = gn(P2[lid][-1])
    node_lines = defaultdict(list)
    for (lid, e), nid in ep.items():
        node_lines[nid].append((lid, e))

    def dot_tan(Pa, sa, Pb, sb):
        ta = tangent(Pa, sa == "s"); tb = tangent(Pb, sb == "s")
        return (-ta[0] * tb[0] - ta[1] * tb[1]) if sa == sb else (ta[0] * tb[0] + ta[1] * tb[1])

    n_tan = {}
    for lid in ids:
        c = 0
        for e in ("s", "e"):
            for (l2, e2) in node_lines[ep[(lid, e)]]:
                if l2 == lid:
                    continue
                if dot_tan(P2[lid], e, P2[l2], e2) > 0.7:
                    c += 1
        n_tan[lid] = c

    # ---- 切向连续链（chain）：把"顺滑接续"的线段串成链，链的规模/闭合性/跨度
    #      → 直接量化"这是不是一个环"，解决 BELT(长环) vs TETHER(局部) 、SEAM(小闭环) vs CAVITY(长轮廓)
    pair = {}
    for node, lst in node_lines.items():
        if len(lst) < 2:
            continue
        cand = []
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                l1, e1 = lst[i]; l2, e2 = lst[j]
                d = dot_tan(P2[l1], e1, P2[l2], e2)
                if d > 0.7:
                    cand.append((d, l1, e1, l2, e2))
        cand.sort(reverse=True)
        used = set()
        for d, l1, e1, l2, e2 in cand:
            if (l1, e1) in used or (l2, e2) in used:
                continue
            used.add((l1, e1)); used.add((l2, e2))
            pair[(l1, e1)] = (l2, e2); pair[(l2, e2)] = (l1, e1)

    chain_of, chains = {}, []
    for lid in ids:
        for e_in in ("s", "e"):
            if lid in chain_of:
                break
            chain, closed = [lid], False
            cur_l, cur_e = lid, e_in
            for _ in range(len(ids) + 5):
                e_out = "e" if cur_e == "s" else "s"
                if (cur_l, e_out) not in pair:
                    break
                nl, ne = pair[(cur_l, e_out)]
                if nl == lid:
                    closed = True
                    break
                if nl in chain:
                    break
                chain.append(nl)
                cur_l, cur_e = nl, ne
            cid = len(chains)
            chains.append({"lines": chain, "closed": closed})
            for l in chain:
                chain_of.setdefault(l, cid)

    ch_feat = {}
    for cid, ch in enumerate(chains):
        ls = ch["lines"]
        xs = [p[0] for l in ls for p in P2[l]]
        ys = [p[1] for l in ls for p in P2[l]]
        ext = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / D
        tl = sum(L[l] for l in ls) / D
        rads = [math.hypot(sum(p[0] for p in P2[l]) / len(P2[l]) - cx,
                           sum(p[1] for p in P2[l]) / len(P2[l]) - cy) / (0.5 * D) for l in ls]
        angs = [math.degrees(math.atan2(sum(p[1] for p in P2[l]) / len(P2[l]) - cy,
                                        sum(p[0] for p in P2[l]) / len(P2[l]) - cx)) for l in ls]
        nb = int(360 / 10)
        hit = [0] * nb
        for a in angs:
            hit[int((a + 180) // 10) % nb] = 1
        best = cur = 0
        for i in range(2 * nb):
            if hit[i % nb]:
                cur += 1; best = max(best, cur)
            else:
                cur = 0
        span = min(best, nb) * 10
        ch_feat[cid] = {
            "ch_n": len(ls), "ch_len": tl, "ch_ext": ext,
            "ch_closed": 1 if ch["closed"] else 0,
            "ch_span": span / 360.0,
            "ch_rad": float(np.median(rads)) if rads else 0.0,
        }

    # ---- 符号簇：只把"短线"(< 3×中位线长)互相焊接，得到硬件符号连通块
    short = [l for l in ids if L[l] < 3.0 * med_len]
    par = {l: l for l in short}
    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]; a = par[a]
        return a
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb
    nid2shorts = defaultdict(list)
    for l in short:
        for e in ("s", "e"):
            nid2shorts[ep[(l, e)]].append(l)
    for nid, ls in nid2shorts.items():
        for i in range(1, len(ls)):
            union(ls[0], ls[i])
    clust = defaultdict(list)
    for l in short:
        clust[find(l)].append(l)
    cl_of, cl_size, cl_diag = {}, {}, {}
    for root, ls in clust.items():
        xs = [p[0] for l in ls for p in P2[l]]
        ys = [p[1] for l in ls for p in P2[l]]
        dg = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / D
        for l in ls:
            cl_of[l] = root; cl_size[l] = len(ls); cl_diag[l] = dg

    # ---- 网格加速：密集度
    mids = np.array([[sum(p[0] for p in P2[l]) / len(P2[l]),
                      sum(p[1] for p in P2[l]) / len(P2[l])] for l in ids])
    mid_lid = ids
    r_dens = DENS_RADIUS_FRAC * D
    from scipy.spatial import cKDTree
    tree = cKDTree(mids)
    dens_cnt = {}
    dens_len = {}
    for i, l in enumerate(mid_lid):
        nb = tree.query_ball_point(mids[i], r_dens)
        dens_cnt[l] = len(nb) - 1
        dens_len[l] = sum(L[mid_lid[j]] for j in nb if j != i) / max(L[l], 1e-9)

    # ---- 角度覆盖 / 径向序列（供参考，不主导）
    # 先算每线深度（链级聚合需要）
    dep = {}
    for lid in ids:
        ins, outs = sample_depth(dt_in, dt_out, to_px, P2[lid], RASTER_N)
        ins_n = [v / RASTER_N for v in ins] or [0.0]
        dep[lid] = (min(ins_n), float(np.median(ins_n)), max(ins_n),
                    (min(outs) / RASTER_N) if outs else 0.0)

    # 链级深度 / 链是否贴轮廓
    ch_dep = {}
    for cid, ch in enumerate(chains):
        ds = [dep[l][1] for l in ch["lines"] if l in dep]
        ch_dep[cid] = float(np.median(ds)) if ds else 0.0

    feats = {}
    for lid in ids:
        P = P2[lid]
        dep_min, dep_med, dep_max, out_n = dep[lid]

        xs = [p[0] for p in P]; ys = [p[1] for p in P]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        rad = math.hypot(mx - cx, my - cy) / (0.5 * D)      # 0..1，相对中心
        closed = 1 if math.hypot(P[0][0] - P[-1][0], P[0][1] - P[-1][1]) < WELD else 0

        cid = chain_of.get(lid, -1)
        cf = ch_feat.get(cid, {"ch_n": 1, "ch_len": L[lid] / D, "ch_ext": 0.0,
                              "ch_closed": 0, "ch_span": 0.0, "ch_rad": rad})
        feats[lid] = {
            # —— 轮廓深度（核心：布带/气腔/缝线分层）——
            "dep_min": dep_min, "dep_med": dep_med, "dep_max": dep_max, "out_min": out_n,
            # —— 尺度（中位线长归一，跨图可比）——
            "len_med": L[lid] / med_len, "len_diag": L[lid] / D,
            # —— 密集度（核心：硬件符号簇）——
            "dens_cnt": dens_cnt[lid], "log_dens_len": math.log10(1.0 + dens_len[lid]),
            # —— 符号簇规模 ——
            "cl_size": cl_size.get(lid, 0), "cl_diag": cl_diag.get(lid, 0.0),
            # —— 切向链（核心：环的结构信息）——
            "ch_n": cf["ch_n"], "ch_len": cf["ch_len"], "ch_ext": cf["ch_ext"],
            "ch_closed": cf["ch_closed"], "ch_span": cf["ch_span"],
            "ch_rad": cf["ch_rad"], "ch_dep": ch_dep.get(cid, 0.0),
            # —— 拓扑/形态 ——
            "closed": closed, "n_tan": n_tan[lid],
            "aspect": math.log10(max(w, h) / max(1e-9, min(w, h)) + 1.0),
            "rad": rad,
            "w_diag": w / D, "h_diag": h / D,
            "npts": len(P),
        }

    # ---- 图内相对量：消除"图与图之间尺度/画法不同"造成的阈值漂移
    #      例：同一张图上 SEAM 的链深度总比 CAVITY 深，但不同图整体深度水平不同
    from scipy.stats import rankdata
    for key in ("dep_min", "dep_med", "len_med", "dens_cnt", "ch_len", "ch_dep", "ch_ext"):
        v = np.array([feats[l][key] for l in ids], float)
        r = rankdata(v) / float(len(v))
        for i, l in enumerate(ids):
            feats[l]["rk_" + key] = float(r[i])
    lm = np.array([feats[l]["len_med"] for l in ids], float)
    dm = np.array([feats[l]["dep_min"] for l in ids], float)
    base = float(np.median(dm[lm >= np.median(lm)])) or 1e-9
    for i, l in enumerate(ids):
        feats[l]["dep_rel"] = float(dm[i] / max(base, 1e-9))

    meta = {"use_z": use_z, "n_lines": len(ids), "bbox": [x0, x1, y0, y1],
            "diag": D, "med_len": med_len, "weld": WELD, "raster": RASTER_N,
            "feature_order": list(next(iter(feats.values())).keys())}
    if verbose:
        print("[featurize2] %s  plane=%s  lines=%d  diag=%.1f  med_len=%.2f  sil_px=%d" % (
            workdir, "X-Z" if use_z else "X-Y", len(ids), D, med_len, int(sil.sum())))
    return meta, feats


def main():
    wd = os.path.expanduser(os.sys.argv[1]).rstrip("/\\")
    meta, feats = compute_features(wd, verbose=True)
    out = os.path.join(wd, "out")
    os.makedirs(out, exist_ok=True)
    json.dump({"__meta__": meta, "features": {str(k): v for k, v in feats.items()}},
              open(os.path.join(out, "features2.json"), "w"))
    print("wrote features2.json with", len(feats), "lines")


if __name__ == "__main__":
    main()
