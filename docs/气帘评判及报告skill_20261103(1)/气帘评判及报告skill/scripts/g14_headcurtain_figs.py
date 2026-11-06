#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Render the head-vs-curtain evidence figures (offline, orthographic, shaded).

  F1  iso 3/4 view of the 4 heads against the deployed curtain
  F2  2x2 YZ sections through each head CoG (bag thickness + gap annotated)
  F3  occupant-side projection with the G.3 evaluation zone and the head outlines
  F4  curtain Y envelope / thickness along the vehicle axis
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.patches import Rectangle

EV = r"E:\work\workbuddy\2026-10-30-20-33-11\CAB_G143_evidence"
NPZ = os.path.join(EV, "heads_vs_curtain.npz")

INK = "#2B2F33"
GREY = "#8A9096"
BLUE = "#1F5C9E"
BAG_FILL = "#C9D6E2"
RED = "#C0392B"

HEAD_COG = {
    "HIII 5F  front":  (1401.5, 120.1, 1089.3),
    "HIII 5F  rear":   (2501.5, 120.1, 1089.3),
    "HIII 95M front":  (1683.3, 124.6, 1255.1),
    "HIII 95M rear":   (2683.3, 124.6, 1205.1),
}
HEAD_COLOR = {
    "HIII 5F  front":  "#C0392B",
    "HIII 5F  rear":   "#D9822B",
    "HIII 95M front":  "#12876F",
    "HIII 95M rear":   "#7D3C98",
}
ZONE = dict(x0=1288.0, x1=2812.0, z0=1018.0, z1=1362.0)


def load():
    z = np.load(NPZ, allow_pickle=True)
    d = {"cxyz": z["curtain_nodes_xyz"], "celem": z["curtain_elem"],
         "cpid": z["curtain_pid"], "heads": {}}
    i = 0
    while "head%d_label" % i in z.files:
        d["heads"][str(z["head%d_label" % i][0])] = {
            "xyz": z["head%d_nodes_xyz" % i], "elem": z["head%d_elem" % i]}
        i += 1
    return d


def tri_of(xyz, elem):
    a, b, c, dd = elem[:, 0], elem[:, 1], elem[:, 2], elem[:, 3]
    t = np.vstack([np.stack([a, b, c], 1), np.stack([a, c, dd], 1)])
    ok = (t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])
    return t[ok]


def camera(az_deg, el_deg):
    az, el = np.radians(az_deg), np.radians(el_deg)
    eye = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    right = np.cross(np.array([0.0, 0.0, 1.0]), eye)
    right /= np.linalg.norm(right)
    up = np.cross(eye, right)
    return eye, right, up


def shade(xyz, tri, base, eye):
    p = xyz[tri]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    ln = np.linalg.norm(n, axis=1)
    ln[ln == 0] = 1
    n = n / ln[:, None]
    lam = np.abs(n @ (eye / np.linalg.norm(eye)))
    k = 0.42 + 0.58 * lam
    return np.clip(np.array(base, float)[None, :] * k[:, None], 0, 1)


def paint(ax, xyz, tri, colors, eye, right, up, lw=0.0, edge="none", alpha=1.0):
    P = xyz[tri]
    sx, sy, dp = P @ right, P @ up, P @ eye
    order = np.argsort(dp.mean(axis=1))
    verts = [np.stack([sx[i], sy[i]], axis=1) for i in order]
    ax.add_collection(PolyCollection(verts, facecolors=colors[order],
                                     edgecolors=edge, linewidths=lw,
                                     alpha=alpha, antialiased=True))


def style(ax):
    for s in ax.spines.values():
        s.set_color("#D5DCE4")
    ax.tick_params(labelsize=7, colors=GREY)


def fig_iso(d, out):
    cxyz, ctri = d["cxyz"], tri_of(d["cxyz"], d["celem"])
    eye, right, up = camera(58.0, 22.0)
    ccol = shade(cxyz, ctri, (0.66, 0.73, 0.81), eye)

    fig = plt.figure(figsize=(13.0, 6.4), dpi=150)
    ax = fig.add_axes([0.02, 0.04, 0.74, 0.80])
    paint(ax, cxyz, ctri, ccol, eye, right, up, lw=0.08, edge="#55606B")
    for label, g in d["heads"].items():
        t = tri_of(g["xyz"], g["elem"])
        col = shade(g["xyz"], t, matplotlib.colors.to_rgb(HEAD_COLOR[label]), eye)
        paint(ax, g["xyz"], t, col, eye, right, up, lw=0.12, edge="#3b2418")
    basis = np.stack([right, up], 1)
    allp = np.vstack([cxyz @ basis] + [g["xyz"] @ basis for g in d["heads"].values()])
    lo, hi = allp.min(0), allp.max(0)
    pad = (hi - lo) * 0.05
    ax.set_xlim(lo[0] - pad[0], hi[0] + pad[0])
    ax.set_ylim(lo[1] - pad[1], hi[1] + pad[1])
    ax.set_aspect("equal")
    ax.axis("off")

    axl = fig.add_axes([0.77, 0.33, 0.22, 0.40])
    axl.axis("off")
    axl.text(0, 1.0, "Reference heads", fontsize=9.5, color=INK, weight="bold",
             va="top")
    for i, (label, col) in enumerate(HEAD_COLOR.items()):
        yy = 0.86 - i * 0.12
        axl.add_patch(Rectangle((0, yy - 0.05), 0.09, 0.07, fc=col, ec="none"))
        axl.text(0.13, yy - 0.03, label, fontsize=8.5, color=INK, va="center")
    yy = 0.34
    axl.add_patch(Rectangle((0, yy - 0.05), 0.09, 0.07, fc="#9FB0C0", ec="none"))
    axl.text(0.13, yy - 0.03, "curtain, parts 4/6/7/8", fontsize=8.5, color=INK,
             va="center")
    axl.text(0, 0.16, "iso 58° / 22°   state 82 · t = 200 ms\nno scale factor, mm",
             fontsize=7.8, color=GREY, va="top", linespacing=1.6)

    fig.text(0.02, 0.955, "Deployed curtain with the four head CoG reference models",
             fontsize=14, color=INK, weight="bold")
    fig.text(0.02, 0.908,
             "Curtain geometry exported from 2974.h3d at the last state and assembled with the main_dummy.key head models",
             fontsize=8.5, color=GREY)
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    print("wrote", out)


