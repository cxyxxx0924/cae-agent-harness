# -*- coding: utf-8 -*-
"""
在气腔单面网格边界内侧插入一圈 washer 窄带 (cab2)
=================================================================
动机
  气腔是 Z±0.5 双层膜, 到布带/缝线/颈部收口处必须合拢到 Z0。
  原来这个 0.5mm 的收拢完全压在一排 5mm 单元里, 充气鼓起时该排剧烈剪切/翻折。
  参考人工做法: 在边界内侧加一圈窄单元(washer), 让过渡集中在窄带上。

做法 (纯 2D, 不改 HM 拓扑)
  1) 自由边 = 只属于 1 个单元的边 -> 边界节点 B
  2) 每条自由边的内法向 = 由该边所属单元的 3/4 个节点重心确定 (指向气腔内部),
     不需要给边界排环序, 也不依赖 CW/CCW
  3) 节点法向 = 其所属自由边法向的均值 + miter 长度补偿 (1/cos), 限幅
  4) B' = B + w * n
  5) 原第一排单元把边界顶点换成 B' 顶点 (使其收缩到 w 处)
  6) B 与 B' 之间填四边形条带 = washer 单元
  输出新的 mesh txt, 由 assemble 组装 (B 收 Z0, B' 天然落 ±0.5)
"""
import collections
import json
import math
import statistics
import sys

SRC = "cab2_step1_mesh.txt"
DST = "cab2_step1_washer.txt"
REPORT = "washer_report.json"

W = 2.5             # washer 宽度 mm (参考模型实测收拢带 4.0mm/内部 5mm; 取 5mm 均分避免挤出退化排)
NID0 = 50_000_000   # 新节点 id 起点
MITRE_MAX = 2.5     # miter 限幅 (倍数 W)
MIN_WASHER_AREA = 0.05   # mm^2, 小于此的条带视为退化丢弃


def load(path):
    nodes = {}
    elems = collections.defaultdict(list)     # tag -> [(eid, [n...])]
    for line in open(path, encoding="utf-8"):
        f = line.replace("{", " ").replace("}", " ").split()
        if not f:
            continue
        if f[0] == "N":
            nodes[int(f[1])] = (float(f[2]), float(f[3]))
        elif f[0] == "S":
            elems[f[1]].append((int(f[2]), [int(x) for x in f[3:]]))
    return nodes, elems


def sarea(pts):
    s = 0.0
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        s += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return s / 2


