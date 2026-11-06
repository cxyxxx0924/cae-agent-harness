# v9_recon2.py — 补齐: 拐角线 / 凸台顶边盖线 / BELT 主环精确成员 / 排气口区
import json, os
from collections import defaultdict

BASE = os.environ.get("WORKDIR", ".") + "/out/"

feat = {}
for ln in open(BASE + "geom_features.txt", encoding="utf-8"):
    if not ln.startswith("LINE "):
        continue
    p = ln.split("|")
    f = p[0].split()
    lid = int(f[1])
    feat[lid] = dict(
        L=float(f[2]),
        sp=tuple(map(float, p[1].split()[:2])),
        ep=tuple(map(float, p[2].split()[:2])),
    )

cls = json.load(open(BASE + "classify_final.json", encoding="utf-8"))["line_comp"]
CLS = {int(k): v for k, v in cls.items()}

def ends(lid):
    return (feat[lid]["sp"], feat[lid]["ep"])

print("=== A. 拐角 (1620.23,382.56) 10mm 内有端点的线 ===")
for lid in sorted(feat):
    for tag, pt in (("sp", feat[lid]["sp"]), ("ep", feat[lid]["ep"])):
        if abs(pt[0] - 1620.23) < 12 and abs(pt[1] - 382.56) < 12:
            d = feat[lid]
            print(f"  L{lid:<4d} [{CLS.get(lid,'-'):7s}] L={d['L']:7.2f} sp({d['sp'][0]:8.2f},{d['sp'][1]:7.2f}) ep({d['ep'][0]:8.2f},{d['ep'][1]:7.2f}) .{tag}")
            break

print()
print("=== B. BELT 线 max(x)>1430 全列 ===")
for lid in sorted(feat):
    if CLS.get(lid) != "BELT":
        continue
    d = feat[lid]
    if max(d["sp"][0], d["ep"][0]) > 1430:
        print(f"  L{lid:<4d} L={d['L']:7.2f} sp({d['sp'][0]:8.2f},{d['sp'][1]:7.2f}) ep({d['ep'][0]:8.2f},{d['ep'][1]:7.2f})")

print()
print("=== C. TETHER 线端点 y in [377,386] (凸台顶边盖线候选, 全域) ===")
for lid in sorted(feat):
    if CLS.get(lid) != "TETHER":
        continue
    d = feat[lid]
    for tag, pt in (("sp", d["sp"]), ("ep", d["ep"])):
        if 377 <= pt[1] <= 386 and d["L"] > 20:
            print(f"  L{lid:<4d} L={d['L']:7.2f} sp({d['sp'][0]:8.2f},{d['sp'][1]:7.2f}) ep({d['ep'][0]:8.2f},{d['ep'][1]:7.2f})")
            break

print()
print("=== D. BELT 连通组分 (端点搭接 tol=0.05) ===")
adj = defaultdict(list)
for lid in feat:
    if CLS.get(lid) != "BELT":
        continue
    s, e = ends(lid)
    for lid2 in feat:
        if lid2 <= lid or CLS.get(lid2) != "BELT":
            continue
        s2, e2 = ends(lid2)
        for p1 in (s, e):
            for p2 in (s2, e2):
                if abs(p1[0] - p2[0]) < 0.05 and abs(p1[1] - p2[1]) < 0.05:
                    adj[lid].append(lid2)
                    adj[lid2].append(lid)
seen = set()
comps = []
for lid in sorted(feat):
    if CLS.get(lid) != "BELT" or lid in seen:
        continue
    stack = [lid]; comp = []
    seen.add(lid)
    while stack:
        c = stack.pop()
        comp.append(c)
        for n in adj[c]:
            if n not in seen:
                seen.add(n); stack.append(n)
    comps.append(sorted(comp))
comps.sort(key=len, reverse=True)
deg = {lid: len(adj[lid]) for lid in feat if CLS.get(lid) == "BELT"}
for i, comp in enumerate(comps):
    danglers = [l for l in comp if deg[l] < 2]
    print(f"  comp{i}: {len(comp)} 线, dangling({len(danglers)}): {danglers[:15]}")
print("  主环成员:", comps[0] if comps else [])

print()
print("=== E. 排气口区 TETHER 全线 (x[-350,50] y[-150,60]) 及其连通 ===")
for lid in sorted(feat):
    if CLS.get(lid) != "TETHER":
        continue
    d = feat[lid]
    if any(-350 <= p[0] <= 50 and -150 <= p[1] <= 60 for p in (d["sp"], d["ep"])):
        print(f"  L{lid:<4d} L={d['L']:7.2f} sp({d['sp'][0]:8.2f},{d['sp'][1]:7.2f}) ep({d['ep'][0]:8.2f},{d['ep'][1]:7.2f})")