def fig_sections(d, meta, out):
    from g14_headcurtain_sections import plane_segments
    cxyz, ctri = d["cxyz"], tri_of(d["cxyz"], d["celem"])

    fig, axes = plt.subplots(2, 2, figsize=(11.4, 8.8), dpi=150)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.875, bottom=0.065,
                        wspace=0.14, hspace=0.30)
    # one common frame for all four panels so sections can be compared directly
    XLIM, YLIM = (-160.0, 230.0), (880.0, 1460.0)
    for ax, (label, cog) in zip(axes.ravel(), HEAD_COG.items()):
        x, y, z = cog
        h = d["heads"][label]
        bs = plane_segments(cxyz, ctri, 0, x)
        hs = plane_segments(h["xyz"], tri_of(h["xyz"], h["elem"]), 0, x)
        m = meta["heads"][label]

        if len(bs):
            ax.add_collection(LineCollection(
                np.stack([bs[:, :, 1], bs[:, :, 2]], -1), colors=BLUE,
                linewidths=1.7, zorder=3))
        if len(hs):
            ax.add_collection(LineCollection(
                np.stack([hs[:, :, 1], hs[:, :, 2]], -1),
                colors=HEAD_COLOR[label], linewidths=1.5, zorder=4))

        th = m["bag_y"]
        if th:
            ya, yb = th
            ax.annotate("", xy=(ya, z), xytext=(yb, z),
                        arrowprops=dict(arrowstyle="<->", color=BLUE, lw=1.2,
                                        shrinkA=0, shrinkB=0), zorder=6)
            ax.text((ya + yb) / 2, z + 7, "%.0f mm" % (yb - ya), fontsize=8,
                    color=BLUE, ha="center", va="bottom", weight="bold", zorder=7)
        ax.plot([y], [z], marker="+", ms=9, mew=1.5, color=INK, zorder=8)
        ax.annotate("CoG", xy=(y, z), xytext=(6, -12), textcoords="offset points",
                    fontsize=7.2, color=INK, zorder=8)

        ax.set_title("%s   ·   X = %.0f mm" % (label, x), fontsize=10, color=INK,
                     loc="left", pad=4)
        ax.text(0.02, 0.03,
                "bag Y-thickness %.0f mm\nmin gap head↔bag %.1f mm"
                % (m["thickness"], m["gap_min"]),
                transform=ax.transAxes, ha="left", va="bottom", fontsize=8.2,
                color=INK, linespacing=1.5,
                bbox=dict(boxstyle="round,pad=0.35", fc="#F4F7FA", ec="#D5DCE4"))
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(XLIM)
        ax.set_ylim(YLIM)
        ax.grid(alpha=0.22, lw=0.5)
        ax.set_xlabel("Y (mm)  →  occupant side", fontsize=7.8, color=GREY)
        ax.set_ylabel("Z (mm)", fontsize=7.8, color=GREY)
        style(ax)

    fig.text(0.012, 0.962, "YZ sections through the head CoG planes",
             fontsize=14, color=INK, weight="bold")
    fig.text(0.012, 0.925,
             "blue = curtain shell (parts 4/6/7/8) · coloured = dummy head skin · double arrow = curtain Y-thickness at CoG height (±30 mm window) · common axes",
             fontsize=8.3, color=GREY)
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    print("wrote", out)


