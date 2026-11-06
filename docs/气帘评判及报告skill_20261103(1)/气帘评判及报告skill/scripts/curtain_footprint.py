#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse a LS-DYNA deck's *AIRBAG_REFERENCE_GEOMETRY curtain nodes and report
the curtain footprint, then (optionally) check the reference-report head
barycenter points against that footprint.

WHY THIS EXISTS
    The deployment mesh of a membrane airbag (curtain) is defined via
    *AIRBAG_REFERENCE_GEOMETRY node IDs, not a regular *PART. To know where the
    curtain sits we must resolve those node IDs against the *NODE pool and take
    the bounding box. That gives the *initial* (undeformed) footprint.

IMPORTANT FRAME CAVEAT
    The head-barycenter coordinates from the reference report live in the
    VEHICLE GLOBAL frame (X longitudinal / Y lateral / Z height). The curtain
    reference geometry is frequently in a LOCAL / mirrored frame (e.g. Y ~ 0).
    Do NOT blindly declare "heads fall outside the curtain" — first confirm the
    two sets share a frame. This script prints both bounding boxes and lets you
    decide; the head-in-footprint check only fires when you pass --assume-same-frame.

Usage:
    python curtain_footprint.py <deck.k> [--decks a.k b.key ...] [--heads heads.json]
"""
import argparse
import glob
import json
import os
import re


def parse_nodes(path):
    """Return {nid:(x,y,z)} from a deck's *NODE block(s)."""
    pool = {}
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError:
        return pool
    in_node = False
    for ln in lines:
        s = ln.strip()
        if s.upper().startswith("*NODE"):
            in_node = True
            continue
        if s.startswith("*"):
            in_node = False
            continue
        if not in_node or not s or s.startswith("$"):
            continue
        p = s.replace(",", " ").split()
        if len(p) < 4:
            continue
        try:
            nid = int(float(p[0]))
            pool[nid] = (float(p[1]), float(p[2]), float(p[3]))
        except ValueError:
            continue
    return pool


def arb_node_ids(path):
    """Return ordered list of node IDs referenced in *AIRBAG_REFERENCE_GEOMETRY."""
    ids = []
    in_arb = False
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for ln in fh:
            s = ln.strip()
            if s.upper().startswith("*AIRBAG_REFERENCE_GEOMETRY"):
                in_arb = True
                continue
            if s.startswith("*"):
                in_arb = False
                continue
            if not in_arb or not s or s.startswith("$"):
                continue
            for tok in s.replace(",", " ").split():
                if re.fullmatch(r"1000\d{4}", tok):
                    ids.append(int(tok))
    return list(dict.fromkeys(ids))


def bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck", help="deck file containing *AIRBAG_REFERENCE_GEOMETRY")
    ap.add_argument("--decks", nargs="*", default=[], help="extra decks to build node pool")
    ap.add_argument("--heads", default=None, help="json file: {name:[x,y,z,thk], ...}")
    ap.add_argument("--assume-same-frame", action="store_true",
                    help="DANGER: also run head-in-footprint check (only if frames match)")
    args = ap.parse_args()

    all_decks = [args.deck] + args.decks
    # also glob the same directory for any .k/.key to enrich the pool
    base_dir = os.path.dirname(os.path.abspath(args.deck))
    for f in glob.glob(os.path.join(base_dir, "*.k")) + glob.glob(os.path.join(base_dir, "*.key")):
        if f not in all_decks:
            all_decks.append(f)

    pool = {}
    for d in all_decks:
        pool.update(parse_nodes(d))

    ids = arb_node_ids(args.deck)
    matched = [i for i in ids if i in pool]
    print(f"deck            : {args.deck}")
    print(f"ARB node ids    : {len(ids)}  (matched in node pool: {len(matched)})")
    if not matched:
        print("  !! no curtain nodes resolved — check deck include paths / node pool")
        return
    cb = bbox([pool[i] for i in matched])
    print(f"  CURTAIN X: {cb[0]:.1f}..{cb[1]:.1f} (span {cb[1]-cb[0]:.1f})")
    print(f"  CURTAIN Y: {cb[2]:.1f}..{cb[3]:.1f} (span {cb[3]-cb[2]:.1f})")
    print(f"  CURTAIN Z: {cb[4]:.1f}..{cb[5]:.1f} (span {cb[5]-cb[4]:.1f})")

    if args.heads:
        with open(args.heads, encoding="utf-8") as fh:
            heads = json.load(fh)
        hx = [v[0] for v in heads.values()]
        hy = [v[1] for v in heads.values()]
        hz = [v[2] for v in heads.values()]
        print(f"\n  HEAD   X: {min(hx):.1f}..{max(hx):.1f}")
        print(f"  HEAD   Y: {min(hy):.1f}..{max(hy):.1f}")
        print(f"  HEAD   Z: {min(hz):.1f}..{max(hz):.1f}")
        if args.assume_same_frame:
            print("\n  Head-in-curtain-footprint check (X&Y&Z within span):")
            for name, v in heads.items():
                ix = cb[0] <= v[0] <= cb[1]
                iy = cb[2] <= v[1] <= cb[3]
                iz = cb[4] <= v[2] <= cb[5]
                print(f"    {name}: X_in={ix} Y_in={iy} Z_in={iz}")
        else:
            print("\n  (skipped head check — frames likely differ; confirm before comparing)")


if __name__ == "__main__":
    main()
