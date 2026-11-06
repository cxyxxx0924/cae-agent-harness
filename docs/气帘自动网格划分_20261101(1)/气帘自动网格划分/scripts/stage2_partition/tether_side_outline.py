# -*- coding: utf-8 -*-
"""
侧面拉带轮廓提取 (cab2 第二步补漏)
------------------------------------------------------------------
用户指出的红圈处: 一条横向拉带, 从布带内部 (X~1450) 穿过端面 X=1620 的
20.22mm 缺口 (L1 762) 伸出到 X=1770, 右端是眼环 + 凸销。

方法同 tether_full.py: L4 线粗笔画墙 -> 外缘 flood fill -> 取非外部 ->
腐蚀半线宽回到墙中线 -> Moore 边界 -> DP 简化。
内部眼环孔/缝制纹按"细小 curve 忽略"填实。
"""
import collections, json, math, sys
import numpy as np
from PIL import Image, ImageDraw

SRC = "lines_pts.txt"
OUT_JSON = "side_tether.json"
OUT_PNG = "side_tether_check.png"
RES = 0.2
WALL = 2.0
DP_TOL = 0.8
BOX = (1425.0, 1800.0, 135.0, 215.0)     # x0,x1,y0,y1


def load_l4(box):
    segs = []
    x0, x1, y0, y1 = box
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
        if len(pts) < 2:
            continue
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
            continue
        # 需要至少一段在窗口内 -> 裁剪到稍大窗口
        segs.append((int(p[1]), pts))
    return segs


def polygon(lines, box):
    x0, x1, y0, y1 = box
    W = int((x1 - x0) / RES) + 2
    H = int((y1 - y0) / RES) + 2
    img = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(img)
    wpx = max(2, int(WALL / RES))
    for _, pts in lines:
        px = [((q[0] - x0) / RES, (y1 - q[1]) / RES) for q in pts]
        dr.line(px, fill=255, width=wpx, joint="curve")
        for q in px:
            dr.ellipse([q[0]-wpx/2, q[1]-wpx/2, q[0]+wpx/2, q[1]+wpx/2], fill=255)
    m = np.array(img) > 0

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
                outside[ny, nx] = True; st.append((nx, ny))
    mask = ~outside

    r = max(1, int((WALL / 2) / RES))
    pad_m = np.pad(mask, r, mode="constant")
    er = np.ones_like(mask)
    for dj in range(-r, r + 1):
        for di in range(-r, r + 1):
            if di * di + dj * dj <= r * r:
                er &= pad_m[r + dj:r + dj + H, r + di:r + di + W]
    mask = er

    # 保留全部像样的连通块
    lab = np.zeros((H, W), np.int32); keep = np.zeros_like(mask)
    MIN_PX = int(40.0 / (RES * RES)); cur = 0
    for sj in range(H):
        for si in range(W):
            if not mask[sj, si] or lab[sj, si]:
                continue
            cur += 1; st = [(si, sj)]; lab[sj, si] = cur; cells = [(si, sj)]
            while st:
                x, y = st.pop()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H and mask[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = cur; st.append((nx, ny)); cells.append((nx, ny))
            if len(cells) >= MIN_PX:
                for x, y in cells:
                    keep[y, x] = True
    mask = keep

    ys_i, xs_i = np.nonzero(mask)
    sj0 = int(ys_i.min()); si0 = int(xs_i[sj0 == ys_i].min())
    nb = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    contour = [(si0, sj0)]; prev = 0; cx, cy = si0, sj0
    for _ in range(8 * (W + H) * 4):
        found = False
        for k in range(8):
            d = (prev + k) % 8
            nx, ny = cx + nb[d][0], cy + nb[d][1]
            if 0 <= nx < W and 0 <= ny < H and mask[ny, nx]:
                prev = (d + 5) % 8; cx, cy = nx, ny
                contour.append((cx, cy)); found = True; break
        if not found:
            break
        if (cx, cy) == (si0, sj0) and len(contour) > 8:
            break
    return [(x0 + p[0] * RES, y1 - p[1] * RES) for p in contour], (mask, x0, x1, y0, y1)


def dp(pts, tol):
    if len(pts) < 3:
        return pts
    keep = np.zeros(len(pts), bool); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        ax, ay = pts[i]; bx, by = pts[j]
        dx, dy = bx - ax, by - ay; L = math.hypot(dx, dy)
        best, bi = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k]
            d = abs(dy*px - dx*py + bx*ay - by*ax)/L if L > 1e-9 else math.hypot(px-ax, py-ay)
            if d > best:
                best, bi = d, k
        if best > tol:
            keep[bi] = True; stack.append((i, bi)); stack.append((bi, j))
    return [p for p, k in zip(pts, keep) if k]


def area(p):
    s = 0.0
    for i in range(len(p)):
        j = (i + 1) % len(p)
        s += p[i][0]*p[j][1] - p[j][0]*p[i][1]
    return s / 2


segs = load_l4(BOX)
print(f"窗口内 L4 线 {len(segs)} 条")
raw, (mask, x0, x1, y0, y1) = polygon(segs, BOX)
print(f"原始轮廓点 {len(raw)}  面积 {abs(area(raw)):.1f}")
pts = dp(raw, DP_TOL)
A = abs(area(pts)); As = abs(area(raw))
xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
print(f"DP 简化 -> {len(pts)} 点  面积 {A:.1f} (偏差 {100*(A-As)/As:+.2f}%)")
print(f"X[{min(xs):.1f},{max(xs):.1f}] Y[{min(ys):.1f},{max(ys):.1f}]  宽 {max(ys)-min(ys):.1f} 长 {max(xs)-min(xs):.1f}")
json.dump([{"name": "side", "area": A, "pts": pts}], open(OUT_JSON, "w", encoding="utf-8"), indent=1)

S = 4.0
W, H = int((x1 - x0) * S), int((y1 - y0) * S)
img = Image.new("RGB", (W, H), (255, 255, 255)); dr = ImageDraw.Draw(img)
p = [((q[0]-x0)*S, H-(q[1]-y0)*S) for q in pts]
dr.polygon(p, outline=(220, 30, 30), width=2)
for lid, sp in segs:
    dr.line([((q[0]-x0)*S, H-(q[1]-y0)*S) for q in sp], fill=(205, 205, 205), width=1)
dr.line([((1620.2-x0)*S, H-(215-y0)*S), ((1620.2-x0)*S, H-(135-y0)*S)], fill=(60, 120, 235), width=2)
img.save(OUT_PNG)
print("校验图", OUT_PNG)
