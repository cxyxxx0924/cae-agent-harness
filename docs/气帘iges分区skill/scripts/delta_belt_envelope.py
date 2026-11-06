# -*- coding: utf-8 -*-
"""DIAGNOSTIC / EXPERIMENTAL — NOT wired into run_auto.sh.

Attempts to implement the user's "最外闭环 = BELT" (outer envelope = BELT) rule
by finding the widest-angular connected component among TETHER/CAVITY lines.

STATUS (2026-10-23): UNRELIABLE. On 5P-BAG the outer envelope is fragmented
(gaps between short segments) so it does NOT weld into one component, and this
rule selects a wrong interior component. It also REGRESSES the accepted newcab
result (reassigns 10 outer-hardware TETHER -> BELT, breaking 721/721).
Conclusion: the outer-envelope vs outer-hardware boundary is a genuine
"语义归人" seam that pure geometry cannot resolve. Left here as a diagnostic
only; default is --dry (no file write). Do NOT rely on it for production.
"""
import os, sys, json, math
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import featurize as F

WELD = F.WELD
DOT_MIN = 0.7          # tangent alignment to chain
MIN_LOOP_LINES = 6     # ignore tiny boss loops

def outermost_envelope_loop(workdir):
    """Among lines the tree labeled TETHER (and any CAVITY that sits on the
    outer shell), weld endpoints and find the single connected component whose
    angular coverage is widest -> that is the bag envelope -> BELT.
    Localized small components (inflator/port) are left as TETHER."""
    meta, feats = F.compute_features(workdir)
    lines = F.load_lines(workdir)
    use_z = meta["use_z"]
    cls = json.load(open(workdir + "/out/classify_final.json"))["line_comp"]
    cand = [l for l in feats if cls.get(str(l)) in ("TETHER", "CAVITY")]
    P2 = {lid: [F.xy_of(use_z, p) for p in d["pts"]] for lid, d in lines.items()}
    # weld endpoints of candidate lines
    nodes = {}
    def gn(p):
        for k, v in nodes.items():
            if abs(k[0]-p[0]) < WELD and abs(k[1]-p[1]) < WELD:
                return v
        v = len(nodes); nodes[p] = v; return v
    ep_node = {}
    for lid in cand:
        P = P2[lid]
        ep_node[(lid, False)] = gn(P[0]); ep_node[(lid, True)] = gn(P[-1])
    parent = {}
    def find(a):
        while parent.get(a, a) != a: a = parent[a] = parent.get(a, a)
        return a
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb
    for k in ep_node.values(): parent.setdefault(k, k)
    nd = defaultdict(list)
    for (l, e), nid in ep_node.items(): nd[nid].append(l)
    for nid, ls in nd.items():
        for i in range(1, len(ls)): union(ls[0], ls[i])
    comp = defaultdict(set)
    for l in cand: comp[find(ep_node[(l, False)])].add(l)
    gc = meta["centroid"]
    best = None
    for cid, ls in comp.items():
        ls = list(ls)
        if len(ls) < MIN_LOOP_LINES:
            continue
        # angular coverage of midpoints around centroid
        angs = [math.degrees(math.atan2(feats[l]["cy_n"], feats[l]["cx_n"])) for l in ls]
        hist = [0]*36
        for a in angs: hist[int((a+180)//10) % 36] += 1
        cover = sum(1 for h in hist if h > 0) * 10
        rm = max(feats[l]["maxr_n"] for l in ls)
        score = (cover, len(ls), rm)
        if best is None or score > best[0]:
            best = (score, ls)
    if best is None:
        return None, []
    return best[0][2], best[1]

def main():
    workdir = sys.argv[1]
    apply = "--apply" in sys.argv[2:]
    rmin, env = outermost_envelope_loop(workdir)
    cls = json.load(open(workdir + "/out/classify_final.json"))
    lc = cls["line_comp"]
    before = defaultdict(int)
    for l in env:
        before[lc.get(str(l), "lines0")] += 1
    print(f"[delta][DIAGNOSTIC only] outermost component: rmin={rmin} n_lines={len(env)}")
    print(f"[delta] would move to BELT: {dict(before)}")
    if not apply:
        print("[delta] DRY RUN (default). This rule is UNRELIABLE — not wired into run_auto.sh.")
        print("[delta] To actually apply, pass --apply AND manually verify the result.")
        return
    moved = 0
    for l in env:
        if lc.get(str(l)) != "BELT":
            lc[str(l)] = "BELT"; moved += 1
    json.dump(cls, open(workdir + "/out/classify_final.json", "w"), indent=1)
    print(f"[delta] APPLIED: moved {moved} lines to BELT (verify visually before trusting)")

if __name__ == "__main__":
    main()
