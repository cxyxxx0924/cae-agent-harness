#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build the merged deck (original node IDs kept) + the numpy cache.

Keeping the LS-DYNA node IDs identical to 5P-BAG_005.key means HyperView can load
this deck *together with* 2974.h3d and still contour the curtain — the heads then
simply show up as un-resulted geometry on top.

Outputs
  heads_vs_curtain.key   merged deck (HyperView / HyperMesh ready)
  heads_vs_curtain.npz   0-based index arrays for the offline renderer
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

MODEL_DIR = r"E:\work\AI_CAB\Model_update_Move_Iter04\Model_update_Move_Iter04"
HEAD_DIR = r"E:\work\AI_CAB\head_area"
NODES_JSON = r"C:\Users\hekie\Documents\HyperWorksMCP\workspace\Iter04\nodes_last.json"
OUT_DIR = r"E:\work\workbuddy\2026-10-30-20-33-11\CAB_G143_evidence"

CURTAIN_PIDS = (4, 6, 7, 8)
HEAD_ID_OFF = 10000000            # same trick as main_dummy.key

HEADS = [
    ("HIII_5F_Head.key",       (1400.0, 50.0, 1100.0), "HIII 5F  front"),
    ("HIII_5F_Head_Rear.key",  (2500.0, 50.0, 1100.0), "HIII 5F  rear"),
    ("HIII_95M_Head.key",      (1700.0, 50.0, 1250.0), "HIII 95M front"),
    ("HIII_95M_Head_Rear.key", (2700.0, 50.0, 1200.0), "HIII 95M rear"),
]