def fig_zone(d, out):
    cxyz, ctri = d["cxyz"], tri_of(d["cxyz"], d["celem"])
    fig, ax = plt.subplots(figsize=(13.2, 5.9), dpi=150)
    P = cxyz[ctri][:, :, [0, 2]]
    order = np.argsort(cxyz[ctri][:, :, 1].mean(1))
    ax.add_collection(PolyCollection([P[i] for i in order],
                                     facecolors="#C9D6E2", edgecolors="none"))
    for label, g in d["heads"].items():
        ht = tri_of(g["xyz"], g["elem"])
        Q = g["xyz"][ht][:, :, [0, 2]]
        o = np.argsort(g["xyz"][ht][:, :, 1].mean(1))
        ax.add_collection(PolyCollection([Q[i] for i in o],
                                         facecolors=HEAD_COLOR[label],
                                         edgecolors="none", alpha=0.35))
        cx, cy, cz = HEAD_COG[label]
        ax.plot([cx], [cz], "o", ms=5, color=HEAD_COLOR[label], mec="white", mew=1.1,
                zorder=9)
        ax.annotate(label.replace("HIII ", ""), xy=(cx, cz), xytext=(0, 30),
                    textcoords="offset points", fontsize=8.5, color=HEAD_COLOR[label],
                    ha="center", weight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
    ax.add_patch(Rectangle((ZONE["x0"], ZONE["z0"]), ZONE["x1"] - ZONE["x0"],
                           ZONE["z1"] - ZONE["z0"], fill=False, ec=RED, lw=1.8,
                           ls=(0, (6, 3)), zorder=10))
    ax.text(ZONE["x0"] + 8, ZONE["z1"] + 10, "G.3 evaluation zone  82/82/82/52, r = 82 mm",
            fontsize=8.5, color=RED, va="bottom")
    ax.set_aspect("equal")
    ax.set_xlabel("X (mm)", fontsize=8, color=GREY)
    ax.set_ylabel("Z (mm)", fontsize=8, color=GREY)
    style(ax)
    ax.grid(alpha=0.18, lw=0.5)
    fig.text(0.012, 0.955,
             "Occupant-side projection — curtain, evaluation zone and head positions",
             fontsize=13, color=INK, weight="bold")
    fig.text(0.012, 0.912,
             "the four head CoGs (white dots) all fall inside the G.3 zone and inside the inflated area",
             fontsize=8.5, color=GREY)
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    print("wrote", out)


def fig_thickness(d, meta, out):
    cxyz = d["cxyz"]
    xs = np.arange(1250, 2900, 20.0)
    lo, hi = [], []
    for x in xs:
        m = np.abs(cxyz[:, 0] - x) < 12.0
        y = cxyz[m, 1]
        lo.append(y.min() if m.sum() > 4 else np.nan)
        hi.append(y.max() if m.sum() > 4 else np.nan)
    lo, hi = np.array(lo), np.array(hi)

    fig, ax = plt.subplots(figsize=(13.2, 4.6), dpi=150)
    ax.fill_between(xs, lo, hi, color="#DCE6F0", lw=0,
                    label="curtain Y envelope (all Z)")
    ax.plot(xs, hi, color=BLUE, lw=1.0)
    ax.plot(xs, lo, color=BLUE, lw=1.0)
    for label, cog in HEAD_COG.items():
        m = meta["heads"][label]
        ax.plot([cog[0]], [m["bag_y"][0]], marker="v", ms=5,
                color=HEAD_COLOR[label], mec="white", mew=0.9, zorder=6)
        ax.plot([cog[0]], [m["bag_y"][1]], marker="^", ms=5,
                color=HEAD_COLOR[label], mec="white", mew=0.9, zorder=6)
        ax.axvline(cog[0], color=HEAD_COLOR[label], lw=1.0, ls="--", alpha=0.75)
        ax.annotate("%s\n%.0f mm" % (label.replace("HIII ", ""), m["thickness"]),
                    xy=(cog[0], m["bag_y"][1]), xytext=(6, 10),
                    textcoords="offset points", fontsize=8, color=HEAD_COLOR[label],
                    weight="bold", linespacing=1.4)
    ax.set_ylabel("Y (mm)", fontsize=8.5, color=GREY)
    ax.set_xlabel("X (mm)", fontsize=8.5, color=GREY)
    style(ax)
    ax.grid(alpha=0.22, lw=0.5)
    fig.text(0.012, 0.955,
             "Curtain Y envelope along the vehicle axis and the thickness at each head CoG",
             fontsize=13, color=INK, weight="bold")
    fig.text(0.012, 0.905,
             "envelope from all curtain nodes in a ±12 mm X window;  ▲ ▼  mark the measured bag surfaces at that head's CoG height (±30 mm section window)",
             fontsize=8.3, color=GREY)
    fig.tight_layout(rect=[0, 0, 1, 0.89])
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    print("wrote", out)


def main():
    d = load()
    with open(os.path.join(EV, "sections.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    which = sys.argv[1:] or ["1", "2", "3", "4"]
    if "1" in which:
        fig_iso(d, os.path.join(EV, "fig_overlap.png"))
    if "2" in which:
        fig_sections(d, meta, os.path.join(EV, "fig_sections_yz.png"))
    if "3" in which:
        fig_zone(d, os.path.join(EV, "fig_zone.png"))
    if "4" in which:
        fig_thickness(d, meta, os.path.join(EV, "fig_thickness_x.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
