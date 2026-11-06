# -*- coding: utf-8 -*-
"""p07_report.py — 分区终检报告 (通用, 不依赖任何项目硬编码)

输入: $WORKDIR/out/classify_final.json + $WORKDIR/out/geom_features.txt
输出: 屏幕摘要 + $WORKDIR/out/final_report.txt

查什么:
  1. 四组计数 + 未归档(lines0) 计数
  2. 每组 bbox / 连通组分 / 主环自由端(开环位置) —— 环闭合性
  3. 每个连通分量的尺寸: **小尺寸独立分量(<30mm) 单独列出** —— 这类多半是
     图纸符号/标记残留(v14 三小圆即此型), 应人工确认后移出
  4. 组内重复线(同端点同坐标) —— 退化重复微段的强判据
  5. 自由端近邻提示: 开环端点 6mm 内最近的其他线, 供建面/共节点桥接参考

用法: WORKDIR=<工作区> python p07_report.py
"""
import json, os, math
from collections import defaultdict

BASE = os.environ.get("WORKDIR", ".") + "/out/"
SMALL_MM = float(os.environ.get("SMALL_MM", "30"))     # 小分量阈值
NEAR_MM = float(os.environ.get("NEAR_MM", "6"))        # 开环端点近邻搜索半径

feat = {}
for ln in open(BASE + "geom_features.txt", encoding="utf-8"):
    if not ln.startswith("LINE "):
        continue
    p = ln.split("|")
    f = p[0].split()
    feat[int(f[1])] = dict(
        L=float(f[2]),
        sp=tuple(map(float, p[1].split()[:2])),
        ep=tuple(map(float, p[2].split()[:2])),
    )

cls = json.load(open(BASE + "classify_final.json", encoding="utf-8"))["line_comp"]
C = {int(k): v for k, v in cls.items()}
CLASSES = ("BELT", "CAVITY", "SEAM", "TETHER")

lines = []
def emit(s=""):
    print(s)
    lines.append(s)

n = {c: sum(1 for v in C.values() if v == c) for c in CLASSES}
emit("=" * 68)
emit("分区终检报告  (p07_report.py)")
emit("=" * 68)
emit(f"计数: {n}  合计 {sum(n.values())}   未归档 {len(feat)-sum(n.values())} / 总 {len(feat)}")

def components(ids, tol=0.05):
    """tol 内端点视为同一节点, 返回连通分量 [(lines, dangling_lines)]"""
    adj = defaultdict(set)
    pts = {}
    for lid in ids:
        pts[(lid, "sp")] = feat[lid]["sp"]
        pts[(lid, "ep")] = feat[lid]["ep"]
        adj[(lid, "sp")].add((lid, "ep"))
        adj[(lid, "ep")].add((lid, "sp"))
    keys = list(pts)
    for i, k1 in enumerate(keys):
        for k2 in keys[i+1:]:
            if k1[0] == k2[0]:
                continue
            p1, p2 = pts[k1], pts[k2]
            if abs(p1[0]-p2[0]) < tol and abs(p1[1]-p2[1]) < tol:
                adj[k1].add(k2); adj[k2].add(k1)
    seen = set(); comps = []
    for k in keys:
        if k in seen:
            continue
        st = [k]; seen.add(k); comp = []
        while st:
            c = st.pop(); comp.append(c)
            for nb in adj[c]:
                if nb not in seen:
                    seen.add(nb); st.append(nb)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    out = []
    for comp in comps:
        lds = sorted(set(l for l, t in comp))
        deg = defaultdict(int)
        for l, t in comp:
            deg[l] += len(adj[(l, t)]) - 1
        dang = sorted(l for l in lds if deg[l] < 2)
        out.append((lds, dang, adj, pts))
    return out

def bbox(lds):
    xs = []; ys = []
    for l in lds:
        xs += [feat[l]["sp"][0], feat[l]["ep"][0]]
        ys += [feat[l]["sp"][1], feat[l]["ep"][1]]
    return min(xs), max(xs), min(ys), max(ys)

def dup_pairs(lds):
    """组内重复线: 端点坐标完全相同(含互为反向)"""
    seen = {}; dups = []
    for l in lds:
        a, b = feat[l]["sp"], feat[l]["ep"]
        key = tuple(sorted([(round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3))]))
        if key in seen:
            dups.append((seen[key], l))
        else:
            seen[key] = l
    return dups

for cname in CLASSES:
    ids = sorted(l for l, c in C.items() if c == cname)
    if not ids:
        emit(f"\n--- {cname}: 0 线 ---")
        continue
    comps = components(ids)
    x0, x1, y0, y1 = bbox(ids)
    emit(f"\n--- {cname}: {len(ids)} 线, {len(comps)} 连通组分, "
         f"bbox x[{x0:.0f},{x1:.0f}] y[{y0:.0f},{y1:.0f}] ---")
    for i, (lds, dang, adj, pts) in enumerate(comps):
        a0, a1, b0, b1 = bbox(lds)
        w, h = a1 - a0, b1 - b0
        tag = "  <主环>" if i == 0 else ""
        small = "  <<< 小分量, 疑符号残留?" if max(w, h) < SMALL_MM else ""
        emit(f"  comp{i} [{len(lds)}线] bbox x[{a0:.1f},{a1:.1f}] y[{b0:.1f},{b1:.1f}] "
             f"({w:.1f}x{h:.1f}mm){tag}{small}")
        if i == 0 and dang:
            emit(f"    自由端(开环): {dang}")
            for l in dang:
                for tg, pt in (("sp", feat[l]["sp"]), ("ep", feat[l]["ep"])):
                    best = min(
                        ((l2, t2, math.hypot(pt[0]-p2[0], pt[1]-p2[1]))
                         for l2 in feat if l2 not in ids
                         for t2, p2 in (("sp", feat[l2]["sp"]), ("ep", feat[l2]["ep"]))
                         if math.hypot(pt[0]-p2[0], pt[1]-p2[1]) < NEAR_MM),
                        default=None, key=lambda x: x[2])
                    if best:
                        emit(f"      L{l}.{tg}({pt[0]:.1f},{pt[1]:.1f}) 最近邻 "
                             f"L{best[0]}.{best[1]} d={best[2]:.2f}mm")
    dups = dup_pairs(ids)
    if dups:
        emit(f"  重复线 {len(dups)} 对 (疑退化微段): {dups[:6]}{' ...' if len(dups)>6 else ''}")

unass = sorted(set(feat) - set(C))
emit(f"\n--- 未归档(lines0): {len(unass)} 线 ---")
if unass:
    ucomp = components(unass)
    small_u = [(lds, bbox(lds)) for lds, _, _, _ in ucomp]
    tiny = [(lds, bb) for lds, bb in small_u if max(bb[1]-bb[0], bb[3]-bb[2]) < SMALL_MM]
    emit(f"  连通组分 {len(ucomp)} 个, 其中小分量(<{SMALL_MM:.0f}mm) {len(tiny)} 个")
    for lds, bb in tiny[:10]:
        emit(f"    small: {lds}  bbox x[{bb[0]:.1f},{bb[1]:.1f}] y[{bb[2]:.1f},{bb[3]:.1f}]")

emit("\n" + "=" * 68)
emit("门禁建议: ① 小分量逐个人工确认(符号残留 -> 移出) ② 主环自由端须为设计允许的")
emit("          开口(充气口等) ③ 重复线对不为 0 时查是否为退化微段 ④ 交付前跑 t07/t08")
emit("=" * 68)

with open(BASE + "final_report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\nwrote", BASE + "final_report.txt")
