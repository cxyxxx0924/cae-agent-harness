# v14_remove_tiny_circles.py — 用户 2026-10-21 19:01 反馈：剔除气腔内三个小圆圈
#
# 用户反馈 (HM 截图标注"移走"):
#   拉带(TETHER)组里有三个小圆圈, 独立漂浮在气腔内部, 面积很小 —— 从拉带组移走。
#   发图说明时必须先渲染一张带坐标标注的图核对再动手 (out/v14_confirm_coords.png)。
#
# 几何实证 (geom_features.txt 全 828 条 LINE, 无 ARC):
#   circle A  (580.06,260.30)~(582.88,265.60)  L229+L230  同一小段重复 2 次
#   circle B  (894.05,263.60)~(896.87,268.90)  L231/232/235/236/239/240/243/244
#                                              同一小段重复 8 次 (4 副本 x 双向)
#   circle C  (878.30,320.67)~(881.12,325.96)  L247+L248  同一小段重复 2 次
#   三者均为 ~6.1mm 退化重复微段 (bbox 2.8 x 5.3mm), 互相独立、与任何环不连通,
#   在 HM 中渲染即用户截图中的"小圆圈"。属图纸符号/标记残留, 不参与分区。
#
# v14 = v13 + delta:  TETHER -= {229,230,231,232,235,236,239,240,243,244,247,248}
#                     (12 条 -> lines0, 与其他 DROP 一致)
#
# 源: 规范 v8 newcab_classify8.json (119/78/59/572), 幂等可重跑
# 输出: classify_v14.json + classify_final.json
import json, os, shutil
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

# V14_SRC 可为绝对路径或 out/ 下的裸文件名 (P53: 裸文件名必须拼 BASE, 否则 FileNotFoundError)
SRC = os.environ.get("V14_SRC", "newcab_classify8.json")
if not os.path.isabs(SRC):
    SRC = BASE + SRC
cls = json.load(open(SRC, encoding="utf-8"))["line_comp"]
C = {int(k): v for k, v in cls.items()}

# ---- v9 修正清单 ----
TO_BELT   = [822, 525, 767]
TO_CAVITY = [134, 166, 167, 253, 471, 161]   # v10 清单 + v12 唯一新增 L161
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
V10_DROP = [162, 163, 164, 233, 234, 159, 158, 157]

# ---- v13 delta ----
V13_REMOVE_FROM_CAVITY = [161]                       # 移除左边错线
V13_ADD_TO_CAVITY = [168, 169, 170, 172, 188, 196]  # 编号顺滑链 + 封口段

# ---- v14 delta: 剔除气腔内三个小圆圈 (拉带组, 退化重复微段) ----
V14_TINY_CIRCLES = [229, 230, 231, 232, 235, 236, 239, 240, 243, 244, 247, 248]

moved = defaultdict(list)
for lid in TO_BELT:
    if lid in C: moved[f"{C[lid]}->BELT"].append(lid); C[lid] = "BELT"
for lid in TO_CAVITY:
    if lid in C: moved[f"{C[lid]}->CAVITY"].append(lid); C[lid] = "CAVITY"
for lid in TO_TETHER:
    if lid in C: moved[f"{C[lid]}->TETHER"].append(lid); C[lid] = "TETHER"
for lid in V9_DROP + V10_DROP:
    if lid in C: moved[f"{C[lid]}->DROP"].append(lid); del C[lid]

# v13: 先移除 161 (回未归档/lines0)
for lid in V13_REMOVE_FROM_CAVITY:
    if C.get(lid) == "CAVITY":
        moved[f"CAVITY->UNCLASS(v13)"].append(lid); del C[lid]
# v13: 编号顺滑链 + 封口段并入 CAVITY
for lid in V13_ADD_TO_CAVITY:
    prev = C.get(lid, "未归档")
    moved[f"{prev}->CAVITY(v13)"].append(lid); C[lid] = "CAVITY"

# v14: 三个小圆圈移出拉带 (-> lines0)
for lid in V14_TINY_CIRCLES:
    if C.get(lid) == "TETHER":
        moved["TETHER->UNCLASS(v14)"].append(lid); del C[lid]

print("=== 变更清单 (v14 delta) ===")
for k in sorted(moved):
    print(f"  {k}: {sorted(moved[k])}")

# ---- 小圆圈专项核验: 12 条确实全在气腔 bbox 内且互不相连 ----
cav_ids = sorted(l for l, c in C.items() if c == "CAVITY")
cxs = []; cys = []
for l in cav_ids:
    cxs += [feat[l]["sp"][0], feat[l]["ep"][0]]
    cys += [feat[l]["sp"][1], feat[l]["ep"][1]]
print(f"\nCAVITY bbox: x[{min(cxs):.0f},{max(cxs):.0f}] y[{min(cys):.0f},{max(cys):.0f}]")
for grp, name in ((V14_TINY_CIRCLES[:2], "A"), (V14_TINY_CIRCLES[2:10], "B"), (V14_TINY_CIRCLES[10:], "C")):
    xs = []; ys = []
    for l in grp:
        xs += [feat[l]["sp"][0], feat[l]["ep"][0]]
        ys += [feat[l]["sp"][1], feat[l]["ep"][1]]
    inside = min(cxs) <= min(xs) and max(xs) <= max(cxs) and min(cys) <= min(ys) and max(ys) <= max(cys)
    print(f"  circle {name}: x[{min(xs):.1f},{max(xs):.1f}] y[{min(ys):.1f},{max(ys):.1f}] 气腔内部={inside}")

# ---- 连通性 QA (tol=0.05) ----
def trace(class_name, ids):
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
    return comps

n14 = {c: sum(1 for v in C.values() if v == c) for c in ("BELT", "CAVITY", "SEAM", "TETHER")}
print(f"\n=== v14 计数: {n14}  合计 {sum(n14.values())} (原828, 移出 {828-sum(n14.values())} 条) ===")
for cname in ("BELT", "CAVITY", "SEAM", "TETHER"):
    ids = sorted(l for l, c in C.items() if c == cname)
    if ids:
        trace(cname, ids)

out = {"version": "v14", "line_comp": {str(k): v for k, v in sorted(C.items())},
       "note": "v13 + 剔除气腔内三个小圆圈(L229/230,231/232/235/236/239/240/243/244,247/248, 拉带组退化重复微段 -> lines0)"}
json.dump(out, open(BASE + "classify_v14.json", "w"), indent=1)
shutil.copy(BASE + "classify_v14.json", BASE + "classify_final.json")
print("\nwrote classify_v14.json + classify_final.json")
