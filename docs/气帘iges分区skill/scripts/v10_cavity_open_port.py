# v10_cavity_open_port.py — 用户 2026-10-21 15:22 反馈：气腔环在充气口不往回折闭合
#
# 用户反馈（附截图标注）:
#   1. 气腔环到充气口顶部不是往回折形成封闭区域(红叉叉)——气道回路整体不要
#   2. 气腔环其实跟布带环相约在最上面那个斜的线段上:
#      L471 平行于布带 L470 内侧、L166 平行于布带 L189 内侧, 一路往上,
#      到楔形顶端封闭端 (834.89,497.37) = 布带 L249/L196 交点 停止
#   3. 那条线不封闭也没有关系 —— 气腔环在口部是"开口环", 两个自由端停在口部
#   4. 后续网格: 布带层黄色面网格, 充气口处全是气腔面区域, 自然过渡 (参考 cab1)
#
# 落地: 在 v9 基础上, 把气道回路 9 条线从 CAVITY 移出(DROP):
#   L161/L162/L163  左下降壁 (楔顶 835,496 -> 531,335 -> 583,239)
#   L164            气道底壁 (585,239 -> 896,256)
#   L233/L234       右端连接 (896,256 -> 900,275 -> 890,292)
#   L159            右竖直下降 (890,344 -> 890,292)
#   L157/L158       L167 的 1mm 平行重复线 + 斜连接 (835,349 -> 885,349 -> 890,344)
# 保留: L134 -> L471 -> L166 (左侧上行, 顶端开口) + L12 <- L252 <- L251 <- L253 <- L167 (右侧, 开口)
#
# 源: 规范 v8 newcab_classify8.json (119/78/59/572), 幂等可重跑 (P43/P44 教训)
# 输出: classify_v10.json + classify_final.json, 期望 36/83/43/567 = 729 (99 条不参与)
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

# V10_SRC 可为绝对路径或 out/ 下的裸文件名 (P53: 裸文件名必须拼 BASE, 否则 FileNotFoundError)
SRC = os.environ.get("V10_SRC", "newcab_classify8.json")
if not os.path.isabs(SRC):
    SRC = BASE + SRC
cls = json.load(open(SRC, encoding="utf-8"))["line_comp"]
C = {int(k): v for k, v in cls.items()}

# ---- v9 修正清单 (气道相关行已按 v10 反馈剔除, 改入 V10_DROP) ----
TO_BELT   = [822, 525, 767]
TO_CAVITY = [134, 166, 167, 253, 471]        # 仅口部内壁上行线 + 顶边延续链
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
# ---- v10 新增: 气道回路整体移出 (用户红叉叉) ----
V10_DROP = [161, 162, 163, 164, 233, 234, 159, 158, 157]

moved = defaultdict(list)
for lid in TO_BELT:
    if lid in C: moved[f"{C[lid]}->BELT"].append(lid); C[lid] = "BELT"
for lid in TO_CAVITY:
    if lid in C: moved[f"{C[lid]}->CAVITY"].append(lid); C[lid] = "CAVITY"
for lid in TO_TETHER:
    if lid in C: moved[f"{C[lid]}->TETHER"].append(lid); C[lid] = "TETHER"
for lid in V9_DROP + V10_DROP:
    if lid in C: moved[f"{C[lid]}->DROP"].append(lid); del C[lid]

print("=== 变更清单 ===")
for k in sorted(moved):
    print(f"  {k}: {sorted(moved[k])}")

# ---- 连通性 QA (tol=0.05) + 断点诚实报告 (<=6mm 近邻) ----
def trace(class_name, ids, expect_open=0):
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
        if danglers and i == 0:
            print(f"  自由端(开环): {danglers}")
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

n10 = {c: sum(1 for v in C.values() if v == c) for c in ("BELT", "CAVITY", "SEAM", "TETHER")}
print(f"\n=== v10 计数: {n10}  合计 {sum(n10.values())} (原828, 移出 {828-sum(n10.values())} 条) ===")
for cname, expect in (("BELT", None), ("CAVITY", 1), ("SEAM", None), ("TETHER", None)):
    ids = sorted(l for l, c in C.items() if c == cname)
    if ids:
        trace(cname, ids, expect_open=expect or 0)

out = {"version": "v10", "line_comp": {str(k): v for k, v in sorted(C.items())},
       "note": "v9极简轮廓 + v10气腔口部开环(气道回路9线移出, 环与布带环相约楔顶斜线段, 开口停止)"}
json.dump(out, open(BASE + "classify_v10.json", "w"), indent=1)
import shutil
shutil.copy(BASE + "classify_v10.json", BASE + "classify_final.json")
print("\nwrote classify_v10.json + classify_final.json")
