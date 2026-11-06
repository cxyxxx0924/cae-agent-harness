# -*- coding: utf-8 -*-
"""Connectivity graph of the right-edge ladder region (x[1550,1800] y[130,210])."""
import json, os
BASE = os.environ.get("WORKDIR", ".") + "/out/"
cls = json.load(open(BASE + "classify_final.json"))["line_comp"]

lines = {}
for raw in open(BASE + "lines_pts.txt", encoding="utf-8"):
    raw = raw.strip()
    if not raw.startswith("L "):
        continue
    parts = raw.split(None, 4)
    lid = int(parts[1])
    rest = parts[4].split("|", 1)[1] if "|" in parts[4] else ""
    pts = []
    for seg in rest.strip().split(";"):
        t = seg.split()
        if len(t) >= 2:
            pts.append((float(t[0]), float(t[1])))
    lines[lid] = pts

# region lines
reg = {}
for lid, pts in lines.items():
    if len(pts) < 2: continue
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    if 1550 <= (min(xs)+max(xs))/2 <= 1800 and 130 <= (min(ys)+max(ys))/2 <= 210:
        reg[lid] = pts
print("region lines:", len(reg))

def close(a, b, tol=2.0):
    return (a[0]-b[0])**2 + (a[1]-b[1])**2 <= tol*tol

# build endpoint adjacency
ends = {}
for lid, pts in reg.items():
    ends[lid] = [pts[0], pts[-1]]

adj = {lid: set() for lid in reg}
lids = sorted(reg)
for i, a in enumerate(lids):
    for b in lids[i+1:]:
        for ea in ends[a]:
            for eb in ends[b]:
                if close(ea, eb):
                    adj[a].add(b); adj[b].add(a)

# components
seen = set(); comps = []
for lid in lids:
    if lid in seen: continue
    stack = [lid]; comp = []
    seen.add(lid)
    while stack:
        c = stack.pop(); comp.append(c)
        for nb in adj[c]:
            if nb not in seen:
                seen.add(nb); stack.append(nb)
    comps.append(sorted(comp))

print("components (by endpoint connectivity, tol=2mm):", len(comps))
for comp in sorted(comps, key=len, reverse=True):
    cc = {}
    for lid in comp:
        cc[cls[str(lid)]] = cc.get(cls[str(lid)], 0) + 1
    xs = [p[0] for lid in comp for p in reg[lid]]
    ys = [p[1] for lid in comp for p in reg[lid]]
    print("  n=%3d %s  x[%.1f,%.1f] y[%.1f,%.1f]" % (
        len(comp), cc, min(xs), max(xs), min(ys), max(ys)))
    if len(comp) <= 40:
        print("     ids:", comp)

# specifically: what touches L760/L761 (the two circles at 1595,189/154)?
print("\nL760 neighbors:", sorted(adj.get(760, [])))
print("L761 neighbors:", sorted(adj.get(761, [])))
print("L747 (rail top) neighbors:", sorted(adj.get(747, [])))
print("L748 (rail bot) neighbors:", sorted(adj.get(748, [])))
print("L749 (left cap) neighbors:", sorted(adj.get(749, [])))
