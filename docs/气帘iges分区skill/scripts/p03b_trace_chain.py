"""Full tangent-continuous chain tracer: follow a seed line through junctions,
report ordered chain + gap sizes at each breakpoint."""
import json, os, sys
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

def nbrs(lid, end, tol=12.0, tangent=True):
    """all lines with an end within tol of feat[lid][end]; tangent filter optional"""
    e = feat[lid][end]
    mine = feat[lid]["ts"] if end == "sp" else feat[lid]["te"]
    out = []
    for o, d in feat.items():
        if o == lid:
            continue
        for oe in ("sp", "ep"):
            p = d[oe]
            dist = ((p[0]-e[0])**2 + (p[1]-e[1])**2) ** 0.5
            if dist < tol:
                tt = d["ts"] if oe == "sp" else d["te"]
                dot = tt[0]*mine[0] + tt[1]*mine[1]
                out.append((dist, o, oe, dot))
    out.sort()
    return out

def trace(seed, direction="sp", maxn=60, tol=12.0):
    """walk tangent-continuous chain; report every step incl. gaps"""
    chain = [seed]
    cur, end = seed, direction
    steps = []
    for _ in range(maxn):
        cands = [c for c in nbrs(cur, end, tol) if c[1] not in chain and c[3] < -0.98]
        if not cands:
            # allow non-tangent but close (corner)
            cands = [c for c in nbrs(cur, end, tol) if c[1] not in chain]
            if not cands:
                steps.append(("DEADEND", cur, end, None, None, None))
                break
        dist, o, oe, dot = cands[0]
        steps.append(("STEP", cur, end, o, dist, dot))
        chain.append(o)
        cur = o
        end = "sp" if oe == "ep" else "ep"
    return chain, steps

def show(seed):
    print(f"\n########## trace from L{seed} ({CLS.get(seed)}) ##########")
    chain, steps = trace(seed)
    for kind, cur, end, o, dist, dot in steps:
        if kind == "DEADEND":
            e = feat[cur][end]
            print(f"  DEAD END at L{cur}.{end} ({e[0]:.2f},{e[1]:.2f})")
        else:
            e = feat[cur][end]
            p = feat[o]["sp"] if o else None
            oe_ = None
            print(f"  L{cur}.{end} ({e[0]:8.2f},{e[1]:8.2f}) -> L{o:<4d} gap={dist:6.2f} "
                  f"dot={dot:6.3f} [{CLS.get(o)}]")
    print(f"  chain ({len(chain)}): {chain}")

for s in [int(x) for x in sys.argv[1:]]:
    show(s)
