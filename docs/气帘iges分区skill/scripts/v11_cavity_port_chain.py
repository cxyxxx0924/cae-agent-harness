# v11_cavity_port_chain.py — 用户 2026-10-21 15:52 反馈：白色未归档链天然连到封口处，加进气腔环
#
# 用户反馈（附 HyperMesh 截图）:
#   v10 之后口部那批白色未归档线里, 有一条是连续连接的链, 它天然一路延伸到
#   最斜上方蓝色(布带)封口斜线段处 = 充气口封口线段处 —— "加上这一下段就完美了"。
#
# 几何实证 (端点搭接, 最大内部间隙 0.29mm, 链总长 922.7mm):
#   气腔右支自由端 L167.ep(835.96,350.33)
#     -> L157 (836,349 -> 885,349 水平, 与 L167 成 1mm 双壁=缝纫管真实结构)
#     -> L158 (885,349 -> 890,344) -> L159 (890,344 -> 890,292 右竖直壁)
#     -> L234 -> L233 (右端连接 900,275) -> L164 (气道底壁 585,239 -> 896,256)
#     -> L163 -> L162 (531,335 -> 583,239) -> L161 (左长斜壁 835,496 -> 531,335)
#     -> 楔顶 (834.89,497.37) = 布带封口线段 L249/L196 交点 = 气腔 L166.sp, 距离 1.0mm
#   注: v10 红叉叉的是平行重复线 (L160/L165 与 L164 重复、L204-217 族、L137-186 折叠族);
#       这条主链不是重复垃圾, 是气腔在口部的真实内壁轮廓。
#
# 落地: 在 v10 基础上把这条 9 线链从 DROP 归入 CAVITY (链首尾各留 ~1mm 图纸固有微缝)
# 源: 规范 v8 newcab_classify8.json (119/78/59/572), 幂等可重跑 (P43/P44 教训)
# 输出: classify_v11.json + classify_final.json, 期望 36/92/43/567 = 738 (90 条不参与)
import json, os
from collections import defaultdict

BASE = os.environ.get("WORKDIR", ".") + "/out/"

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

SRC = os.environ.get("V11_SRC", BASE + "newcab_classify8.json")
cls = json.load(open(SRC, encoding="utf-8"))["line_comp"]
C = {int(k): v for k, v in cls.items()}

# ---- v9 修正清单 (气道相关行由 v11 链回归) ----
TO_BELT   = [822, 525, 767]
TO_CAVITY = [134, 166, 167, 253, 471]
TO_TETHER = [262, 263, 316, 317, 370, 371]
V9_DROP = (
    [136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156] +
    [168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186] +
    [190,197,198,199,200,201,202,203,204,206,207,208,209,210,211,212,213,214,215,216,
     217,218,219,220,221,222,223,224,225,226,227,228] +
    [160,165,205,237,238,241,242,245,246] +
    [5,37,820,821,825,826,827,828] +
    [254]
)
# ---- v10 移出 + v11 链回归 (净效果: 这 9 条最终留在 CAVITY) ----
V10_DROP  = [161, 162, 163, 164, 233, 234, 159, 158, 157]
V11_CHAIN = [161, 162, 163, 164, 233, 234, 159, 158, 157]   # 用户确认: 天然连到封口处, 归还 CAVITY

moved = defaultdict(list)
for lid in TO_BELT:
    if lid in C: moved[f"{C[lid]}->BELT"].append(lid); C[lid] = "BELT"
for lid in TO_CAVITY:
    if lid in C: moved[f"{C[lid]}->CAVITY"].append(lid); C[lid] = "CAVITY"
for lid in TO_TETHER:
    if lid in C: moved[f"{C[lid]}->TETHER"].append(lid); C[lid] = "TETHER"
for lid in V9_DROP + V10_DROP:
    if lid in C: moved[f"{C[lid]}->DROP"].append(lid); del C[lid]
for lid in V11_CHAIN:
    moved["DROP->CAVITY(链回归)"].append(lid); C[lid] = "CAVITY"

