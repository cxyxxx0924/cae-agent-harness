# -*- coding: utf-8 -*-
"""Feature extraction for airbag (气帘) line classification.
Pure geometry + connectivity + position. No line-id features -> general.
Exposes compute_features(workdir) -> (meta, feats) so it can be imported by
the auto_partition skill module. Also runnable standalone (writes features.json).
"""
import os, json, math
from collections import defaultdict

W = "E:/work/AI_CAB/onekey/work/auto_newcab"
OUT = W + "/out"
WELD = 8.0
LONG = 25.0   # short-line threshold (hardware/detail below this)

def load_lines(workdir):
    out = workdir + "/out"
    lines = {}
    for ln in open(out + "/lines_pts.txt", encoding="utf-8"):
        if not ln.startswith("L "):
            continue
        h, _, t = ln.strip().partition("|")
        f = h.split()
        lid = int(f[1])
        pts = []
        for s in t.strip().split(";"):
            s = s.strip()
            if not s:
                continue
            c = s.split()
            if len(c) >= 3:
                pts.append((float(c[0]), float(c[1]), float(c[2])))
        if len(pts) >= 2:
            lines[lid] = {"pts": pts, "s": pts[0], "e": pts[-1]}
    return lines

def plane(lines):
    zs = [p[2] for d in lines.values() for p in d["pts"]]
    ys = [p[1] for d in lines.values() for p in d["pts"]]
    return (max(zs) - min(zs)) > 1.0 and (max(ys) - min(ys)) < 1.0

def xy_of(use_z, p):
    return (p[0], p[2]) if use_z else (p[0], p[1])

def convex_hull(pts):
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts
    def cr(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lo = []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]

def dist_seg(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    if dx == 0 and dy == 0:
        return math.hypot(p[0]-a[0], p[1]-a[1])
    t = ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / (dx*dx + dy*dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0]-(a[0]+t*dx), p[1]-(a[1]+t*dy))

def linelen(P):
    return sum(math.hypot(P[i+1][0]-P[i][0], P[i+1][1]-P[i][1]) for i in range(len(P)-1))

def weld(lines, use_z):
    parent = {}
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    nodes = {}
    nid = [0]
    def gn(p):
        for k, v in nodes.items():
            if abs(k[0]-p[0]) < WELD and abs(k[1]-p[1]) < WELD:
                return v
        v = nid[0]; nid[0] += 1
        nodes[p] = v
        parent[v] = v
        return v
    nl = defaultdict(list)
    for lid, d in lines.items():
        a = gn(xy_of(use_z, d["s"])); b = gn(xy_of(use_z, d["e"]))
        union(a, b)
        nl[a].append(lid); nl[b].append(lid)
    lp = {i: i for i in lines}
    def lf(a):
        while lp[a] != a:
            lp[a] = lp[lp[a]]; a = lp[a]
        return a
    def lu(a, b):
        ra, rb = lf(a), lf(b)
        if ra != rb:
            lp[ra] = rb
    for k, v in nl.items():
        for i in range(1, len(v)):
            lu(v[0], v[i])
    comp = defaultdict(list)
    for lid in lines:
        comp[lf(lid)].append(lid)
    return comp

def tangent(P, at_start):
    if at_start:
        a, b = P[0], P[min(3, len(P)-1)]
    else:
        a, b = P[max(0, len(P)-4)], P[-1]
    d = (b[0]-a[0], b[1]-a[1])
    n = math.hypot(*d)
    return (d[0]/n, d[1]/n) if n > 1e-9 else (0.0, 0.0)

def dot_tangent(Pa, sa, Pb, sb):
    ta = tangent(Pa, sa == "s")
    tb = tangent(Pb, sb == "s")
    if sa == sb:
        return -ta[0]*tb[0] - ta[1]*tb[1]
    return ta[0]*tb[0] + ta[1]*tb[1]

