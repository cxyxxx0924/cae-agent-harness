#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""G.14.3 气帘评估：从 HyperView 导出的变形几何（dump_hv_nodes 的 JSON）做量化评判。

输入：
  --geom      dump_hv_nodes 产出的 JSON（含每步、每部件的节点 xyz）
  --protect   Protect_Area.k / 评估区域网格（节点坐标，Y 向可忽略）
  --heads     heads.json（头部 CoG 坐标，见 assets/data/heads_r676_example.json）
输出：
  g14_assess.json      全部指标
  fig_region.png       侧视：评估区 + 气帘包络 + 头部落点
  fig_thickness.png    展开厚度图 + 低厚度带（缝线/非充气斑）

判据（G.14.3）：
  a) 充气区域间接缝宽度 <= 15 mm
  b) 非充气区域直径 <= 50 mm（等效面积 <= 625*pi mm^2）
  c) 头部落点在充气区、无硬接触/触底

方法说明（必须写进报告）：
  用「双层壳的 Y 向张开量」识别充气/不充气：气腔鼓起处 Y 向张量大（数十至百余 mm），
  缝线与拉带锚点处两层贴合，Y 向张量趋近 0。因此 low-thickness mask（< --thk-low）
  即为「不充气区」，其连通域的宽度/直径就是 a)、b) 两问的可测量代理量。
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


# --------------------------------------------------------------------------- io
def load_nodes(path: Path) -> np.ndarray:
    """Parse *NODE of an LS-DYNA keyword file into an (N,3) array.

    ANSA/Primer decks mix two styles: whitespace separated and fixed width
    (I8 + 3*E16).  A plain split() silently merges the latter into one token, so
    fall back to column slicing whenever the float conversion fails.
    """
    rows = []
    mode = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("*"):
            mode = line.strip().upper()
            continue
        if mode != "*NODE":
            continue
        # fixed width first (ANSA / Primer emit I8 + 3*E16, and split() merges
        # "110.1333.90" style columns into one unusable token)
        if len(line) >= 48:
            try:
                rows.append([float(line[8:24]), float(line[24:40]), float(line[40:56])])
                continue
            except ValueError:
                pass
        p = line.replace("\t", " ").split()
        if len(p) >= 4:
            try:
                rows.append([float(p[1]), float(p[2]), float(p[3])])
            except ValueError:
                continue
    return np.asarray(rows, dtype=float)