def main():
    nodes, elems = load(SRC)
    cav = elems["cav"]
    print(f"读入 {SRC}: 节点 {len(nodes)}  cav 单元 {len(cav)}")

    # ---- 1. 自由边 ----
    ec = collections.defaultdict(list)        # edge -> [单元下标]
    for i, (eid, ns) in enumerate(cav):
        u = list(dict.fromkeys(ns))
        for k in range(len(u)):
            a, b = u[k], u[(k + 1) % len(u)]
            ec[(min(a, b), max(a, b))].append(i)
    free = [e for e, v in ec.items() if len(v) == 1]
    print(f"自由边 {len(free)}  -> 边界节点 {len({n for e in free for n in e})}")

    # ---- 2. 边级内法向 ----
    edge_n = {}
    for e in free:
        a, b = e
        ei = ec[e][0]
        ns = list(dict.fromkeys(cav[ei][1]))
        gx = sum(nodes[n][0] for n in ns) / len(ns)
        gy = sum(nodes[n][1] for n in ns) / len(ns)
        ax, ay = nodes[a]; bx, by = nodes[b]
        mx, my = (ax + bx) / 2, (ay + by) / 2
        tx, ty = bx - ax, by - ay
        L = math.hypot(tx, ty)
        if L < 1e-9:
            continue
        tx, ty = tx / L, ty / L
        # 垂直于边的两个候选方向, 取指向单元重心的那个
        nx, ny = -ty, tx
        if (gx - mx) * nx + (gy - my) * ny < 0:
            nx, ny = -nx, -ny
        edge_n[e] = (nx, ny)

    # ---- 3. 节点法向 (miter) ----
    acc = collections.defaultdict(lambda: [0.0, 0.0, []])
    for e, (nx, ny) in edge_n.items():
        for n in e:
            acc[n][0] += nx
            acc[n][1] += ny
            acc[n][2].append((nx, ny))
    node_n = {}
    for n, (sx, sy, lst) in acc.items():
        L = math.hypot(sx, sy)
        if L < 1e-9:                 # 法向完全抵消(180° 折返), 用第一条
            nx, ny = lst[0]
            node_n[n] = (nx, ny, W)
            continue
        ux, uy = sx / L, sy / L
        # 相邻两条边夹角 -> miter 补偿
        if len(lst) >= 2:
            cosh = min(0.99, (lst[0][0] * ux + lst[0][1] * uy))
            scale = min(MITRE_MAX, 1.0 / max(cosh, 0.35))
        else:
            scale = 1.0
        node_n[n] = (ux, uy, W * scale)

    # ---- 4. 生成 B' ----
    nn = NID0
    new_of = {}
    cart = [0.0, 0.0, 0.0]        # 0=翻转, 1=收缩过度, 2=ok
    for n in acc:
        x, y = nodes[n]
        ux, uy, off = node_n[n]
        new_of[n] = nn
        nodes[nn] = (x + ux * off, y + uy * off)
        nn += 1
    # 自交检测: 同一原始边上两端的偏移点必须仍分离
    for e in free:
        a, b = e
        pa, pb = nodes[new_of[a]], nodes[new_of[b]]
        if math.dist(pa, pb) < 0.25 * W:
            cart[1] += 1
    print(f"生成偏移节点 {len(new_of)}  (边级塌缩告警 {int(cart[1])})")

    # ---- 5. 改写第一排单元 ----
    # 必须"全改": 只要留一个单元用原节点, 它和邻居的共享边就变成一对不匹配的自由边
    # (上一版留白 4 个 -> 35 处缺口 / 69 条真实自由边)。形变交给后面的质量统计把关。
    bset = set(acc)
    changed = 0
    kept = []
    shrink = collections.Counter()      # 面积比分档
    for eid, ns in cav:
        u = list(dict.fromkeys(ns))
        cnt = sum(1 for n in u if n in bset)
        if cnt == 0:
            kept.append((eid, ns)); continue
        new = [new_of[n] if n in bset else n for n in u]
        if len(set(new)) < len(u):      # 偏移点重合 -> 无法改写
            kept.append((eid, ns)); continue
        a0 = abs(sarea([nodes[n] for n in u]))
        a1 = abs(sarea([nodes[n] for n in new]))
        r = a1 / a0 if a0 > 1e-12 else 0.0
        if r < 0.2:      shrink["<0.2"] += 1
        elif r < 0.5:    shrink["0.2-0.5"] += 1
        elif r < 0.8:    shrink["0.5-0.8"] += 1
        else:            shrink[">=0.8"] += 1
        kept.append((eid, new))
        changed += 1
    print(f"第一排单元改写 {changed} / {len(cav)}   面积比分布 {dict(shrink)}")

    # ---- 6. washer 条带 ----
    eid_max = max(eid for eid, _ in cav) if cav else 0
    newid = eid_max + 1
    strip = []
    bad = 0
    for e in free:
        a, b = e
        a2, b2 = new_of[a], new_of[b]
        quad = [a, b, b2, a2]
        if len(set(quad)) < 4:
            bad += 1; continue
        A = sarea([nodes[n] for n in quad])
        if abs(A) < MIN_WASHER_AREA:
            bad += 1; continue
        if A < 0:                     # 与气腔绕向相反 -> 反转
            quad = [a, a2, b2, b]
        strip.append((newid, quad))
        newid += 1
    print(f"washer 条带 {len(strip)}  (丢弃 {bad})")

    # ---- 7. 写出 ----
    with open(DST, "w", encoding="utf-8") as f:
        for n in sorted(nodes):
            x, y = nodes[n]
            f.write(f"N {n} {x:.6f} {y:.6f} 0.0\n")
        for tag in elems:
            if tag == "cav":
                continue
            for eid, ns in elems[tag]:
                f.write(f"S {tag} {eid} " + " ".join(str(n) for n in ns) + "\n")
        for eid, ns in kept:
            f.write(f"S cav {eid} " + " ".join(str(n) for n in ns) + "\n")
        for eid, ns in strip:
            f.write(f"S cav_washer {eid} " + " ".join(str(n) for n in ns) + "\n")

    # ---- 8. 报告 ----
    ws = [abs(sarea([nodes[n] for n in q])) for _, q in strip]
    ww = []
    for _, q in strip:
        p0, p1 = nodes[q[0]], nodes[q[1]]
        p2, p3 = nodes[q[2]], nodes[q[3]]
        ww.append(abs(sarea([p0, p1, p2, p3])) / max(math.dist(p0, p1), 1e-9))
    rep = {
        "src": SRC, "dst": DST, "width_mm": W,
        "cav_elems_in": len(cav), "cav_elems_out": len(kept),
        "rewritten": changed, "strips": len(strip), "strips_dropped": bad,
        "free_edges": len(free), "boundary_nodes": len(acc),
        "strip_area_total": sum(ws),
        "strip_width_median": statistics.median(ww) if ww else 0,
        "strip_width_min": min(ww) if ww else 0,
        "strip_width_max": max(ww) if ww else 0,
    }
    json.dump(rep, open(REPORT, "w", encoding="utf-8"), indent=1)
    print("\n=== washer ===")
    for k in ("cav_elems_in", "cav_elems_out", "rewritten", "strips", "strips_dropped",
              "strip_area_total", "strip_width_median", "strip_width_min", "strip_width_max"):
        v = rep[k]
        print(f"  {k:20s} {v:.3f}" if isinstance(v, float) else f"  {k:20s} {v}")


if __name__ == "__main__":
    main()
