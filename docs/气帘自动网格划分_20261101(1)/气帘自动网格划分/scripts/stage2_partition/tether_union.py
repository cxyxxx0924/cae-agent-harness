# -*- coding: utf-8 -*-
"""
拉带完整凸台轮廓提取 (cab2 第二步)
------------------------------------------------------------------
问题: 每站凸台由多个独立/开链环组成(上部梯形 + 下部凸字块 + 内槽 + 螺栓孔),
      旧的"按面积阈值挑两个环"漏掉上部梯形 -> 顶端 7 个凸台上半截没网格。

做法: 按 X 分 8 站 -> 每站所有 L4 线用粗笔画成线墙 -> 从图像外缘 flood fill
      标出"外部" -> 余下全部像素即凸台内部(含被线围住的槽/孔, 按用户要求忽略)
      -> 掩膜膨胀半个线宽补偿 -> Moore 邻域追踪边界 -> DP 简化 -> 输出多边形。
"""
import collections
import json
import math
import sys

import numpy as np
from PIL import Image, ImageDraw

SRC = "lines_pts.txt"
OUT_JSON = "tether_full.json"
OUT_PNG = "tether_full_check.png"

RES = 0.25          # mm / pixel
WALL = 3.0          # 线墙粗细 mm (须 > CAD 断口 1.3mm)
DP_TOL = 0.5        # DP 简化容差 mm
MIN_AREA = 1500.0   # 凸台最小面积 mm^2

# 8 站中心 X (来自 tether_polys 统计)
STATION_X = [-274.6, -4.8, 283.3, 489.5, 982.3, 1275.3, 1483.4, 1631.9]


def load_l4():
    segs = []   # (lid, [(x,y),...])
    for ln in open(SRC, encoding="utf-8", errors="replace"):
        if "|" not in ln:
            continue
        h, rest = ln.split("|", 1)
        p = h.split()
        if len(p) < 9 or p[0] != "L4":
            continue
        pts = []
        for s in rest.strip().split(";"):
            a = s.split()
            if len(a) >= 3:
                pts.append((float(a[0]), float(a[1])))
        if len(pts) >= 2:
            segs.append((int(p[1]), pts))
    return segs


def assign(segs):
    """按线条 bbox 中心 X 归到最近站"""
    buckets = collections.defaultdict(list)
    for lid, pts in segs:
        xs = [q[0] for q in pts]
        cx = (min(xs) + max(xs)) / 2
        k = min(range(len(STATION_X)), key=lambda i: abs(STATION_X[i] - cx))
        if abs(STATION_X[k] - cx) > 130:
            continue        # 离所有站都远, 是站间的连线, 丢弃
        buckets[k].append((lid, pts))
    return buckets


