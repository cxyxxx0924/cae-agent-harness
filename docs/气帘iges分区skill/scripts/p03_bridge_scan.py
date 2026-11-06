"""CORRECT tangent-continuity bridge scan.
Two lines X (end E) and Y (end F) are tangent-continuous (smooth join) iff
  (E=='ep') != (F=='ep')  -> dot(tangent_X_at_E, tangent_Y_at_F) ~= +1
  (E=='ep') == (F=='ep')  -> dot ~= -1
A 'bridge' line = a line of class A whose BOTH ends smoothly join lines of class B.
Such a line is likely a ring fragment of B misclassified into A."""
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

cls = json.load(open(os.path.join(OUT, "classify_prev.json"), encoding="utf-8"))["line_comp"]
CLS = {int(k): v for k, v in cls.items()}

TOL = 8.0
def smooth(lid, end, o, oe):
    """is the join between lid@end and o@oe smooth?"""
    e = feat[lid][end]; p = feat[o][oe]
    if abs(e[0]-p[0]) > TOL or abs(e[1]-p[1]) > TOL:
        return False
    mine = feat[lid]["ts"] if end == "sp" else feat[lid]["te"]
    tt = feat[o]["ts"] if oe == "sp" else feat[o]["te"]
    dot = mine[0]*tt[0] + mine[1]*tt[1]
    expect = 1.0 if (end == "ep") != (oe == "ep") else -1.0
    return abs(dot - expect) < 0.02

# neighbours (smooth only)
nbr = defaultdict(list)
for lid in feat:
    for end in ("sp", "ep"):
        for o in feat:
            if o == lid:
                continue
            for oe in ("sp", "ep"):
                if smooth(lid, end, o, oe):
                    nbr[lid].append((end, o, oe))

print("=== bridge lines: class A line smoothly joining class B lines at BOTH ends ===")
for lid in sorted(feat):
    a = CLS.get(lid)
    ends = {}
    for end, o, oe in nbr[lid]:
        b = CLS.get(o)
        if b and b != a:
            ends.setdefault(end, []).append((o, b))
    if len(ends) == 2:
        bs = {b for v in ends.values() for _, b in v}
        if len(bs) == 1:
            b = bs.pop()
            detail = "; ".join(f"{end}: " + ",".join(f"L{o}" for o, _ in v) for end, v in ends.items())
            print(f"  L{lid:<4d} [{a}] L={feat[lid]['L']:8.2f}  bridges -> [{b}]  {detail}")

print("\n=== lines with a smooth neighbour in a different class (one end only) ===")
cnt = defaultdict(int)
for lid in sorted(feat):
    a = CLS.get(lid)
    for end, o, oe in nbr[lid]:
        b = CLS.get(o)
        if b and b != a:
            cnt[(a, b)] += 1
for (a, b), n in sorted(cnt.items()):
    print(f"  {a} -> {b}: {n}")
