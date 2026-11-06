# -*- coding: utf-8 -*-
"""Check every SEAM component: closed sub-loops (circles) at both ends = dumbbell."""
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

seam = [lid for lid in lines if cls[str(lid)] == "SEAM"]
print("SEAM lines:", len(seam))

# endpoint adjacency among SEAM lines
def close(a, b, tol=2.0):
    return (a[0]-b[0])**2 + (a[1]-b[1])**2 <= tol*tol

ends = {lid: [lines[lid][0], lines[lid][-1]] for lid in seam}
adj = {lid: set() for lid in seam}
for i, a in enumerate(seam):
    for b in seam[i+1:]:
        for ea in ends[a]:
            for eb in ends[b]:
                if close(ea, eb):
                    adj[a].add(b); adj[b].add(a)

seen = set(); comps = []
for lid in sorted(seam):
    if lid in seen: continue
    stack=[lid]; comp=[]; seen.add(lid)
    while stack:
        c=stack.pop(); comp.append(c)
        for nb in adj[c]:
            if nb not in seen:
                seen.add(nb); stack.append(nb)
    comps.append(sorted(comp))

print("SEAM components:", len(comps))
for comp in comps:
    xs=[p[0] for l in comp for p in lines[l]]; ys=[p[1] for l in comp for p in lines[l]]
    # count closed loops inside: a line whose sp~ep is a self-closed circle
    selfclosed = [l for l in comp if close(lines[l][0], lines[l][-1], 0.5)]
    # endpoints that are dangling (only 1 neighbor within comp)
    deg = {l: 0 for l in comp}
    for l in comp:
        for nb in adj[l]:
            if nb in comp: deg[l]+=1
    dang = [l for l in comp if deg[l] <= 1]
    print("  n=%2d x[%7.1f,%7.1f] y[%7.1f,%7.1f] selfclosed=%s dangling=%s" % (
        len(comp), min(xs), max(xs), min(ys), max(ys), selfclosed, dang))
    print("      ids:", comp)
