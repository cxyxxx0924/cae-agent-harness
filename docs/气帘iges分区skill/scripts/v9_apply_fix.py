# v9_apply_fix.py — 按用户 2026-10-21 下午反馈修正四分区
# P1 BELT: 删口部内部折叠线+领圈只留最外轮廓; 凸台顶边盖线 L822/L525/L767 还给 BELT;
#          肩部小竖线 L262/L263/L316/L317/L370/L371 归还 TETHER
# P2 CAVITY: 口部靠内平行闭合 L134/L471/L166 + 气道回路 L161/L162/L163/L164/L233/L234/L159/L158/L157/L167/L253
# P3 SEAM: 只留哑铃, 气道线移走, 平行重复线删除
# P4 TETHER: 排气口 2圆+2十字+2弧 移出
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

# 读稳定 v8 源 (828 全量)，保证可重复/幂等；不读 classify_final (会被自身改写)
# 规范 v8 = newcab_classify8.json (119/78/59/572)；classify_prev.json 是含 9 线差异的变体，勿用
# V9_SRC 可为绝对路径或 out/ 下的裸文件名 (P53: 裸文件名必须拼 BASE, 否则 FileNotFoundError)
SRC = os.environ.get("V9_SRC", "newcab_classify8.json")
if not os.path.isabs(SRC):
    SRC = BASE + SRC
cls = json.load(open(SRC, encoding="utf-8"))["line_comp"]
C = {int(k): v for k, v in cls.items()}

TO_BELT = [822, 525, 767]
TO_CAVITY = [134, 157, 161, 166, 167, 253, 471, 158, 159, 162, 163, 164, 233, 234]
TO_TETHER = [262, 263, 316, 317, 370, 371]
DROP = (
    [136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156] +
    [168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186] +
    [190,197,198,199,200,201,202,203,204,206,207,208,209,210,211,212,213,214,215,216,
     217,218,219,220,221,222,223,224,225,226,227,228] +
    [160,165,205,237,238,241,242,245,246] +
    [5,37,820,821,825,826,827,828] +
    [254]                              # 充气口内部折叠 (仅与已DROP的L212等相连)
)

moved = defaultdict(list)
for lid in TO_BELT:
    if lid in C: moved[f"{C[lid]}->BELT"].append(lid); C[lid] = "BELT"
for lid in TO_CAVITY:
    if lid in C: moved[f"{C[lid]}->CAVITY"].append(lid); C[lid] = "CAVITY"
for lid in TO_TETHER:
    if lid in C: moved[f"{C[lid]}->TETHER"].append(lid); C[lid] = "TETHER"
for lid in DROP:
    if lid in C: moved[f"{C[lid]}->DROP"].append(lid); del C[lid]

print("=== 变更清单 ===")
for k in sorted(moved):
    print(f"  {k}: {sorted(moved[k])}")

# ---- 连通性 QA (tol=0.05) + 断点诚实报告 (<=6mm 近邻) ----
def trace(class_name, ids):
    adj = defaultdict(set)
    pts = {}
    for lid in ids:
        for tag, p in (("sp", feat[lid]["sp"]), ("ep", feat[lid]["ep"])):
            pts[(lid, tag)] = p
        # 线自身两端互连（线是桥）
        adj[(lid, "sp")].add((lid, "ep"))
        adj[(lid, "ep")].add((lid, "sp"))
    keys = list(pts)
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1:]:
            if k1[0] == k2[0]:
                continue
            p1, p2 = pts[k1], pts[k2]
            if abs(p1[0] - p2[0]) < 0.05 and abs(p1[1] - p2[1]) < 0.05:
                adj[k1].add(k2); adj[k2].add(k1)
    deg = {k: len(adj[k]) for k in keys}
    seen, comps = set(), []
    for k in keys:
        if k in seen:
            continue
        stack, comp = [k], []
        seen.add(k)
        while stack:
            c = stack.pop(); comp.append(c)
            for n in adj[c]:
                if n not in seen:
                    seen.add(n); stack.append(n)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    print(f"\n=== {class_name}: {len(ids)} 线, {len(comps)} 个连通组分 ===")
    for i, comp in enumerate(comps):
        lds = sorted(set(l for l, t in comp))
        dang = sorted(k for k in comp if deg[k] < 2)
        closed = "闭合" if all(deg[k] == 2 for k in comp) else f"dangling {len(dang)}"
        print(f"  comp{i}: {len(lds)} 线 [{closed}]")
        # 断点近邻报告
        reported = set()
        for k in dang:
            p1 = pts[k]
            best, bd = None, 6.0
            for k2 in keys:
                if k2[0] == k[0] or k2 in adj[k] or k2 in reported:
                    continue
                p2 = pts[k2]
                d = ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2) ** .5
                if d < bd:
                    bd, best = d, k2
            if best:
                reported.add(k); reported.add(best)
                print(f"     gap {bd:5.2f}mm: L{k[0]}.{k[1]}({p1[0]:.2f},{p1[1]:.2f}) <-> L{best[0]}.{best[1]}({pts[best][0]:.2f},{pts[best][1]:.2f})")
        if len(lds) <= 40 and i == 0:
            print(f"     成员: {lds}")
    return comps

bycls = defaultdict(list)
for lid, c in C.items():
    bycls[c].append(lid)
for cname in ("BELT", "CAVITY", "SEAM", "TETHER"):
    trace(cname, sorted(bycls[cname]))

out = {"version": "v9", "line_comp": {str(k): v for k, v in sorted(C.items())},
       "note": "用户反馈修正: 口部只留最外轮廓/气腔经内壁+气道闭合/缝线只留哑铃/排气口移出; L254充气口内折叠移出"}
json.dump(out, open(BASE + "classify_v9.json", "w"), indent=1)
import shutil
shutil.copy(BASE + "classify_v9.json", BASE + "classify_final.json")
n = {c: sum(1 for v in C.values() if v == c) for c in ("BELT", "CAVITY", "SEAM", "TETHER")}
print(f"\n=== 最终计数: {n}  合计 {sum(n.values())} (原828, 移出 {90} 条不参与分区) ===")