def compute_features(workdir):
    global W, OUT
    W = workdir
    OUT = W + "/out"
    lines = load_lines(workdir)
    use_z = plane(lines)
    P2 = {lid: [xy_of(use_z, p) for p in d["pts"]] for lid, d in lines.items()}

    allp = [p for P in P2.values() for p in P]
    gx = sum(p[0] for p in allp)/len(allp)
    gy = sum(p[1] for p in allp)/len(allp)
    gc = (gx, gy)
    gmaxr = max(math.hypot(p[0]-gc[0], p[1]-gc[1]) for p in allp)
    hull = convex_hull(allp)
    def dist_hull(p):
        return min(dist_seg(p, hull[i], hull[(i+1) % len(hull)]) for i in range(len(hull)))
    xmin = min(p[0] for p in allp); xmax = max(p[0] for p in allp)
    ymin = min(p[1] for p in allp); ymax = max(p[1] for p in allp)
    maxlen = max(linelen(P) for P in P2.values())

    comp = weld(lines, use_z)
    comp_size = {lid: len(c) for c in comp.values() for lid in c}

    nodes = {}
    def gn(p):
        for k, v in nodes.items():
            if abs(k[0]-p[0]) < WELD and abs(k[1]-p[1]) < WELD:
                return v
        v = len(nodes); nodes[p] = v
        return v
    ep_node = {}
    for lid, P in P2.items():
        ep_node[(lid, "s")] = gn(P[0]); ep_node[(lid, "e")] = gn(P[-1])
    node_lines = defaultdict(list)
    for (lid, e), nid in ep_node.items():
        node_lines[nid].append((lid, e))
    n_tan = {}
    for lid, P in P2.items():
        cnt = 0
        for e in ("s", "e"):
            ni = ep_node[(lid, e)]
            for (lid2, e2) in node_lines[ni]:
                if lid2 == lid:
                    continue
                if dot_tangent(P2[lid], e, P2[lid2], e2) > 0.7:
                    cnt += 1
        n_tan[lid] = cnt

    long_lines = [l for l in lines if linelen(P2[l]) >= LONG]
    ang_r = defaultdict(list)
    for l in long_lines:
        P = P2[l]
        mx = sum(p[0] for p in P)/len(P); my = sum(p[1] for p in P)/len(P)
        th = math.atan2(my-gc[1], mx-gc[0])
        R = max(math.hypot(p[0]-gc[0], p[1]-gc[1]) for p in P)
        ang_r[th].append((l, R))
    shell_rank = {}
    for l in long_lines:
        P = P2[l]
        mx = sum(p[0] for p in P)/len(P); my = sum(p[1] for p in P)/len(P)
        th = math.atan2(my-gc[1], mx-gc[0])
        R = max(math.hypot(p[0]-gc[0], p[1]-gc[1]) for p in P)
        Rs = []
        for t2, lst in ang_r.items():
            if abs(((t2-th+math.pi) % (2*math.pi)) - math.pi) <= math.radians(15):
                Rs.extend(r for _, r in lst)
        Rs = sorted(set(Rs), reverse=True)
        rank = Rs.index(R) if R in Rs else len(Rs)
        shell_rank[l] = rank / max(1, len(Rs)-1) if len(Rs) > 1 else 0.0

    feats = {}
    for lid, d in lines.items():
        P = P2[lid]
        L = linelen(P)
        xs = [p[0] for p in P]; ys = [p[1] for p in P]
        w = max(xs)-min(xs); h = max(ys)-min(ys)
        mx = sum(xs)/len(xs); my = sum(ys)/len(ys)
        maxr = max(math.hypot(p[0]-gc[0], p[1]-gc[1]) for p in P)
        midr = math.hypot(mx-gc[0], my-gc[1])
        minr = min(math.hypot(p[0]-gc[0], p[1]-gc[1]) for p in P)
        dh = min(dist_hull(p) for p in P)
        asp = max(w, h)/max(1.0, min(w, h))
        closed = math.hypot(P[0][0]-P[-1][0], P[0][1]-P[-1][1]) < WELD
        cxn = 2*(mx-gx)/(xmax-xmin)
        cyn = 2*(my-gy)/(ymax-ymin)
        ang = math.atan2(my-gc[1], mx-gc[0])
        is_long = 1 if L >= LONG else 0
        feats[lid] = {
            "len_n": L/maxlen,
            "maxr_n": maxr/gmaxr,
            "midr_n": midr/gmaxr,
            "minr_n": minr/gmaxr,
            "dhull_n": dh/gmaxr,
            "onhull": 1 if dh < 3.0 else 0,
            "aspect": math.log10(asp+1),
            "closed": 1 if closed else 0,
            "comp_size_n": math.log10(comp_size[lid]+1),
            "cx_n": cxn, "cy_n": cyn,
            "sin_ang": math.sin(ang), "cos_ang": math.cos(ang),
            "is_long": is_long,
            "shell_rank": shell_rank.get(lid, 1.0),
            "n_tan": n_tan[lid],
            "w_n": w/gmaxr, "h_n": h/gmaxr,
            "npts": len(P),
        }

    meta = {"use_z": use_z, "centroid": gc, "gmaxr": gmaxr,
            "bbox": [xmin, xmax, ymin, ymax], "n_lines": len(lines), "LONG": LONG,
            "feature_order": list(next(iter(feats.values())).keys())}
    return meta, feats

def main():
    meta, feats = compute_features(W)
    print("plane:", "X-Z" if meta["use_z"] else "X-Y", "lines:", meta["n_lines"],
          "; gmaxr=%.1f" % meta["gmaxr"])
    json.dump({"__meta__": meta, "features": {str(k): v for k, v in feats.items()}},
              open(OUT + "/features.json", "w"))
    print("wrote features.json with", len(feats), "lines")

if __name__ == "__main__":
    main()
