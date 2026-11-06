"""Shared helpers for the G.14 curtain-airbag screening scripts.

Kept dependency-light (numpy only) so it runs in any Python that can also import
lasso-python (the CAE env) or a plain system Python (mesh-only checks).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------- deck parsing


def parse_deck(path: str | Path):
    """Return (nodes, elems, parts) from an LS-DYNA deck.

    nodes : {nid: (x, y, z)}
    elems : [(eid, pid, [n1..n4])]      shell elements only
    parts : {pid: title}                from *PART, title line above the pid line
    """
    path = Path(path)
    nodes: dict[int, tuple[float, float, float]] = {}
    elems: list[tuple[int, int, list[int]]] = []
    parts: dict[int, str] = {}

    block = None
    pending_title = None
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith("*"):
                block = line.strip().upper()
                pending_title = None
                continue
            if "*INCLUDE" in (block or ""):
                continue
            if not line.strip() or line.lstrip().startswith("$"):
                continue

            if block == "*PART":
                if pending_title is None:
                    pending_title = line.strip()
                else:
                    fields = [f.strip() for f in line.split(",")]
                    if fields and fields[0].isdigit():
                        parts[int(fields[0])] = pending_title
                    pending_title = None
            elif block == "*NODE":
                f = line.split(",")
                try:
                    nodes[int(f[0])] = (float(f[1]), float(f[2]), float(f[3]))
                except (ValueError, IndexError):
                    pass
            elif block == "*ELEMENT_SHELL":
                f = [x.strip() for x in line.split(",")]
                try:
                    elems.append((int(f[0]), int(f[1]), [int(x) for x in f[2:] if x]))
                except ValueError:
                    pass

    return nodes, elems, parts


def find_parts(parts: dict[int, str], *keywords: str) -> dict[int, int]:
    """Map a logical zone name to a part id by substring match on the title.

    `find_parts(parts, "CAVITY", "SEAM")` -> {"CAVITY": 3, "SEAM": 4}
    Matching is case-insensitive; a keyword that hits nothing raises, because a
    silent miss would produce a confidently wrong verdict.
    """
    out: dict[str, int] = {}
    for kw in keywords:
        hits = [pid for pid, name in parts.items() if kw.upper() in (name or "").upper()]
        if not hits:
            raise SystemExit(
                f"part keyword {kw!r} matched no *PART title. Available: "
                + ", ".join(f"{pid}:{name}" for pid, name in sorted(parts.items()))
            )
        out[kw.upper()] = hits[0]
    return out


# ---------------------------------------------------------------- geometry


def elem_centroid_area(nodes, elems):
    cent, area = [], []
    for _eid, _pid, conn in elems:
        pts = np.array([nodes[n] for n in conn], dtype=float)
        a = 0.0
        for k in range(1, len(pts) - 1):
            a += 0.5 * float(np.linalg.norm(np.cross(pts[k] - pts[0], pts[k + 1] - pts[0])))
        cent.append(pts.mean(axis=0))
        area.append(a)
    return np.array(cent), np.array(area)


class Grid:
    """Uniform bucket grid for nearest-neighbour queries on 2-D (x, z) points."""

    def __init__(self, pts: np.ndarray, cell: float = 25.0):
        self.pts = np.asarray(pts, dtype=float)
        self.cell = float(cell)
        self.map: dict[tuple[int, int], list[int]] = {}
        for i, p in enumerate(self.pts):
            k = (int(math.floor(p[0] / self.cell)), int(math.floor(p[1] / self.cell)))
            self.map.setdefault(k, []).append(i)

    def nearest(self, x: float, z: float, max_rings: int = 60):
        cx, cz = int(math.floor(x / self.cell)), int(math.floor(z / self.cell))
        best, best_i, r = float("inf"), -1, 0
        while r <= max_rings:
            for kx in range(cx - r, cx + r + 1):
                for kz in range(cz - r, cz + r + 1):
                    if max(abs(kx - cx), abs(kz - cz)) != r:
                        continue
                    for i in self.map.get((kx, kz), ()):
                        d = (self.pts[i][0] - x) ** 2 + (self.pts[i][1] - z) ** 2
                        if d < best:
                            best, best_i = d, i
            if best_i >= 0 and math.sqrt(best) <= r * self.cell:
                return math.sqrt(best), best_i
            r += 1
        return (math.sqrt(best) if best_i >= 0 else float("inf")), best_i


def connected_components(elems, part_id: int):
    """Union-find over shell elements sharing a node -> list of element-index groups."""
    sub = [(e, conn) for e, p, conn in elems if p == part_id]
    parent = list(range(len(sub)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    owner: dict[int, int] = {}
    for idx, (_e, conn) in enumerate(sub):
        for n in conn:
            if n in owner:
                ra, rb = find(owner[n]), find(idx)
                if ra != rb:
                    parent[rb] = ra
            else:
                owner[n] = idx

    groups: dict[int, list[int]] = {}
    for idx in range(len(sub)):
        groups.setdefault(find(idx), []).append(idx)
    return sub, list(groups.values())


def region_of_g3(cog5_x: float, cog5_z: float, cog95_z: float, **offsets) -> dict:
    """Evaluation region from figure G.3 (all values mm, relative to the CoG points).

    front  = CoG5.x  - 82
    rear   = CoG95.x + 82
    top    = CoG95.z + 82
    bottom = CoG5.z  - 52
    corner radius 82

    G.3 gives the *side-view* projection only: there is no Y constraint. The caller
    must have both CoG points in the same frame as the mesh.
    """
    o = {"front": 82.0, "rear": 82.0, "top": 82.0, "bottom": 52.0, "radius": 82.0}
    o.update(offsets)
    return {
        "x": [round(cog5_x - o["front"], 1), round(cog5_x + o["rear"], 1)],
        "z": [round(cog5_z - o["bottom"], 1), round(cog95_z + o["top"], 1)],
        "radius": o["radius"],
        "anchor": {"cog5_x": cog5_x, "cog5_z": cog5_z, "cog95_z": cog95_z},
        "note": "G.3 side-view projection; rectangular bound shown, real boundary is a 82 mm-radius rounded quad",
    }


def point_in_rounded_rect(x: float, z: float, reg: dict) -> bool:
    """True if (x, z) is inside the G.3 rounded quadrilateral (corner radius r)."""
    x0, x1 = reg["x"]
    z0, z1 = reg["z"]
    r = reg.get("radius", 0.0)
    if not (x0 <= x <= x1 and z0 <= z <= z1):
        return False
    if r <= 0:
        return True
    cx = x0 + r if x < x0 + r else (x1 - r if x > x1 - r else None)
    cz = z0 + r if z < z0 + r else (z1 - r if z > z1 - r else None)
    if cx is None or cz is None:
        return True
    return (x - cx) ** 2 + (z - cz) ** 2 <= r * r
