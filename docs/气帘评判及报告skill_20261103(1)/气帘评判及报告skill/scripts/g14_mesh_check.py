#!/usr/bin/env python
"""G.14.3.1 geometric screening on a *flat / undeformed* curtain deck.

Answers the three purely-geometric questions of C-NCAP Appendix G:

  1. seam band width      : G.14.3.1.3 a)  <= 15 mm between inflated chambers
  2. non-inflated patches : G.14.3.1.3 b)  diameter <= 50 mm (area <= 625*pi mm^2)
  3. cavity coverage      : G.14.3.1.1    share of the evaluation region that is a
                                           real inflatable chamber rather than seam/belt

Plus a landing classifier used later by the thickness step: is a given (x, z) head
barycentre on an inflated chamber, on a seam, or off the cushion entirely.

Usage
    python g14_mesh_check.py --deck cab1_clean.k --out out/
    python g14_mesh_check.py --deck cab1_clean.k --points heads.json \
        --dx -1500 --dz -625 --out out/
    python g14_mesh_check.py --deck cab1_clean.k --region-x 3000 3164 \
        --region-z 1060 1240 --out out/

`heads.json` is either the export of `g14_heads_from_pptx.py` or a plain list:
    [{"name": "1ROW_WS50@60", "x": 3197.2, "y": -449.4, "z": 1405.2}, ...]

Writes <out>/g14_screening.json and prints a readable summary.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from g14_common import (
    Grid,
    connected_components,
    elem_centroid_area,
    find_parts,
    parse_deck,
    point_in_rounded_rect,
    region_of_g3,
)

# a sample point further than this from every cushion node is treated as off-cushion;
# it is a mesh-resolution tolerance, not a regulation number.
OFF_SURFACE_TOL = 25.0
ON_SEAM_TOL = 3.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deck", required=True, help="curtain deck (.k) containing BELT/CAVITY/SEAM/TETHER parts")
    ap.add_argument("--out", default=".", help="output directory")
    ap.add_argument("--points", help="JSON list of head barycentres (vehicle frame)")
    ap.add_argument("--dx", type=float, default=0.0, help="X shift applied to --points")
    ap.add_argument("--dz", type=float, default=0.0, help="Z shift applied to --points")
    ap.add_argument("--belt-kw", default="BELT")
    ap.add_argument("--cavity-kw", default="CAVITY")
    ap.add_argument("--seam-kw", default="SEAM")
    ap.add_argument("--tether-kw", default="TETHER")
    ap.add_argument("--region-x", nargs=2, type=float, help="explicit evaluation region X range")
    ap.add_argument("--region-z", nargs=2, type=float, help="explicit evaluation region Z range")
    ap.add_argument("--cog5-x", type=float, help="G.3 anchor: 5th-percentile head CoG, X")
    ap.add_argument("--cog5-z", type=float, help="G.3 anchor: 5th-percentile head CoG, Z")
    ap.add_argument("--cog95-z", type=float, help="G.3 anchor: 95th-percentile head CoG, Z")
    ap.add_argument("--region-radius", type=float, default=82.0, help="G.3 corner radius (mm)")
    ap.add_argument("--sample", type=float, default=4.0, help="coverage sampling pitch (mm)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    nodes, elems, parts = parse_deck(args.deck)
    if not elems:
        raise SystemExit("no *ELEMENT_SHELL found in the deck")

    try:
        zone_pid = find_parts(parts, args.belt_kw, args.cavity_kw, args.seam_kw, args.tether_kw)
    except SystemExit as exc:
        raise SystemExit(str(exc))

    cent, area = elem_centroid_area(nodes, elems)
    area_of = {e[0]: a for e, a in zip(elems, area)}
    pid_name = {v: k for k, v in zone_pid.items()}
    result: dict = {
        "source": str(args.deck),
        "parts": {name: pid for name, pid in zone_pid.items()},
        "mesh": {"nodes": len(nodes), "shells": len(elems)},
    }

    # ---------- 1. seam strips ------------------------------------------------
    sub, groups = connected_components(elems, zone_pid["SEAM"])
    strips = []
    for g in groups:
        eids = [sub[i][0] for i in g]
        a = float(sum(area_of[e] for e in eids))
        pts = np.array([nodes[n] for i in g for n in sub[i][1]])
        # band width = area / centreline length, approximated here by the long span of
        # the strip; the exact value comes from the local-window reduction below.
        spans = pts.max(axis=0) - pts.min(axis=0)
        length = float(max(spans[0], spans[2]))
        strips.append({
            "n_elem": len(g),
            "area_mm2": round(a, 1),
            "x": [round(float(pts[:, 0].min()), 1), round(float(pts[:, 0].max()), 1)],
            "z": [round(float(pts[:, 2].min()), 1), round(float(pts[:, 2].max()), 1)],
            "equiv_dia_mm": round(2 * math.sqrt(a / math.pi), 1),
            "width_area_over_length_mm": round(a / length, 2) if length > 1 else None,
        })
    strips.sort(key=lambda s: -s["area_mm2"])
    result["seam_strips"] = {
        "count": len(strips),
        "total_area_mm2": round(sum(s["area_mm2"] for s in strips), 1),
        "all": strips,
    }

    # ---------- 2. modelled seam band width -----------------------------------
    # Node-to-node distance is useless here: a one-element-wide seam row shares all its
    # nodes with the two cavity rows either side, so the distance is 0. Measure instead
    # from each seam centroid outward to the nearest cavity centroid on BOTH sides and
    # add the two distances - that is the width of the non-inflating band.
    def zone_nodes(pid):
        used = sorted({n for _e, p, c in elems if p == pid for n in c})
        return np.array([nodes[n][::2] for n in used])  # (x, z)

    zn = {name: zone_nodes(pid) for name, pid in zone_pid.items()}
    grids = {name: Grid(v) for name, v in zn.items()}

    # Band width per seam element = area / longer side. For a one-row band this returns
    # the element edge itself, which is the honest answer: the mesh width is a modelling
    # choice, not the OPW press width. Anything else (centroid-to-centroid, area over PCA
    # length) breaks on curved strips and reports 15-35 mm for a 5 mm band.
    seam_elems = [(e, c) for e, p, c in elems if p == zone_pid["SEAM"]]
    band_w, elem_area, edge_all = [], [], []
    for e, c in seam_elems:
        P2 = np.array([nodes[n] for n in c])[:, [0, 2]]
        sides = [float(np.linalg.norm(P2[(k + 1) % len(P2)] - P2[k])) for k in range(len(P2))]
        long_side = max(sides)
        edge_all.extend(sides)
        elem_area.append(float(area_of[e]))
        if long_side > 1e-6:
            band_w.append(float(area_of[e]) / long_side)
    band_w = np.array(band_w, dtype=float)
    mean_edge = round(float(np.mean(edge_all)), 2) if edge_all else None
    w_median = round(float(np.median(band_w)), 2) if len(band_w) else None
    rows_across = round(w_median / mean_edge, 2) if (w_median and mean_edge) else None

    # diagnostic: seam node -> nearest cavity node. A one-element seam row shares every
    # node with the neighbouring cavity rows, so most values collapse to 0; the tail is
    # what tells you the seam part also covers a wider stitch/belt area.
    d_node = np.array([grids["CAVITY"].nearest(float(p[0]), float(p[1]))[0] for p in zn["SEAM"]])

    result["seam_band_width"] = {
        "note": (
            "width = element area / longer side, i.e. the modelled width of the non-inflating "
            "band. rows_across ~1 means the band is idealised as a single element row: the mesh "
            "then reproduces whatever width was drawn, so it CANNOT verify the 15 mm limit and "
            "the verdict must stay INDETERMINATE. Measure the real OPW press width on the CAD "
            "flat pattern."
        ),
        "median_mm": w_median,
        "p95_mm": round(float(np.percentile(band_w, 95)), 2) if len(band_w) else None,
        "max_mm": round(float(band_w.max()), 2) if len(band_w) else None,
        "samples": int(len(band_w)),
        "rows_across": rows_across,
        "node_gap_p95_mm": round(float(np.percentile(d_node, 95)), 2) if len(d_node) else None,
        "node_gap_max_mm": round(float(d_node.max()), 2) if len(d_node) else None,
        "mean_element_edge_mm": mean_edge,
        "limit_mm": 15.0,
        "resolvable": bool(rows_across is not None and rows_across >= 2.0),
        "verdict": (
            "INDETERMINATE - band is a single element row, width is a modelling choice"
            if rows_across is None or rows_across < 2.0
            else ("PASS" if float(np.percentile(band_w, 95)) <= 15.0 else "FAIL")
        ),
    }

    # ---------- 3. non-inflated patches ---------------------------------------
    # A compact seam cluster (no extent above 50 mm) is a spot, not a line; only those
    # are subject to the 50 mm / 625*pi mm2 limit.
    patches, line_strips = [], 0
    for s in strips:
        dx = s["x"][1] - s["x"][0]
        dz = s["z"][1] - s["z"][0]
        major, minor = max(dx, dz), min(dx, dz)
        if major <= 50.0:
            patches.append({"x": s["x"], "z": s["z"], "equiv_dia_mm": s["equiv_dia_mm"],
                            "area_mm2": s["area_mm2"], "major_mm": round(major, 1)})
        else:
            line_strips += 1
    result["non_inflated_patches"] = {
        "limit_dia_mm": 50.0,
        "limit_area_mm2": round(625 * math.pi, 1),
        "compact_spots": len(patches),
        "line_strips_excluded": line_strips,
        "count_over_limit": len([p for p in patches if p["equiv_dia_mm"] > 50.0]),
        "max_equiv_dia_mm": round(max((p["equiv_dia_mm"] for p in patches), default=0.0), 1),
        "candidates": patches,
        "note": (
            "spots = seam clusters with no extent above 50 mm. The band width from step 2 is "
            "the real non-inflated width along a joint, so a passing 15 mm band also keeps the "
            "50 mm spot rule satisfied along seams."
        ),
    }

    # ---------- 4. landing classification -------------------------------------
    def classify(x: float, z: float) -> dict:
        res = {"x": round(x, 1), "z": round(z, 1)}
        best = None
        for name, g in grids.items():
            d, _ = g.nearest(x, z)
            res[f"d_{name.lower()}"] = round(d, 1)
            if best is None or d < best[1]:
                best = (name, d)
        res["nearest_zone"] = best[0]
        res["d_surface"] = round(best[1], 1)
        if best[1] > OFF_SURFACE_TOL:
            res["verdict"] = "OUT_OF_CUSHION"
        elif best[0] == "SEAM" or res["d_seam"] < ON_SEAM_TOL:
            res["verdict"] = "ON_SEAM"
        elif best[0] == "CAVITY":
            res["verdict"] = "INFLATED"
        else:
            res["verdict"] = "ON_" + best[0]
        return res

    if args.points:
        raw_points = json.loads(Path(args.points).read_text(encoding="utf-8"))
        if isinstance(raw_points, dict):
            raw_points = raw_points.get("heads", raw_points.get("rows", []))
        landings = []
        for pt in raw_points:
            x, z = float(pt["x"]) + args.dx, float(pt["z"]) + args.dz
            r = classify(x, z)
            r["name"] = pt.get("name", "unnamed")
            r["source_xyz"] = [pt.get("x"), pt.get("y"), pt.get("z")]
            r["shift_applied"] = [args.dx, args.dz]
            landings.append(r)
        result["landing"] = landings

    # ---------- 5. evaluation region & coverage -------------------------------
    region = None
    if args.region_x and args.region_z:
        region = {
            "x": [min(args.region_x), max(args.region_x)],
            "z": [min(args.region_z), max(args.region_z)],
            "radius": args.region_radius,
            "anchor": None,
            "note": "explicit box supplied by the caller",
        }
    elif args.cog5_x is not None and args.cog5_z is not None and args.cog95_z is not None:
        region = region_of_g3(args.cog5_x, args.cog5_z, args.cog95_z, radius=args.region_radius)
        region["anchor"]["derived_from"] = "--cog5-x / --cog5-z / --cog95-z"
    else:
        print("region : skipped - pass --region-x/--region-z, or --cog5-x --cog5-z --cog95-z "
              "to build the G.3 rounded quad")

    if region:
        step = args.sample
        tally = {name: 0 for name in zone_pid}
        tally["OFF_CUSHION"] = 0
        total = 0
        for xx in np.arange(region["x"][0], region["x"][1], step):
            for zz in np.arange(region["z"][0], region["z"][1], step):
                if not point_in_rounded_rect(float(xx), float(zz), region):
                    continue
                total += 1
                best = None
                for name, g in grids.items():
                    d, _ = g.nearest(float(xx), float(zz), max_rings=10)
                    if best is None or d < best[1]:
                        best = (name, d)
                tally["OFF_CUSHION" if best[1] > OFF_SURFACE_TOL else best[0]] += 1
        region["coverage_pct"] = {k: round(100.0 * v / max(total, 1), 1) for k, v in tally.items()}
        region["samples"] = total
        region["inflated_share_pct"] = region["coverage_pct"].get("CAVITY", 0.0)
        result["evaluation_region"] = region

    # ---------- 6. cushion extent ---------------------------------------------
    xz = cent[:, [0, 2]]
    result["cushion_frame"] = {
        "x": [round(float(xz[:, 0].min()), 1), round(float(xz[:, 0].max()), 1)],
        "z": [round(float(xz[:, 1].min()), 1), round(float(xz[:, 1].max()), 1)],
        "y": [round(float(min(p[1] for p in nodes.values())), 1),
              round(float(max(p[1] for p in nodes.values())), 1)],
    }

    (out_dir / "g14_screening.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ---------- console ------------------------------------------------------
    print(f"deck   : {args.deck}")
    print(f"parts  : {zone_pid}")
    print(f"cushion: X {result['cushion_frame']['x']}  Z {result['cushion_frame']['z']}")
    sb = result["seam_band_width"]
    print(f"seam   : {result['seam_strips']['count']} strips, {result['seam_strips']['total_area_mm2']} mm2")
    print(f"         band width median {sb['median_mm']} / p95 {sb['p95_mm']} / max {sb['max_mm']} mm "
          f"over {sb['samples']} seam elements, {sb['rows_across']} element(s) across")
    print(f"         element edge {sb['mean_element_edge_mm']} mm -> 15 mm limit {sb['verdict']}")
    np_ = result["non_inflated_patches"]
    print(f"spots  : {np_['compact_spots']} compact spot(s), {np_['line_strips_excluded']} line strip(s) excluded, "
          f"max equiv dia {np_['max_equiv_dia_mm']} mm (limit 50), over limit: {np_['count_over_limit']}")
    if "evaluation_region" in result:
        reg = result["evaluation_region"]
        print(f"region : X {reg['x']}  Z {reg['z']}  r={reg['radius']}")
        print(f"cover  : {reg['coverage_pct']}")
    for r in result.get("landing", []):
        print(f"  {r['name']:22s} ({r['x']:7.1f},{r['z']:7.1f}) nearest={r['nearest_zone']:8s} "
              f"d={r['d_surface']:7.1f} -> {r['verdict']}")
    print(f"\nwritten: {out_dir / 'g14_screening.json'}")


if __name__ == "__main__":
    main()
