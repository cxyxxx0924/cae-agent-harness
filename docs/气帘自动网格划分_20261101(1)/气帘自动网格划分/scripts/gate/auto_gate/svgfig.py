#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
svgfig.py — 零依赖纯 Python SVG 出图引擎 (auto_gate 自出图审查用)

不依赖 matplotlib/numpy。产出可在任意浏览器打开的自包含 .svg。
坐标系: 世界 (X 横, Z 竖, Z 向上) -> SVG 像素 (y 向下翻转)。
默认浅色主题(白底深字), 适配 IDE light theme。
"""
import math


PALETTE = {
    "ink":    "#1f2733",
    "grid":   "#e2e6ec",
    "axis":   "#9aa3af",
    "cad":    "#d62728",   # IGES 曲线 - 红
    "mesh":   "#1f77b4",   # 网格自由边 - 蓝
    "fill":   "#cfe3f5",
    "ok":     "#2ca02c",
    "warn":   "#e08a00",
    "fail":   "#d62728",
    "belt":   "#9467bd",
    "cav":    "#2ca02c",
    "seam":   "#ff7f0e",
    "tether": "#17becf",
    "accent": "#333333",
}


class Figure:
    def __init__(self, w=680, h=520, title="", subtitle="", margin=(54, 18, 40, 66)):
        self.w, self.h = w, h
        self.mt, self.mr, self.mb, self.ml = margin  # top,right,bottom,left
        self.title = title
        self.subtitle = subtitle
        self.parts = []
        self.xmin = self.ymin = 1e18
        self.xmax = self.ymax = -1e18
        self._bounded = False
        self.legend = []
        self.notes = []

    # ---- bounds ----
    def _touch(self, x, y):
        if x < self.xmin: self.xmin = x
        if x > self.xmax: self.xmax = x
        if y < self.ymin: self.ymin = y
        if y > self.ymax: self.ymax = y
        self._bounded = True

    def set_bounds(self, xmin, ymin, xmax, ymax, pad_frac=0.04):
        self.xmin, self.ymin, self.xmax, self.ymax = xmin, ymin, xmax, ymax
        dx = (xmax - xmin) or 1.0; dy = (ymax - ymin) or 1.0
        self.xmin -= dx * pad_frac; self.xmax += dx * pad_frac
        self.ymin -= dy * pad_frac; self.ymax += dy * pad_frac
        self._bounded = True

    # ---- transform (world -> svg px) ----
    def _sx(self, x):
        pw = self.w - self.ml - self.mr
        dx = self.xmax - self.xmin
        if abs(dx) < 1e-9:
            return self.ml + pw / 2.0
        return self.ml + (x - self.xmin) / dx * pw

    def _sy(self, y):
        ph = self.h - self.mt - self.mb
        dy = self.ymax - self.ymin
        if abs(dy) < 1e-9:
            return self.mt + ph / 2.0
        return self.mt + (self.ymax - y) / dy * ph

    # ---- primitives ----
    def polyline(self, pts, color="mesh", width=1.1, dash=None, opacity=1.0, tag=None):
        for (x, y) in pts:
            self._touch(x, y)
        d = " ".join(("M" if i == 0 else "L") + f"{self._sx(x):.2f},{self._sy(y):.2f}"
                     for i, (x, y) in enumerate(pts))
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-opacity="{opacity}"{da} stroke-linejoin="round" stroke-linecap="round"/>')
        if tag:
            self.legend.append((color, tag, "line"))

    def points(self, pts, color="cad", r=1.6, opacity=1.0, tag=None):
        for (x, y) in pts:
            self._touch(x, y)
        for (x, y) in pts:
            self.parts.append(
                f'<circle cx="{self._sx(x):.2f}" cy="{self._sy(y):.2f}" r="{r}" '
                f'fill="{color}" fill-opacity="{opacity}"/>')
        if tag:
            self.legend.append((color, tag, "dot"))

    def quads(self, quads_xy, fill="fill", stroke=None, width=0.3, opacity=0.5, tag=None):
        """quads_xy: list of [(x,y),(x,y),(x,y),(x,y)] in world coords."""
        for q in quads_xy:
            for (x, y) in q:
                self._touch(x, y)
            d = " ".join(("M" if i == 0 else "L") + f"{self._sx(x):.2f},{self._sy(y):.2f}"
                         for i, (x, y) in enumerate(q)) + " Z"
            st = f' stroke="{stroke}" stroke-width="{width}"' if stroke else ' stroke="none"'
            self.parts.append(f'<path d="{d}" fill="{fill}" fill-opacity="{opacity}"{st}/>')
        if tag:
            self.legend.append((fill, tag, "box"))

    def marker(self, x, y, color="fail", label="", r=4):
        self._touch(x, y)
        self.parts.append(
            f'<circle cx="{self._sx(x):.2f}" cy="{self._sy(y):.2f}" r="{r}" fill="none" '
            f'stroke="{color}" stroke-width="1.6"/>')
        if label:
            self.parts.append(
                f'<text x="{self._sx(x)+r+2:.1f}" y="{self._sy(y)-r-1:.1f}" font-size="10" '
                f'fill="{color}">{_esc(label)}</text>')

    def note(self, text):
        self.notes.append(text)

    # ---- render ----
    def _grid(self):
        out = []
        pw = self.w - self.ml - self.mr; ph = self.h - self.mt - self.mb
        # frame
        out.append(f'<rect x="{self.ml}" y="{self.mt}" width="{pw}" height="{ph}" '
                   f'fill="#ffffff" stroke="{PALETTE["axis"]}" stroke-width="0.8"/>')
        # grid lines (5x5)
        nx, ny = 5, 5
        for i in range(1, nx):
            x = self.ml + pw * i / nx
            out.append(f'<line x1="{x:.1f}" y1="{self.mt}" x2="{x:.1f}" y2="{self.mt+ph}" '
                       f'stroke="{PALETTE["grid"]}" stroke-width="0.6"/>')
        for j in range(1, ny):
            y = self.mt + ph * j / ny
            out.append(f'<line x1="{self.ml}" y1="{y:.1f}" x2="{self.ml+pw}" y2="{y:.1f}" '
                       f'stroke="{PALETTE["grid"]}" stroke-width="0.6"/>')
        # axis tick labels
        for i in range(nx + 1):
            x = self.xmin + (self.xmax - self.xmin) * i / nx
            out.append(f'<text x="{self.ml+pw*i/nx:.1f}" y="{self.mt+ph+14}" font-size="9" '
                       f'fill="{PALETTE["axis"]}" text-anchor="middle">{x:.0f}</text>')
        for j in range(ny + 1):
            y = self.ymax - (self.ymax - self.ymin) * j / ny
            out.append(f'<text x="{self.ml-6}" y="{self.mt+ph*j/ny+3:.1f}" font-size="9" '
                       f'fill="{PALETTE["axis"]}" text-anchor="end">{y:.0f}</text>')
        out.append(f'<text x="{self.ml+pw/2:.1f}" y="{self.h-6}" font-size="10" '
                   f'fill="{PALETTE["ink"]}" text-anchor="middle">X (mm)</text>')
        out.append(f'<text x="12" y="{self.mt+ph/2:.1f}" font-size="10" fill="{PALETTE["ink"]}" '
                   f'text-anchor="middle" transform="rotate(-90 12 {self.mt+ph/2:.1f})">Z (mm)</text>')
        return "".join(out)

    def _legend(self):
        if not self.legend:
            return ""
        x = self.ml + 4; y = self.mt + 12
        rows = []
        for color, tag, kind in self.legend:
            if kind == "dot":
                sw = f'<circle cx="{x+5}" cy="{y-3}" r="3" fill="{color}"/>'
            elif kind == "box":
                sw = f'<rect x="{x}" y="{y-7}" width="10" height="8" fill="{color}" fill-opacity="0.6" stroke="{color}"/>'
            else:
                sw = f'<line x1="{x}" y1="{y-3}" x2="{x+11}" y2="{y-3}" stroke="{color}" stroke-width="2"/>'
            rows.append(sw + f'<text x="{x+16}" y="{y}" font-size="10" fill="{PALETTE["ink"]}">{_esc(tag)}</text>')
            y += 14
        return f'<g>{"".join(rows)}</g>'

    def svg(self):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" font-family="Segoe UI, Arial, sans-serif">')
        bg = f'<rect width="{self.w}" height="{self.h}" fill="#ffffff"/>'
        tt = ""
        if self.title:
            tt += f'<text x="{self.w/2}" y="20" font-size="14" font-weight="600" fill="{PALETTE["ink"]}" text-anchor="middle">{_esc(self.title)}</text>'
        if self.subtitle:
            tt += f'<text x="{self.w/2}" y="36" font-size="10" fill="{PALETTE["axis"]}" text-anchor="middle">{_esc(self.subtitle)}</text>'
        notes = ""
        ny = self.h - 18
        for n in self.notes[-3:]:
            notes += f'<text x="{self.ml}" y="{ny}" font-size="9" fill="{PALETTE["accent"]}">{_esc(n)}</text>'
            ny -= 12
        return head + bg + tt + self._grid() + "".join(self.parts) + self._legend() + notes + "</svg>"

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.svg())
        return path


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def bar_svg(title, subtitle, rows, path, w=680, unit="", ref_label="合格区"):
    """横向条形图(零依赖)。rows: [(label, value, lo, hi, color, note)]。
    lo/hi 为合格参考带(None 则不画)。value 画成条, 带外变红。"""
    n = len(rows)
    row_h = 30
    top = 56
    h = top + n * row_h + 40
    ml, mr = 150, 90
    pw = w - ml - mr
    vmax = max([abs(r[1]) for r in rows] + [abs(r[3]) if r[3] else 0 for r in rows] + [1e-9]) * 1.15
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="Segoe UI, Arial, sans-serif">']
    out.append(f'<rect width="{w}" height="{h}" fill="#ffffff"/>')
    out.append(f'<text x="{w/2}" y="20" font-size="14" font-weight="600" fill="{PALETTE["ink"]}" text-anchor="middle">{_esc(title)}</text>')
    if subtitle:
        out.append(f'<text x="{w/2}" y="36" font-size="10" fill="{PALETTE["axis"]}" text-anchor="middle">{_esc(subtitle)}</text>')
    for i, (label, val, lo, hi, color, note) in enumerate(rows):
        y = top + i * row_h
        out.append(f'<text x="{ml-8}" y="{y+13}" font-size="11" fill="{PALETTE["ink"]}" text-anchor="end">{_esc(label)}</text>')
        # ref band
        if lo is not None and hi is not None:
            x0 = ml + lo / vmax * pw; x1 = ml + hi / vmax * pw
            out.append(f'<rect x="{x0:.1f}" y="{y+3}" width="{max(1,x1-x0):.1f}" height="14" fill="#eef4fb" stroke="{PALETTE["grid"]}"/>')
        bw = abs(val) / vmax * pw
        x0 = ml if val >= 0 else ml - bw
        bad = (lo is not None and val < lo) or (hi is not None and val > hi)
        fill = PALETTE["fail"] if bad else color
        out.append(f'<rect x="{x0:.1f}" y="{y+3}" width="{bw:.1f}" height="14" fill="{fill}" fill-opacity="0.75"/>')
        vx = ml + bw + 6 if val >= 0 else ml - bw - 6
        anc = "start" if val >= 0 else "end"
        out.append(f'<text x="{vx:.1f}" y="{y+14}" font-size="10" fill="{PALETTE["ink"]}" text-anchor="{anc}">{val:.3g}{unit}</text>')
        if note:
            out.append(f'<text x="{ml+pw+8}" y="{y+14}" font-size="9" fill="{PALETTE["accent"]}">{_esc(note)}</text>')
    # ref legend
    out.append(f'<rect x="{ml}" y="{h-24}" width="14" height="10" fill="#eef4fb" stroke="{PALETTE["grid"]}"/>')
    out.append(f'<text x="{ml+20}" y="{h-15}" font-size="9" fill="{PALETTE["axis"]}">{_esc(ref_label)}</text>')
    out.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(out))
    return path
