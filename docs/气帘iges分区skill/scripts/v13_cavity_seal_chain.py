# v13_cavity_seal_chain.py — 用户 2026-10-21 18:04 反馈：右侧顺滑链通到封口段
#
# 用户反馈 (HM 目检 + 口述, 方法论):
#   1. v12 在左边错加了一根 L161 (与 L166 平行下到 x=531, "左边弄了两根") —— 移除
#   2. 蓝色气腔环从 L167 起, 编号顺序 168,169,...,172 沿顺滑方向一路通上去
#      (实测 L167-170 端点 0.00mm 衔接, L170-L172 0.06mm 衔接, 无歧义)
#   3. L172 末端封在封口段 L188 与 L196 上 —— 封口线段并入气腔环,
#      方便下一步网格切割 (闭合气腔环于充气口)
#
# 方法论沉淀 (chain_trace.py): 边界线按绘制顺序连续编号; 真正边界顺滑;
#   从种子线出发, 两端都接其他线时优先沿「邻居线号=seed+1」方向进入,
#   之后容差内找下一根时优先方向最顺滑且朝偏好方向者.
#
# v13 = v12 + delta:
#   CAVITY -= {161}                      (移除左边错线)
#   CAVITY += {168,169,170,172}          (编号顺滑链, 原 v9 DROP 的端口白线)
#   CAVITY += {188,196}                  (封口段, 原 BELT)
#
# 源: 规范 v8 newcab_classify8.json (119/78/59/572), 幂等可重跑
# 输出: classify_v13.json + classify_final.json
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

# V13_SRC 可为绝对路径或 out/ 下的裸文件名 (P53: 裸文件名必须拼 BASE, 否则 FileNotFoundError)
SRC = os.environ.get("V13_SRC", "newcab_classify8.json")
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

print("=== 变更清单 (v13 delta) ===")
for k in sorted(moved):
    print(f"  {k}: {sorted(moved[k])}")

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

n13 = {c: sum(1 for v in C.values() if v == c) for c in ("BELT", "CAVITY", "SEAM", "TETHER")}
print(f"\n=== v13 计数: {n13}  合计 {sum(n13.values())} (原828, 移出 {828-sum(n13.values())} 条) ===")
for cname in ("BELT", "CAVITY", "SEAM", "TETHER"):
    ids = sorted(l for l, c in C.items() if c == cname)
    if ids:
        trace(cname, ids)

out = {"version": "v13", "line_comp": {str(k): v for k, v in sorted(C.items())},
       "note": "v12 + 移除左边错线L161 + 右侧编号顺滑链L168-170-172并入CAVITY + 封口段L188/L196并入CAVITY(闭合气腔环于充气口)"}
json.dump(out, open(BASE + "classify_v13.json", "w"), indent=1)
shutil.copy(BASE + "classify_v13.json", BASE + "classify_final.json")
print("\nwrote classify_v13.json + classify_final.json")
