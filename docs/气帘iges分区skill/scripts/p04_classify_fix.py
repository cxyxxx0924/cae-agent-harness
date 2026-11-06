"""Apply bridge-scan fixes (classify_prev.json -> classify_final.json) + ring-closure QA.

用法:
  1) 先跑 p03_bridge_scan.py 找出"两端都平滑搭接到另一类"的跨类桥接候选线
  2) 把确认要改的线填进下面 FIX = {线id: 目标类}
  3) 跑本脚本: 应用 FIX -> 输出 classify_final.json -> 自动做各类环闭合 QA
     (CAVITY 应 1 个 component 且仅图纸固有缺口有悬挂端; SEAM 各哑铃应 0 悬挂端)
FIX 留空 = 只跑 QA 不改分类。
NEW_CAB 实例（12 条, 全部由 bridge_scan 找出）:
    130/95/93: CAVITY  气腔底边三段（曾被种子列表漏掉）
    69/66/70:  CAVITY  气腔右腰链 L65->L69->L66->L70->L67
    68:        CAVITY  气腔右上角碎片 L72->L68->L30
    91:        CAVITY  气腔右缘（追踪进 L29/L11 链）
    762:       BELT    布带右缘 20.22mm 缺口补段（与 L763/L764 切线连续）
    163/205:   SEAM    缝线通道内的 1~2mm 小连接段
"""
import json, os
from collections import defaultdict

BASE = os.environ.get("WORKDIR", os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out")

feat = {}
for ln in open(os.path.join(OUT, "geom_features.txt"), encoding="utf-8"):
    if not ln.startswith("LINE "):
        continue
    p = ln.split("|")
    f = p[0].split()
    lid = int(f[1])
    feat[lid] = dict(
        L=float(f[2]),
        sp=tuple(map(float, p[1].split()[:2])),
        ep=tuple(map(float, p[2].split()[:2])),
        ts=tuple(map(float, p[3].split()[:2])),
        te=tuple(map(float, p[4].split()[:2])),
    )

d = json.load(open(os.path.join(OUT, "classify_prev.json"), encoding="utf-8"))
cls = {int(k): v for k, v in d["line_comp"].items()}

FIX = {
    # 示例: 130: "CAVITY", 762: "BELT",
    # 实际值由 p03_bridge_scan.py 输出 + 渲染复核后人工确认填入
}
for lid, c in sorted(FIX.items()):
    old = cls.get(lid)
    cls[lid] = c
    print(f"L{lid:<4d} {old} -> {c}   L={feat[lid]['L']:8.2f}")

counts = defaultdict(int)
for c in cls.values():
    counts[c] += 1
print("\n=== counts after fix ===")
for c in ("BELT", "CAVITY", "SEAM", "TETHER"):
    print(f"  {c}: {counts[c]}")
print(f"  total: {sum(counts.values())}")

# ---------- ring closure QA ----------
TOL = 8.0
def near(a, b):
    return abs(a[0]-b[0]) < TOL and abs(a[1]-b[1]) < TOL

print("\n=== ring-closure QA (same-class, 8mm) ===")
for c in ("BELT", "CAVITY", "SEAM"):
    lids = [l for l, v in cls.items() if v == c]
    adj = defaultdict(list)
    for lid in lids:
        for end in ("sp", "ep"):
            e = feat[lid][end]
            for o in lids:
                if o == lid:
                    continue
                for oe in ("sp", "ep"):
                    if near(feat[o][oe], e):
                        adj[lid].append((o, end, oe))
    dangling = [(lid, end) for lid in lids for end in ("sp", "ep")
                if not any(e2 == end for _, e2, _ in adj[lid])]
    seen, comps = set(), []
    for lid in lids:
        if lid in seen:
            continue
        stack, comp = [lid], set()
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            for o, _, _ in adj[x]:
                if o not in comp:
                    stack.append(o)
        seen |= comp
        comps.append(comp)
    print(f"\n{c}: {len(lids)} lines, {len(comps)} components, {len(dangling)} dangling ends")
    for comp in sorted(comps, key=len, reverse=True):
        dl = [l for l in comp if any(not any(e2 == end for _, e2, _ in adj[l])
                                     for end in ("sp", "ep"))]
        tag = "CLOSED" if not dl else f"open({len(dl)})"
        print(f"   size={len(comp):3d} {tag}  {sorted(comp)[:16]}{'...' if len(comp)>16 else ''}")
    if dangling:
        for lid, end in dangling:
            e = feat[lid][end]
            best = min((( (feat[o][oe][0]-e[0])**2 + (feat[o][oe][1]-e[1])**2 )**0.5, o)
                       for o in lids if o != lid for oe in ("sp","ep"))
            print(f"   dangling L{lid}.{end} ({e[0]:8.2f},{e[1]:8.2f}) nearest same-class L{best[1]} d={best[0]:.2f}")

d["line_comp"] = {str(k): v for k, v in cls.items()}
d["version"] = "fix"
d["fixes"] = {str(k): v for k, v in FIX.items()}
json.dump(d, open(os.path.join(OUT, "classify_final.json"), "w", encoding="utf-8"), indent=1)
print("\nsaved " + OUT + "/classify_final.json")
