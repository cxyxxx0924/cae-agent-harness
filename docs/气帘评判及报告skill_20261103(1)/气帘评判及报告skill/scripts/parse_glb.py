#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Minimal GLB (glTF 2.0 binary) reader — positions per mesh, world transformed.

Why: HyperView's Python API exposes node coordinates one property read at a time
(~3 ms each).  A 149k-node model then needs ~15 min and trips the bridge request
budget.  ExportModelGLB writes the deformed geometry in one call; this module
turns the binary chunk into numpy arrays in well under a second.

Usage:
    python parse_glb.py model.glb                # bbox table per mesh
    python parse_glb.py model.glb --out out.npz  # save {mesh_name: Nx3}
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np

COMP = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
        5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _read_glb(path: Path):
    raw = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF":
        raise ValueError("not a GLB file")
    off = 12
    js, bin_chunk = None, None
    while off < length:
        clen, ctype = struct.unpack_from("<II", raw, off)
        payload = raw[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(payload.decode("utf-8"))
        elif ctype == 0x004E4942:
            bin_chunk = payload
        off += 8 + clen + ((4 - clen % 4) % 4)
    if js is None or bin_chunk is None:
        raise ValueError("GLB is missing the JSON or BIN chunk")
    return js, bin_chunk


def _accessor(js, blob, index):
    acc = js["accessors"][index]
    n = acc["count"]
    ncomp = NCOMP[acc["type"]]
    fmt, size = COMP[acc["componentType"]]
    bv = js["bufferViews"][acc["bufferView"]]
    base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride") or ncomp * size
    if stride == ncomp * size:
        arr = np.frombuffer(blob, dtype=np.dtype("<" + fmt), count=n * ncomp, offset=base)
    else:
        out = np.empty(n * ncomp, dtype=np.dtype("<" + fmt))
        for i in range(n):
            out[i * ncomp:(i + 1) * ncomp] = np.frombuffer(
                blob, dtype=np.dtype("<" + fmt), count=ncomp, offset=base + i * stride)
        arr = out
    arr = np.asarray(arr, dtype=np.float64 if fmt == "f" else np.int64)
    return arr.reshape(n, ncomp)


def _mat(node):
    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T
    t = np.array(node.get("translation", [0, 0, 0]), dtype=float)
    r = np.array(node.get("rotation", [0, 0, 0, 1]), dtype=float)
    s = np.array(node.get("scale", [1, 1, 1]), dtype=float)
    x, y, z, w = r
    rot = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    m = np.eye(4)
    m[:3, :3] = rot * s
    m[:3, 3] = t
    return m


def load_glb(path: Path) -> dict[str, np.ndarray]:
    js, blob = _read_glb(path)
    meshes = js.get("meshes", [])
    out: dict[str, np.ndarray] = {}
    scene = js.get("scenes", [{}])[js.get("scene", 0) or 0]
    roots = scene.get("nodes", [])

    def walk(idx, parent):
        node = js["nodes"][idx]
        world = parent @ _mat(node)
        if "mesh" in node:
            mesh = meshes[node["mesh"]]
            name = mesh.get("name") or node.get("name") or f"mesh{node['mesh']}"
            pts = []
            for prim in mesh.get("primitives", []):
                attrs = prim.get("attributes", {})
                if "POSITION" not in attrs:
                    continue
                p = _accessor(js, blob, attrs["POSITION"])
                pts.append(p)
            if pts:
                p = np.vstack(pts)
                ph = np.hstack([p, np.ones((len(p), 1))])
                p = (ph @ world.T)[:, :3]
                out[name] = np.vstack([out[name], p]) if name in out else p
        for child in node.get("children", []):
            walk(child, world)

    for r in roots:
        walk(r, np.eye(4))
    if not out:  # no scene graph: fall back to raw mesh list
        for i, mesh in enumerate(meshes):
            name = mesh.get("name") or f"mesh{i}"
            for prim in mesh.get("primitives", []):
                if "POSITION" in prim.get("attributes", {}):
                    p = _accessor(js, blob, prim["attributes"]["POSITION"])
                    out[name] = np.vstack([out[name], p]) if name in out else p
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    data = load_glb(Path(args.glb))
    total = 0
    for name, pts in sorted(data.items(), key=lambda kv: -len(kv[1])):
        total += len(pts)
        lo, hi = pts.min(0), pts.max(0)
        print(f"{len(pts):>8}  {name[:46]:<46} "
              f"X {lo[0]:8.1f}..{hi[0]:8.1f}  Y {lo[1]:7.1f}..{hi[1]:7.1f}  "
              f"Z {lo[2]:8.1f}..{hi[2]:8.1f}")
    print(f"{total:>8}  vertices total, {len(data)} meshes")
    if args.out:
        np.savez_compressed(args.out, **{k: v for k, v in data.items()})
        print("saved", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