def station_polygon(lines):
    """一站的所有线 -> 凸台外轮廓 (像素级 union + 外缘 flood fill)"""
    xs = [q[0] for _, pts in lines for q in pts]
    ys = [q[1] for _, pts in lines for q in pts]
    pad = 6.0
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad
    W = int((x1 - x0) / RES) + 2
    H = int((y1 - y0) / RES) + 2

    img = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(img)
    wpx = max(2, int(WALL / RES))
    for _, pts in lines:
        px = [((q[0] - x0) / RES, (y1 - q[1]) / RES) for q in pts]
        dr.line(px, fill=255, width=wpx, joint="curve")
        for q in px:                       # 补端点圆头
            dr.ellipse([q[0]-wpx/2, q[1]-wpx/2, q[0]+wpx/2, q[1]+wpx/2], fill=255)

    m = np.array(img) > 0
    # 从图像四边 flood fill "外部"
    outside = np.zeros_like(m)
    st = []
    for i in range(W):
        for j in (0, H - 1):
            if not m[j, i] and not outside[j, i]:
                outside[j, i] = True; st.append((i, j))
    for j in range(H):
        for i in (0, W - 1):
            if not m[j, i] and not outside[j, i]:
                outside[j, i] = True; st.append((i, j))
    while st:
        x, y = st.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and not m[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                st.append((nx, ny))

    # 非外部 = 凸台(含线墙)。墙两侧各 1.5mm, 外缘即"真实CAD线 + 1.5mm",
    # 故统一腐蚀半个线宽即可回到墙中线, 同时上/下部块天然连通。
    mask = ~outside
    r = max(1, int((WALL / 2) / RES))
    pad_m = np.pad(mask, r, mode="constant")
    er = np.ones_like(mask)
    for dj in range(-r, r + 1):
        for di in range(-r, r + 1):
            if di * di + dj * dj <= r * r:
                er &= pad_m[r + dj:r + dj + H, r + di:r + di + W]
    mask = er
    # 膨胀后再取最大块(此时上/下部已连成一体)
    lab2 = np.zeros((H, W), np.int32)
    best, best_n, cur = 0, 0, 0
    for sj in range(H):
        for si in range(W):
            if not mask[sj, si] or lab2[sj, si]:
                continue
            cur += 1
            st = [(si, sj)]; lab2[sj, si] = cur; n = 0
            while st:
                x, y = st.pop(); n += 1
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H and mask[ny, nx] and not lab2[ny, nx]:
                        lab2[ny, nx] = cur; st.append((nx, ny))
            if n > best_n:
                best_n, best = n, cur
    mask = lab2 == best

    # Moore 邻域边界跟踪
    ys_i, xs_i = np.nonzero(mask)
    sj0 = int(ys_i.min())
    si0 = int(xs_i[sj0 == ys_i].min())
    nb = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    contour = [(si0, sj0)]
    prev = 0
    cx, cy = si0, sj0
    for _ in range(4 * (W + H) * 4):
        found = False
        for k in range(8):
            d = (prev + k) % 8
            nx, ny = cx + nb[d][0], cy + nb[d][1]
            if 0 <= nx < W and 0 <= ny < H and mask[ny, nx]:
                prev = (d + 5) % 8
                cx, cy = nx, ny
                contour.append((cx, cy))
                found = True
                break
        if not found:
            break
        if (cx, cy) == (si0, sj0) and len(contour) > 8:
            break

    pts = [(x0 + p[0] * RES, y1 - p[1] * RES) for p in contour]
    return pts, (x0, x1, y0, y1)


def dp(pts, tol):
    if len(pts) < 3:
        return pts
    keep = np.zeros(len(pts), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        ax, ay = pts[i]; bx, by = pts[j]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        best, bi = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / L if L > 1e-9 else math.hypot(px - ax, py - ay)
            if d > best:
                best, bi = d, k
        if best > tol:
            keep[bi] = True
            stack.append((i, bi)); stack.append((bi, j))
    return [p for p, k in zip(pts, keep) if k]


def area(p):
    s = 0.0
    for i in range(len(p)):
        j = (i + 1) % len(p)
        s += p[i][0] * p[j][1] - p[j][0] * p[i][1]
    return s / 2


def main():
    segs = load_l4()
    print(f"L4 线 {len(segs)} 条")
    buckets = assign(segs)
    result = []
    for k in sorted(buckets):
        lines = buckets[k]
        pts, box = station_polygon(lines)
        pts = dp(pts, DP_TOL)
        A = abs(area(pts))
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        print(f"站{k+1}: 线{len(lines):3d}  轮廓点{len(pts):3d}  面积{A:8.1f}  "
              f"X[{min(xs):8.1f},{max(xs):8.1f}] Y[{min(ys):6.1f},{max(ys):6.1f}]")
        if A < MIN_AREA:
            print("   -> 面积过小, 跳过")
            continue
        result.append({"station": k + 1, "area": A, "pts": pts})
    json.dump(result, open(OUT_JSON, "w", encoding="utf-8"), indent=1)
    print(f"\n写出 {OUT_JSON}: {len(result)} 个凸台")

    # 校验图
    x0 = min(min(q[0] for q in it["pts"]) for it in result) - 20
    x1 = max(max(q[0] for q in it["pts"]) for it in result) + 20
    y0 = min(min(q[1] for q in it["pts"]) for it in result) - 20
    y1 = max(max(q[1] for q in it["pts"]) for it in result) + 20
    S = 0.8
    W, H = int((x1 - x0) * S), int((y1 - y0) * S)
    img = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    for it in result:
        p = [((q[0] - x0) * S, H - (q[1] - y0) * S) for q in it["pts"]]
        dr.polygon(p, outline=(220, 30, 30), width=2)
        for q in p:
            dr.ellipse([q[0]-2, q[1]-2, q[0]+2, q[1]+2], fill=(30, 90, 220))
    for lid, pts in segs:
        if not (x0 <= pts[0][0] <= x1):
            continue
        dr.line([((q[0] - x0) * S, H - (q[1] - y0) * S) for q in pts], fill=(200, 200, 200), width=1)
    img.save(OUT_PNG)
    print("校验图", OUT_PNG)


if __name__ == "__main__":
    main()
