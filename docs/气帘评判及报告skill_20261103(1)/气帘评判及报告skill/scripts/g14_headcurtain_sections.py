#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Section cuts and thickness measurements for the head-vs-curtain evidence.

Everything works on the numpy cache written by g14_build_merged.py:
  * plane cut of the shell mesh  -> segments (no GUI, exact)
  * Y-thickness of the inflated bag at a station
  * shortest distance from a head surface to the bag skin
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

EV = r"E:\work\workbuddy\2026-10-30-20-33-11\CAB_G143_evidence"
NPZ = os.path.join(EV, "heads_vs_curtain.npz")

# head CoG anchors from the regulatory setup (heads.json), X / Z used for cuts
HEAD_COG = {
    "HIII 5F  front":  (1401.5, 120.1, 1089.3),
    "HIII 5F  rear":   (2501.5, 120.1, 1089.3),
    "HIII 95M front":  (1683.3, 124.6, 1255.1),
    "HIII 95M rear":   (2683.3, 124.6, 1205.1),
}


def load():
    z = np.load(NPZ, allow_pickle=True)
    d = {
        "cxyz": z["curtain_nodes_xyz"],
        "celem": z["curtain_elem"],
        "cpid": z["curtain_pid"],
        "heads": {},
    }
    i = 0
    while "head%d_label" % i in z.files:
        d["heads"][str(z["head%d_label" % i][0])] = {
            "xyz": z["head%d_nodes_xyz" % i],
            "elem": z["head%d_elem" % i],
        }
        i += 1
    return d


def quad_faces(xyz, elem):
    """Triangulate quads (a,b,c,d) -> two triangles, degenerate-safe."""
    a, b, c, dd = elem[:, 0], elem[:, 1], elem[:, 2], elem[:, 3]
    t1 = np.stack([a, b, c], axis=1)
    t2 = np.stack([a, c, dd], axis=1)
    tri = np.vstack([t1, t2])
    good = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
    return tri[good]


def plane_segments(pts, tri, axis, value):
    """Intersect a triangle soup with the plane pts[:,axis] == value.

    Returns an (N,2,3) array of segments in 3-D, two per cut triangle.
    """
    d = pts[:, axis] - value
    s = np.sign(d[tri])                 # (F,3)
    tris = tri[np.all(s != 0, axis=1)]
    s = s[np.all(s != 0, axis=1)]
    by_face = {}
    for i, j in ((0, 1), (1, 2), (2, 0)):
        mask = s[:, i] * s[:, j] < 0
        if not mask.any():
            continue
        f = np.nonzero(mask)[0]
        na, nb = tris[f, i], tris[f, j]
        t = (d[na] / (d[na] - d[nb]))[:, None]
        p = pts[na] + t * (pts[nb] - pts[na])
        for k, fi in enumerate(f):
            by_face.setdefault(int(fi), []).append(p[k])
    out = [v[:2] for v in by_face.values() if len(v) >= 2]
    return np.array(out) if out else np.zeros((0, 2, 3))


def thickness_y(pts, tri, x, z, half=12.0):
    """Y-extent of the bag surface in a window around (x, z)."""
    p = pts[tri].reshape(-1, 3)
    m = (np.abs(p[:, 0] - x) < half) & (np.abs(p[:, 2] - z) < half)
    if not m.any():
        return None
    y = p[m, 1]
    return float(y.min()), float(y.max())


def head_distance(pts, head_xyz):
    """Shortest / mean gap from the head skin to the bag skin (KD-tree on bag nodes).

    Node-based, mesh is ~2 mm, so the discretisation bias stays far below the
    values we report.
    """
    from scipy.spatial import cKDTree
    tree = cKDTree(pts)
    dist, _ = tree.query(head_xyz, k=1)
    return float(dist.min()), float(dist.mean())


def main():
    d = load()
    cxyz, celem = d["cxyz"], d["celem"]
    ctri = quad_faces(cxyz, celem)
    print("curtain: %d nodes, %d shells, %d triangles"
          % (len(cxyz), len(celem), len(ctri)))

    result = {"bag": {}, "heads": {}}
    result["bag"]["y_min"] = float(cxyz[:, 1].min())
    result["bag"]["y_max"] = float(cxyz[:, 1].max())
    result["bag"]["x_range"] = [float(cxyz[:, 0].min()), float(cxyz[:, 0].max())]
    result["bag"]["z_range"] = [float(cxyz[:, 2].min()), float(cxyz[:, 2].max())]

    rows = []
    for label, cog in HEAD_COG.items():
        h = d["heads"][label]
        x, y, z = cog
        # YZ section through the head centre; thickness read off that section so
        # the number always matches what the figure shows.
        yz = plane_segments(cxyz, ctri, 0, x)
        pts = yz.reshape(-1, 3)
        band = np.abs(pts[:, 2] - z) < 30.0
        th = (float(pts[band, 1].min()), float(pts[band, 1].max())) if band.sum() > 4 else None
        dmin, dmean = head_distance(cxyz, h["xyz"])
        # XY section at head height
        xy = plane_segments(cxyz, ctri, 2, z)
        rows.append(dict(label=label, cog=[x, y, z],
                         bag_y=th, thickness=(th[1] - th[0]) if th else None,
                         gap_min=dmin, gap_mean=dmean,
                         n_yz=int(len(yz)), n_xy=int(len(xy))))
        result["heads"][label] = rows[-1]
        print("%-16s bag Y %.1f..%.1f  t=%5.1f  gap_min %5.1f  gap_mean %5.1f"
              % (label, th[0], th[1], th[1] - th[0], dmin, dmean))

    with open(os.path.join(EV, "sections.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    print("wrote sections.json")

    # quick debug plot of the 5F front section
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    lab = "HIII 5F  front"
    x = HEAD_COG[lab][0]
    yz = plane_segments(cxyz, ctri, 0, x)
    h = d["heads"][lab]
    hyz = plane_segments(h["xyz"], quad_faces(h["xyz"], h["elem"]), 0, x)
    fig, ax = plt.subplots(figsize=(9, 6))
    for s in yz:
        ax.plot(s[:, 1], s[:, 2], color="#1f4e79", lw=1.0)
    for s in hyz:
        ax.plot(s[:, 1], s[:, 2], color="#c00000", lw=1.2)
    ax.set_aspect("equal")
    ax.set_xlabel("Y (mm)")
    ax.set_ylabel("Z (mm)")
    ax.set_title("debug YZ section at X=%.0f" % x)
    fig.tight_layout()
    fig.savefig(os.path.join(EV, "_debug_yz.png"), dpi=110)
    print("wrote _debug_yz.png", len(yz), "bag segs,", len(hyz), "head segs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