print("=== 变更清单 ===")
for k in sorted(moved):
    print(f"  {k}: {sorted(moved[k])}")

# ---- 连通性 QA (tol=0.05) + 断点诚实报告 (<=6mm 近邻) ----
def trace(class_name, ids):
    adj = defaultdict(set)
    pts = {}
    for lid in ids:
        pts[(lid, "sp")] = feat[lid]["sp"]
        pts[(lid, "ep")] = feat[lid]["ep"]
        adj[(lid, "sp")].add((lid, "ep"))   # 线自身是桥
        adj[(lid, "ep")].add((lid, "sp"))
    keys = list(pts)
    for i, k1 in enumerate(keys):
        for k2 in keys[i+1:]:
            if k1[0] == k2[0]:
                continue
            p1, p2 = pts[k1], pts[k2]
            if abs(p1[0]-p2[0]) < 0.05 and abs(p1[1]-p2[1]) < 0.05:
                adj[k1].add(k2); adj[k2].add(k1)
    seen = set(); comps = []
    for k in keys:
        if k in seen:
            continue
        st = [k]; seen.add(k); comp = []
        while st:
            c = st.pop(); comp.append(c)
            for n in adj[c]:
                if n not in seen:
                    seen.add(n); st.append(n)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    print(f"\n=== {class_name}: {len(ids)} 线, {len(comps)} 个连通组分 ===")
    for i, comp in enumerate(comps):
        lds = sorted(set(l for l, t in comp))
        deg = defaultdict(int)
        for l, t in comp:
            deg[l] += len(adj[(l, t)]) - 1
        danglers = sorted(l for l in lds if deg[l] < 2)
        xs = []; ys = []
        for l in lds:
            xs += [feat[l]["sp"][0], feat[l]["ep"][0]]
            ys += [feat[l]["sp"][1], feat[l]["ep"][1]]
        tag = " <-- 主环" if i == 0 else ""
        print(f"comp{i} [{len(lds)}线] bbox x[{min(xs):.0f},{max(xs):.0f}] y[{min(ys):.0f},{max(ys):.0f}]{tag}")
        if danglers:
            print(f"  自由端: {danglers}")
            for l in danglers:
                for tagp, pt in (("sp", feat[l]["sp"]), ("ep", feat[l]["ep"])):
                    if deg[l] < 2:
                        best = min(
                            ((l2, t2, ((pt[0]-p2[0])**2+(pt[1]-p2[1])**2)**.5)
                             for l2 in feat if l2 != l and l2 not in ids
                             for t2, p2 in (("sp", feat[l2]["sp"]), ("ep", feat[l2]["ep"]))
                             if ((pt[0]-p2[0])**2+(pt[1]-p2[1])**2)**.5 < 6.0),
                            default=None, key=lambda x: x[2])
                        if best:
                            print(f"    L{l}.{tagp}({pt[0]:.1f},{pt[1]:.1f}) 近邻 L{best[0]}.{best[1]} d={best[2]:.2f}")
    return comps

n11 = {c: sum(1 for v in C.values() if v == c) for c in ("BELT", "CAVITY", "SEAM", "TETHER")}
print(f"\n=== v11 计数: {n11}  合计 {sum(n11.values())} (原828, 移出 {828-sum(n11.values())} 条) ===")
for cname in ("BELT", "CAVITY", "SEAM", "TETHER"):
    ids = sorted(l for l, c in C.items() if c == cname)
    if ids:
        trace(cname, ids)

out = {"version": "v11", "line_comp": {str(k): v for k, v in sorted(C.items())},
       "note": "v9极简轮廓 + v10气腔口部开环 + v11白色连续链9线归还CAVITY(天然连到楔顶封口处, 1mm图纸微缝)"}
json.dump(out, open(BASE + "classify_v11.json", "w"), indent=1)
import shutil
shutil.copy(BASE + "classify_v11.json", BASE + "classify_final.json")
print("\nwrote classify_v11.json + classify_final.json")
