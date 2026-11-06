#!/usr/bin/env python
"""Measure the curtain's through-thickness (normal-direction) expansion from d3plot.

Why this exists: a curtain cushion is modelled as two shell sheets (one facing the
occupant, one facing the door). Every physical material point therefore appears twice,
once per sheet. Pairing those two nodes and taking their separation gives the local
inflated thickness - the same quantity the reference IC-Coverage report calls
"IC Thickness @ Head Barycenter".

Requires lasso-python (ships with the lspp-mcp env):
    C:/Users/hekie/.workbuddy/binaries/python/envs/lspp-mcp/Scripts/python.exe

Usage
    python g14_thickness.py --d3plot run/d3plot --out out/
    python g14_thickness.py --d3plot run/d3plot --points heads.json \
        --dx -1500 --dz -625 --t-main 160 --t-early 120 --figures --out out/

    # inverse mode: no known frame shift, solve one that reproduces the target
    # thickness values carried in heads.json ("thk" field)
    python g14_thickness.py --d3plot run/d3plot --points heads.json --solve-translation --out out/

Outputs
    <out>/thickness_summary.json   per-state max / p95 / median, pairing diagnostics
    <out>/thickness_points.json    per-point values at the requested times + full curves
    <out>/fig_thk_field.png        thickness contour with the sample points (with --figures)
    <out>/fig_thk_curves.png       thickness vs time (with --figures)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


# --------------------------------------------------------------- d3plot access


def dump_json(obj, path: Path) -> None:
    """json.dump that tolerates numpy scalars, which lasso hands back everywhere."""
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False,
                   default=lambda o: o.item() if hasattr(o, "item") else str(o)),
        encoding="utf-8",
    )


def open_d3plot(path: str):
    import lasso.dyna as ld

    db = ld.D3plot(path)
    at = ld.ArrayType
    data = {
        "c0": db.arrays[at.node_coordinates].astype(np.float64),
        "disp": db.arrays[at.node_displacement].astype(np.float64),
        "times": db.arrays[at.global_timesteps].astype(np.float64),
        "conn": db.arrays[at.element_shell_node_indexes],
        "pidx": db.arrays[at.element_shell_part_indexes],
        "part_ids": db.arrays[at.part_ids],
        "titles": [t.decode(errors="replace").strip() for t in db.arrays[at.part_titles]],
    }
    return data


def resolve_part_index(data, name: str | None, index: int | None) -> tuple[int, str]:
    titles = data["titles"]
    if index is not None:
        return index, titles[index] if index < len(titles) else "?"
    if not name:
        raise SystemExit("pass --part-name (e.g. CAVITY) or --part-index")
    hits = [i for i, t in enumerate(titles) if name.upper() in t.upper()]
    if not hits:
        listing = ", ".join(f"{i}:{t}" for i, t in enumerate(titles))
        raise SystemExit(f"part name {name!r} not found in d3plot. Parts: {listing}")
    return hits[0], titles[hits[0]]


def pair_sheets(c0, conn, pidx, part_index: int, tol: float = 0.01):
    """Pair the two sheets by identical (x, z) in the undeformed state.

    Returns (ia, ib) node indices plus a diagnostic dict. Pairing on the undeformed
    state is the whole trick: once inflated the two sheets no longer share (x, z).
    """
    nodes = np.unique(conn[pidx == part_index])
    p = c0[nodes]
    key = np.round(np.stack([p[:, 0], p[:, 2]], axis=1), 2)
    order = np.lexsort((p[:, 1], key[:, 1], key[:, 0]))
    ks, ids = key[order], nodes[order]
    same = np.all(np.abs(ks[1:] - ks[:-1]) <= tol, axis=1)
    ia, ib = ids[:-1][same], ids[1:][same]
    t0 = np.abs(c0[ia, 1] - c0[ib, 1]) if len(ia) else np.array([])
    diag = {
        "part_index": part_index,
        "shell_nodes": int(len(nodes)),
        "paired_points": int(len(ia)),
        "pairing_ratio_pct": round(100.0 * len(ia) / max(len(nodes), 1), 1),
        "initial_thickness_mm": [round(float(t0.min()), 3), round(float(t0.max()), 3)] if len(t0) else None,
        "initial_thickness_note": "should be a few mm at most; a large spread means the pairing is wrong",
    }
    return ia, ib, diag


def thickness(disp_state, c0, ia, ib):
    y = c0[:, 1] + disp_state[:, 1]
    return np.abs(y[ia] - y[ib])


def lookup(x0, z0, thk, xq, zq, k=4):
    d2 = (x0 - xq) ** 2 + (z0 - zq) ** 2
    idx = np.argpartition(d2, min(k, len(d2) - 1))[:k]
    w = 1.0 / np.maximum(d2[idx], 1e-6)
    return float(np.sum(thk[idx] * w) / np.sum(w)), float(np.sqrt(d2[idx].min()))


# --------------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--d3plot", required=True)
    ap.add_argument("--out", default=".")
    ap.add_argument("--part-name", default="CAVITY", help="substring of the inflated-chamber part title")
    ap.add_argument("--part-index", type=int, help="override the part index (see the printed part list)")
    ap.add_argument("--times", nargs="*", type=float, help="times to report (ms, model time)")
    ap.add_argument("--t-main", type=float, default=160.0, help="reference state for figures / comparison")
    ap.add_argument("--t-early", type=float, default=120.0, help="secondary state (deployment in progress)")
    ap.add_argument("--tdet", type=float, default=0.0, help="detonation time in ms; shifts the 'since ignition' annotation")
    ap.add_argument("--points", help="JSON head barycentres, optional 'thk' target per point")
    ap.add_argument("--dx", type=float, default=0.0)
    ap.add_argument("--dz", type=float, default=0.0)
    ap.add_argument("--solve-translation", action="store_true",
                    help="search dx/dz minimising |thickness - target| (needs 'thk' in --points)")
    ap.add_argument("--figures", action="store_true")
    ap.add_argument("--pair-tol", type=float, default=0.01)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = open_d3plot(args.d3plot)
    c0, disp, times = data["c0"], data["disp"], data["times"]
    part_index, part_title = resolve_part_index(data, args.part_name, args.part_index)
    ia, ib, diag = pair_sheets(c0, data["conn"], data["pidx"], part_index, args.pair_tol)
    if len(ia) == 0:
        listing = ", ".join(f"{i}:{t}" for i, t in enumerate(data["titles"]))
        raise SystemExit(f"no sheet pairs found in part {part_index} ({part_title}). Parts: {listing}")
    print(f"d3plot: {args.d3plot}")
    print(f"part  : {part_index} = {part_title}  paired {diag['paired_points']} / {diag['shell_nodes']} nodes "
          f"({diag['pairing_ratio_pct']}%), initial thickness {diag['initial_thickness_mm']} mm")
    print(f"states: {len(times)}  t = {times[0]:.1f} .. {times[-1]:.1f} ms")

    x0, z0 = c0[ia, 0], c0[ia, 2]

    # ---- per-state summary
    report_times = sorted({float(t) for t in (list(args.times or []) + [args.t_early, args.t_main])})
    summary = {
        "d3plot": args.d3plot,
        "part": {"index": part_index, "title": part_title},
        "pairing": diag,
        "n_states": int(len(times)),
        "time_range_ms": [round(float(times[0]), 2), round(float(times[-1]), 2)],
        "states": {},
    }
    for t_t in report_times:
        s = int(np.argmin(np.abs(times - t_t)))
        thk = thickness(disp[s], c0, ia, ib)
        summary["states"][f"{times[s]:.1f}"] = {
            "state_index": s + 1,
            "max": round(float(thk.max()), 1),
            "p95": round(float(np.percentile(thk, 95)), 1),
            "median": round(float(np.median(thk)), 1),
            "inflated_share_pct": round(100.0 * float((thk > 0.25 * thk.max()).mean()), 1),
        }

    # ---- sampling at the head points
    points_payload = None
    if args.points:
        raw = json.loads(Path(args.points).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("heads", raw.get("rows", []))
        s_main = int(np.argmin(np.abs(times - args.t_main)))
        s_early = int(np.argmin(np.abs(times - args.t_early)))
        thk_main = thickness(disp[s_main], c0, ia, ib)
        thk_early = thickness(disp[s_early], c0, ia, ib)
        xs = np.array([float(p["x"]) for p in raw])
        zs = np.array([float(p["z"]) for p in raw])
        targets = [p.get("thk") for p in raw]

        dx, dz, solve_err = args.dx, args.dz, None
        if args.solve_translation:
            if any(t is None for t in targets):
                raise SystemExit("--solve-translation needs a 'thk' value on every point")
            best = None
            for cand_dx in np.arange(-1600, 401, 20):
                for cand_dz in np.arange(-600, 401, 20):
                    err = 0.0
                    for xq, zq, tgt in zip(xs + cand_dx, zs + cand_dz, targets):
                        v, dmin = lookup(x0, z0, thk_main, xq, zq, k=3)
                        err += 200.0 if dmin > 120 else abs(v - tgt)
                    if best is None or err < best[0]:
                        best = (err, cand_dx, cand_dz)
            err, dx, dz = best
            for ddx in np.arange(dx - 20, dx + 21, 5):
                for ddz in np.arange(dz - 20, dz + 21, 5):
                    e = 0.0
                    for xq, zq, tgt in zip(xs + ddx, zs + ddz, targets):
                        v, dmin = lookup(x0, z0, thk_main, xq, zq, k=3)
                        e += 200.0 if dmin > 120 else abs(v - tgt)
                    if e < err:
                        err, dx, dz = e, ddx, ddz
            solve_err = round(float(err), 1)
            print(f"solved translation dx={dx:.0f} dz={dz:.0f}  residual {solve_err} mm "
                  f"(mean {solve_err / max(len(raw), 1):.1f})")

        rows, curves = [], {}
        for i, p in enumerate(raw):
            xq, zq = xs[i] + dx, zs[i] + dz
            v_main, gap_main = lookup(x0, z0, thk_main, xq, zq, k=3)
            v_early, _ = lookup(x0, z0, thk_early, xq, zq, k=3)
            curve = []
            for s in range(len(times)):
                v, _ = lookup(x0, z0, thickness(disp[s], c0, ia, ib), xq, zq, k=2)
                curve.append([round(float(times[s]), 1), round(float(v), 1)])
            name = p.get("name", f"PT{i + 1}")
            curves[name] = curve
            rows.append({
                "name": name,
                "source_xyz": [p.get("x"), p.get("y"), p.get("z")],
                "target_thk": p.get("thk"),
                "sample_xz": [round(float(xq), 1), round(float(zq), 1)],
                f"thk_{times[s_early]:.0f}": round(v_early, 1),
                f"thk_{times[s_main]:.0f}": round(v_main, 1),
                "delta_vs_target": round(v_main - p["thk"], 1) if p.get("thk") is not None else None,
                "gap_to_mesh_mm": round(gap_main, 1),
            })
        points_payload = {
            "translation": {"dx": dx, "dz": dz, "solved": bool(args.solve_translation), "residual": solve_err},
            "t_main": float(times[s_main]),
            "t_early": float(times[s_early]),
            "rows": rows,
            "curves": curves,
        }

    s_ref = int(np.argmin(np.abs(times - args.t_main)))
    summary["reference_state"] = {
        "time_ms": round(float(times[s_ref]), 2),
        "state_index": s_ref + 1,
        "max": summary["states"][f"{times[s_ref]:.1f}"]["max"],
        "p95": summary["states"][f"{times[s_ref]:.1f}"]["p95"],
    }
    dump_json(summary, out_dir / "thickness_summary.json")
    for t_key, v in summary["states"].items():
        print(f"  t={t_key:7s} ms  max {v['max']:6.1f}  p95 {v['p95']:6.1f}  median {v['median']:5.1f}  "
              f"inflated {v['inflated_share_pct']:5.1f}%")
    if points_payload:
        dump_json(points_payload, out_dir / "thickness_points.json")
        for r in points_payload["rows"]:
            d = f"  target {r['target_thk']:6.1f}  d {r['delta_vs_target']:+6.1f}" if r["target_thk"] is not None else ""
            print(f"  {r['name']:16s} at ({r['sample_xz'][0]:7.1f},{r['sample_xz'][1]:7.1f}) "
                  f"thk {r['thk_' + format(points_payload['t_main'], '.0f')]:6.1f} mm{d}  gap {r['gap_to_mesh_mm']:5.1f}")

    # ---- figures
    if args.figures:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.rcParams["font.family"] = ["Microsoft YaHei", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

        s_main = int(np.argmin(np.abs(times - args.t_main)))
        thk_main = thickness(disp[s_main], c0, ia, ib)
        fig, ax = plt.subplots(figsize=(15, 6.0), dpi=130)
        keep = thk_main > 2
        sc = ax.scatter(x0[keep], z0[keep], c=thk_main[keep], s=2.2, cmap="turbo",
                        vmin=0, vmax=float(np.percentile(thk_main, 99)), linewidths=0)
        cb = fig.colorbar(sc, ax=ax, fraction=0.022, pad=0.015)
        cb.set_label("thickness (mm)")
        if points_payload:
            for i, r in enumerate(points_payload["rows"]):
                ax.plot(r["sample_xz"][0], r["sample_xz"][1], "o", ms=8, mfc="white", mec="#111", mew=1.6, zorder=6)
                off = (8, 14) if i % 2 == 0 else (8, -22)
                ax.annotate(f"{r['name']}  {r['thk_' + format(points_payload['t_main'], '.0f')]:.0f} mm",
                            (r["sample_xz"][0], r["sample_xz"][1]), textcoords="offset points",
                            xytext=off, fontsize=8.5, color="#111", zorder=7,
                            bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="#BBBBBB", alpha=0.9))
        ax.set_aspect("equal")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Z (mm)")
        ax.set_title(f"Curtain Y-thickness at t = {times[s_main]:.0f} ms "
                     f"({times[s_main] - args.tdet:.0f} ms after ignition)")
        fig.tight_layout()
        fig.savefig(out_dir / "fig_thk_field.png")
        plt.close(fig)

        if points_payload:
            fig2, ax2 = plt.subplots(figsize=(9.6, 4.6), dpi=150)
            colors = ["#005496", "#009FE3", "#E3051B", "#F2A33C", "#7DB03C", "#8A9096"]
            for (name, curve), col in zip(points_payload["curves"].items(), colors):
                ax2.plot([p[0] for p in curve], [p[1] for p in curve], lw=1.9, color=col, label=name)
            if args.tdet > 0:
                ax2.axvline(args.tdet, color="#8A9096", ls="--", lw=1)
                ax2.text(args.tdet + 1, ax2.get_ylim()[1] * 0.92, f"ignition {args.tdet:.0f} ms",
                         fontsize=8, color="#8A9096")
            ax2.set_xlabel("time (ms)")
            ax2.set_ylabel("Y-thickness (mm)")
            ax2.set_title("Thickness history at the head barycentres")
            ax2.grid(alpha=0.15)
            ax2.legend(fontsize=8, frameon=False, ncol=2)
            for side in ("top", "right"):
                ax2.spines[side].set_visible(False)
            fig2.tight_layout()
            fig2.savefig(out_dir / "fig_thk_curves.png")
            plt.close(fig2)

    print(f"\nwritten: {out_dir}")


if __name__ == "__main__":
    main()