def parse_deck(path):
    nodes, shells, parts, titles = {}, [], {}, {}
    mode, last_part = None, None
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            if line.startswith("*"):
                kw = line.strip().upper()
                mode = ("node" if kw.startswith("*NODE") else
                        "shell" if kw.startswith("*ELEMENT_SHELL") else
                        "part" if kw.startswith("*PART") else
                        "title" if kw.startswith("*TITLE") else None)
                continue
            if mode == "node":
                try:
                    nodes[int(line[0:8])] = (float(line[8:24]), float(line[24:40]),
                                             float(line[40:56]))
                except ValueError:
                    pass
            elif mode == "shell":
                try:
                    ns = [int(line[a:a + 8]) for a in (16, 24, 32, 40)
                          if line[a:a + 8].strip()]
                    if len(ns) >= 3:
                        shells.append((int(line[0:8]), int(line[8:16]), ns))
                except ValueError:
                    pass
            elif mode == "part":
                try:
                    last_part = int(line[0:8])
                except ValueError:
                    last_part = None
            elif mode == "title" and last_part:
                titles[last_part] = line.strip()
    return nodes, shells, titles


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cnodes, cshells, ctitles = parse_deck(os.path.join(MODEL_DIR, "5P-BAG_005.key"))
    with open(NODES_JSON, encoding="utf-8") as fh:
        deformed = {int(r[0]): r[1] for r in json.load(fh)["rows"]}

    keep = [s for s in cshells if s[1] in CURTAIN_PIDS]
    used = sorted({n for _, _, ns in keep for n in ns})
    missing = [n for n in used if n not in deformed]
    if missing:
        raise SystemExit("coordinate dump incomplete: %d nodes" % len(missing))
    print("curtain: %d shells, %d nodes" % (len(keep), len(used)))

    heads = {}
    for i, (fn, tr, label) in enumerate(HEADS):
        hn, hs, ht = parse_deck(os.path.join(HEAD_DIR, fn))
        off = np.array(tr)
        heads[label] = dict(
            labels=sorted(hn), nodes=hn, shells=hs,
            off=off, idoff=HEAD_ID_OFF * (i + 1), pid=9001 + i)
        print("%-16s nodes %5d shells %5d idoff +%d" % (label, len(hn), len(hs),
                                                        heads[label]["idoff"]))

    # ------------------------------------------------------------- deck
    out = os.path.join(OUT_DIR, "heads_vs_curtain.key")
    titles = {4: "CURTAIN main", 6: "CURTAIN layer2",
              7: "CURTAIN strap A", 8: "CURTAIN strap B"}
    for label, h in heads.items():
        titles[h["pid"]] = "HEAD " + label
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("*KEYWORD\n$ G.14.3 evidence: deformed curtain + positioned heads\n")
        fh.write("*TITLE\nheads_vs_curtain  t = 200 ms\n$\n*NODE\n")
        for n in used:
            x, y, z = deformed[n]
            fh.write("%8d%16.6f%16.6f%16.6f\n" % (n, x, y, z))
        for label, h in heads.items():
            for k in h["labels"]:
                x, y, z = h["nodes"][k]
                fh.write("%8d%16.6f%16.6f%16.6f\n"
                         % (k + h["idoff"], x + h["off"][0], y + h["off"][1],
                            z + h["off"][2]))
        for pid in list(CURTAIN_PIDS) + [h["pid"] for h in heads.values()]:
            fh.write("*PART\n$#                                                                         title\n")
            fh.write("%s\n" % titles[pid])
            fh.write("$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid\n")
            fh.write("%10d%10d%10d\n" % (pid, pid, 0))
            fh.write("*SECTION_SHELL_TITLE\n%s\n" % titles[pid])
            fh.write("*SECTION_SHELL\n")
            fh.write("$#   secid    elform      shrf       nip     propt   qr/irid     icomp     setyp\n")
            fh.write("%10d%10d%10.4f%10d\n" % (pid, 9, 1.0, 1))
            fh.write("$#      t1        t2        t3        t4      nloc     marea      idof    edgset\n")
            fh.write("%10.3f%10.3f%10.3f%10.3f\n" % (1.0, 1.0, 1.0, 1.0))
        fh.write("*ELEMENT_SHELL\n")
        for eid, pid, ns in keep:
            ids = [ns[0], ns[1], ns[2], ns[3] if len(ns) > 3 else ns[2]]
            fh.write("%8d%8d%8d%8d%8d%8d\n" % (eid, pid, ids[0], ids[1], ids[2], ids[3]))
        for label, h in heads.items():
            for eid, pid, ns in h["shells"]:
                ids = [ns[0], ns[1], ns[2], ns[3] if len(ns) > 3 else ns[2]]
                fh.write("%8d%8d%8d%8d%8d%8d\n"
                         % (eid + h["idoff"], h["pid"],
                            ids[0] + h["idoff"], ids[1] + h["idoff"],
                            ids[2] + h["idoff"], ids[3] + h["idoff"]))
        fh.write("*END\n")
    print("wrote", out, os.path.getsize(out) // 1024, "KB")

    # ------------------------------------------------------------- npz
    idx = {n: i for i, n in enumerate(used)}
    arrs = {
        "curtain_nodes_id": np.array(used),
        "curtain_nodes_xyz": np.array([deformed[n] for n in used]),
        "curtain_elem": np.array([[idx[n] for n in ns] for _, _, ns in keep]),
        "curtain_pid": np.array([pid for _, pid, _ in keep]),
    }
    for i, (label, h) in enumerate(heads.items()):
        hix = {k: j for j, k in enumerate(h["labels"])}
        arrs["head%d_label" % i] = np.array([label])
        arrs["head%d_nodes_xyz" % i] = np.array(
            [np.array(h["nodes"][k]) + h["off"] for k in h["labels"]])
        arrs["head%d_elem" % i] = np.array(
            [[hix[n] for n in ns] for _, _, ns in h["shells"]])
        arrs["head%d_offset" % i] = h["off"]
    npz = os.path.join(OUT_DIR, "heads_vs_curtain.npz")
    np.savez_compressed(npz, **arrs)
    print("wrote", npz, os.path.getsize(npz) // 1024, "KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