def load_geom(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    sims = [str(s) for s in data["simulations"]]
    geo = {}
    for s in sims:
        geo[s] = {int(pid): np.asarray(v, dtype=float) for pid, v in data["geometry"][s].items()}
    return data, geo


def load_glb_cloud(path: Path) -> np.ndarray:
    """GLB exported by HyperView (ExportModelGLB) → model coordinates.

    HyperView writes the viewer frame: glbX = X, glbY = Z, glbZ = Y (+const).
    The constant offset does not matter: every quantity below is either an X-Z
    position or a Y *spread*.
    """
    import sys
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    from parse_glb import load_glb

    meshes = load_glb(path)
    pts = np.vstack([p for p in meshes.values() if len(p)])
    return np.column_stack([pts[:, 0], pts[:, 2], pts[:, 1]])


# ------------------------------------------------------------------ raster utils
def rasterize(points_xz: np.ndarray, origin, shape, cell: float, radius: float = 0.0) -> np.ndarray:
    """Binary mask of points (XZ) with an optional disk dilation of `radius` mm."""
    nx, ny = shape
    mask = np.zeros(shape, dtype=bool)
    ix = np.floor((points_xz[:, 0] - origin[0]) / cell).astype(int)
    iy = np.floor((points_xz[:, 1] - origin[1]) / cell).astype(int)
    ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    mask[ix[ok], iy[ok]] = True
    if radius > 0:
        mask = dilate(mask, int(math.ceil(radius / cell)))
    return mask


def dilate(mask: np.ndarray, steps: int) -> np.ndarray:
    if steps <= 0:
        return mask.copy()
    try:
        from scipy import ndimage
        return ndimage.binary_dilation(mask, iterations=steps)
    except Exception:  # noqa: BLE001
        out = mask.copy()
        for _ in range(steps):
            grown = out.copy()
            grown[1:, :] |= out[:-1, :]
            grown[:-1, :] |= out[1:, :]
            grown[:, 1:] |= out[:, :-1]
            grown[:, :-1] |= out[:, 1:]
            out = grown
        return out


def fill_mask(mask: np.ndarray, steps: int = 3) -> np.ndarray:
    """Close + fill holes so a node cloud (or a closed outline) becomes a solid area."""
    try:
        from scipy import ndimage
        m = ndimage.binary_closing(mask, iterations=max(1, steps))
        return ndimage.binary_fill_holes(m)
    except Exception:  # noqa: BLE001
        m = dilate(mask, steps)
        m = ~dilate(~m, steps)
        return m


def label(mask: np.ndarray):
    """4-connected component labelling."""
    try:
        from scipy import ndimage
        lab, n = ndimage.label(mask)
        return lab, n
    except Exception:  # noqa: BLE001
        h, w = mask.shape
        lab = np.zeros((h, w), dtype=int)
        cur = 0
        for i in range(h):
            for j in range(w):
                if mask[i, j] and lab[i, j] == 0:
                    cur += 1
                    stack = [(i, j)]
                    lab[i, j] = cur
                    while stack:
                        a, b = stack.pop()
                        for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            x, y = a + da, b + db
                            if 0 <= x < h and 0 <= y < w and mask[x, y] and lab[x, y] == 0:
                                lab[x, y] = cur
                                stack.append((x, y))
        return lab, cur


def band_width(area: float, perimeter: float) -> float:
    """Width of a long thin band: area ~= L*w, perimeter ~= 2L  ->  w ~= 2A/P."""
    if perimeter <= 0:
        return 0.0
    return 2.0 * area / perimeter


def perimeter_of(mask: np.ndarray) -> int:
    p = 0
    h, w = mask.shape
    for i in range(h):
        for j in range(w):
            if not mask[i, j]:
                continue
            for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                x, y = i + da, j + db
                if x < 0 or y < 0 or x >= h or y >= w or not mask[x, y]:
                    p += 1
    return p


def equivalent_diameter(area_mm2: float) -> float:
    return 2.0 * math.sqrt(max(area_mm2, 0.0) / math.pi)


# ------------------------------------------------------------------- thickness
def thickness_field(curtain: np.ndarray, cell: float, origin, shape, radius: float = 6.0,
                    block: int = 3):
    """Y-spread of curtain nodes per XZ cell (deployment thickness).

    `block` aggregates over block×block cells before upsampling: a 2 mm cell of a
    4 mm shell mesh holds ~0.4 nodes, so a raw per-cell min/max would report
    zero thickness almost everywhere and fake "non-inflated" blotches.
    """
    nx, ny = shape
    step = cell * block
    bx = int(nx / block) + 2
    by = int(ny / block) + 2
    ix = np.floor((curtain[:, 0] - origin[0]) / step).astype(int)
    iy = np.floor((curtain[:, 2] - origin[1]) / step).astype(int)
    ok = (ix >= 0) & (ix < bx) & (iy >= 0) & (iy < by)
    ix, iy, y = ix[ok], iy[ok], curtain[ok, 1]
    ymin = np.full((bx, by), np.inf)
    ymax = np.full((bx, by), -np.inf)
    cnt = np.zeros((bx, by), dtype=int)
    np.minimum.at(ymin, (ix, iy), y)
    np.maximum.at(ymax, (ix, iy), y)
    np.add.at(cnt, (ix, iy), 1)
    coarse = np.where(cnt > 0, ymax - ymin, 0.0)
    # grow by one coarse cell so a chamber edge does not read as a seam
    grown = coarse.copy()
    for _ in range(1):
        g = grown.copy()
        g[1:, :] = np.maximum(g[1:, :], grown[:-1, :])
        g[:-1, :] = np.maximum(g[:-1, :], grown[1:, :])
        g[:, 1:] = np.maximum(g[:, 1:], grown[:, :-1])
        g[:, :-1] = np.maximum(g[:, :-1], grown[:, 1:])
        grown = g
    filled = np.repeat(np.repeat(grown, block, axis=0), block, axis=1)[:nx, :ny]
    cnt_full = np.repeat(np.repeat(cnt, block, axis=0), block, axis=1)[:nx, :ny]
    return filled, filled, cnt_full


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geom", default="", help="dump_hv_nodes JSON")
    ap.add_argument("--glb", default="", help="ExportModelGLB output (preferred: one call, seconds)")
    ap.add_argument("--protect", required=True)
    ap.add_argument("--out", default="out")
    ap.add_argument("--sim", default=None, help="simulation id (default: last)")
    ap.add_argument("--curtain-parts", default="", help="comma separated part ids")
    ap.add_argument("--cell", type=float, default=2.0)
    ap.add_argument("--thk-low", type=float, default=3.0,
                    help="Y-spread below this is treated as non-inflated (mm)")
    ap.add_argument("--cavity-thk", type=float, default=30.0,
                    help="Y-spread above this counts as inflated cavity (mm)")
    ap.add_argument("--dilate", type=float, default=8.0)
    ap.add_argument("--heads", default="")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    curtain_ids: list[int] = []
    if args.glb:
        curtain = load_glb_cloud(Path(args.glb))
        meta = {"source": args.glb, "simulations": ["last"], "parts": []}
        sim = "last"
        parts = {}
    else:
        if not args.geom:
            raise SystemExit("give --glb or --geom")
        meta, geo = load_geom(Path(args.geom))
        sim = args.sim or str(meta["simulations"][-1])
        if sim not in geo:
            raise SystemExit(f"sim {sim} not in geom, available: {list(geo)}")

        parts = {p["id"]: p for p in meta["parts"]}
        if args.curtain_parts:
            curtain_ids = [int(x) for x in args.curtain_parts.split(",") if x.strip()]
        else:
            curtain_ids = [p["id"] for p in meta["parts"] if p.get("bbox")]
        missing = [p for p in curtain_ids if p not in geo[sim]]
        if missing:
            raise SystemExit(f"parts {missing} have no geometry at sim {sim}")

        curtain = np.vstack([geo[sim][pid] for pid in curtain_ids])
    region = load_nodes(Path(args.protect))

    # only the assessment region matters; clipping keeps the raster small
    pad = 40.0
    rlo = region[:, [0, 2]].min(0) - pad
    rhi = region[:, [0, 2]].max(0) + pad
    keep = ((curtain[:, 0] >= rlo[0]) & (curtain[:, 0] <= rhi[0])
            & (curtain[:, 2] >= rlo[1]) & (curtain[:, 2] <= rhi[1]))
    curtain = curtain[keep]

    cell = args.cell
    lo = np.minimum(region[:, [0, 2]].min(0), curtain[:, [0, 2]].min(0)) - 30
    hi = np.maximum(region[:, [0, 2]].max(0), curtain[:, [0, 2]].max(0)) + 30
    shape = (int((hi[0] - lo[0]) / cell) + 1, int((hi[1] - lo[1]) / cell) + 1)

    reg_mask = fill_mask(rasterize(region[:, [0, 2]], lo, shape, cell), 2)
    cur_mask = dilate(rasterize(curtain[:, [0, 2]], lo, shape, cell), int(round(args.dilate / cell)))
    thk, thk_fill, cnt = thickness_field(curtain, cell, lo, shape, radius=6.0)

    cavity = cur_mask & (thk_fill >= args.cavity_thk)
    # cushion envelope = filled cavity outline; the thin body structure (rails,
    # pillars, door) also reads as "thin", so non-inflated areas are only counted
    # inside the inflated envelope — the same exclusion the regulation makes for
    # roof rail / B-pillar / C-pillar / beltline.
    envelope = fill_mask(cavity, 2)
    noninfl = cur_mask & (thk_fill < args.thk_low) & envelope
    inside_noninfl = noninfl & reg_mask

    reg_area = float(reg_mask.sum()) * cell * cell
    cov_area = float((reg_mask & cur_mask).sum()) * cell * cell
    cav_area = float((reg_mask & cavity).sum()) * cell * cell

    # non-inflated blobs inside the assessment region
    lab, n = label(inside_noninfl)
    blobs = []
    for k in range(1, n + 1):
        m = lab == k
        a = float(m.sum()) * cell * cell
        if a < 4.0 * cell * cell:      # ignore raster noise
            continue
        p = perimeter_of(m) * cell
        blobs.append({
            "area_mm2": round(a, 1),
            "equiv_diameter_mm": round(equivalent_diameter(a), 2),
            "band_width_mm": round(band_width(a, p), 2),
            "perimeter_mm": round(p, 1),
        })
    blobs.sort(key=lambda b: b["area_mm2"], reverse=True)

    res = {
        "sim": sim,
        "curtain_parts": curtain_ids,
        "curtain_nodes": int(len(curtain)),
        "cell_mm": cell,
        "thresholds": {"thk_low": args.thk_low, "cavity_thk": args.cavity_thk,
                       "dilate": args.dilate},
        "curtain_bbox": [round(float(v), 1) for v in
                         [curtain[:, 0].min(), curtain[:, 1].min(), curtain[:, 2].min(),
                          curtain[:, 0].max(), curtain[:, 1].max(), curtain[:, 2].max()]],
        "region_bbox": [round(float(v), 1) for v in
                        [region[:, 0].min(), region[:, 2].min(),
                         region[:, 0].max(), region[:, 2].max()]],
        "region_area_mm2": round(reg_area, 0),
        "covered_area_mm2": round(cov_area, 0),
        "coverage_pct": round(100.0 * cov_area / reg_area, 1) if reg_area else None,
        "cavity_covered_pct": round(100.0 * cav_area / reg_area, 1) if reg_area else None,
        "thickness_max_mm": round(float(np.nanmax(thk_fill)), 1),
        "noninflated_blobs": blobs[:12],
        "noninflated_max_diameter_mm": blobs[0]["equiv_diameter_mm"] if blobs else 0.0,
        "noninflated_max_band_mm": max((b["band_width_mm"] for b in blobs), default=0.0),
    }

    # head points -> distance to the inflated cavity + local thickness
    if args.heads:
        heads = json.loads(Path(args.heads).read_text(encoding="utf-8"))
        items = heads if isinstance(heads, list) else heads.get("heads", [])
        hci = np.floor((curtain[:, 0] - lo[0]) / cell).astype(int)
        hcj = np.floor((curtain[:, 2] - lo[1]) / cell).astype(int)
        ok = (hci >= 0) & (hci < shape[0]) & (hcj >= 0) & (hcj < shape[1])
        cav_pts = curtain[ok][cavity[hci[ok], hcj[ok]]]
        if len(cav_pts) == 0:
            cav_pts = curtain
        hres = []
        for h in items:
            p = np.array(h["cog"], dtype=float)
            d = np.linalg.norm(cav_pts - p, axis=1)
            nearest = cav_pts[int(np.argmin(d))]
            ix = min(max(int((nearest[0] - lo[0]) / cell), 0), shape[0] - 1)
            iy = min(max(int((nearest[2] - lo[1]) / cell), 0), shape[1] - 1)
            hres.append({
                "name": h.get("name", ""),
                "cog": [round(v, 1) for v in p.tolist()],
                "dist_to_cavity_mm": round(float(d.min()), 1),
                "nearest_cavity_point": [round(v, 1) for v in nearest.tolist()],
                "thickness_at_head_mm": round(float(thk_fill[ix, iy]), 1),
                "in_region": bool(reg_mask[ix, iy]),
                "in_cavity": bool(cavity[ix, iy]),
            })
        res["heads"] = hres

    (out / "g14_assess.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                        encoding="utf-8")

    # ---------------------------------------------------------------- figures
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch

        ext = [lo[0], lo[0] + shape[0] * cell, lo[1], lo[1] + shape[1] * cell]
        fig, ax = plt.subplots(figsize=(13, 6.2), dpi=150)
        ax.imshow(np.where(cavity, 1.0, np.nan).T, origin="lower", extent=ext,
                  cmap=matplotlib.colors.ListedColormap(["#E3051B"]), vmin=0, vmax=1,
                  alpha=0.55, interpolation="nearest")
        ax.imshow(np.where(reg_mask, 1.0, np.nan).T, origin="lower", extent=ext,
                  cmap=matplotlib.colors.ListedColormap(["#005496"]), vmin=0, vmax=1,
                  alpha=0.18, interpolation="nearest")
        ax.contour(reg_mask.T.astype(float), levels=[0.5], extent=ext,
                   colors="#005496", linewidths=1.6, origin="lower")
        ax.scatter(region[:, 0], region[:, 2], s=1, c="#005496", alpha=0.30)
        if args.heads:
            for h in res.get("heads", []):
                ax.plot(h["cog"][0], h["cog"][2], "o", ms=9, mfc="#FBBB21",
                        mec="#000000", mew=1.0)
                ax.annotate(h["name"], (h["cog"][0], h["cog"][2]),
                            textcoords="offset points", xytext=(8, 6), fontsize=8)
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Z (mm)")
        ax.set_title(f"G.14.3 assessment region vs inflated cushion  (sim {sim})", fontsize=11)
        ax.legend(handles=[
            Patch(color="#005496", alpha=0.35, label="Assessment region (Fig. G.3)"),
            Patch(color="#E3051B", alpha=0.65,
                  label=f"Inflated cavity, Y-spread >= {args.cavity_thk:.0f} mm"),
        ], loc="upper left", fontsize=8)
        ax.set_aspect("equal")
        fig.tight_layout()
        fig.savefig(out / "fig_region.png")
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(13, 6.2), dpi=150)
        show = np.where(cur_mask, thk_fill, np.nan)
        im = ax.imshow(show.T, origin="lower", extent=ext, cmap="turbo", vmin=0, vmax=180)
        ax.contour(inside_noninfl.T.astype(float), levels=[0.5], extent=ext,
                   colors="#000000", linewidths=1.2, origin="lower")
        ax.contour(reg_mask.T.astype(float), levels=[0.5], extent=ext,
                   colors="#005496", linewidths=1.4, origin="lower")
        cb = fig.colorbar(im, ax=ax, shrink=0.85)
        cb.set_label("Y-spread / deployment thickness (mm)")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Z (mm)")
        ax.set_title("Deployment thickness, black contour = non-inflated band", fontsize=11)
        ax.set_aspect("equal")
        fig.tight_layout()
        fig.savefig(out / "fig_thickness.png")
        plt.close(fig)
    except Exception as exc:  # noqa: BLE001
        res["figure_error"] = str(exc)

    print(json.dumps({k: v for k, v in res.items() if k != "noninflated_blobs"},
                     ensure_ascii=False, indent=2))
    print(f"\ntop non-inflated blobs: {len(res['noninflated_blobs'])}")
    for b in res["noninflated_blobs"][:5]:
        print("  ", b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
