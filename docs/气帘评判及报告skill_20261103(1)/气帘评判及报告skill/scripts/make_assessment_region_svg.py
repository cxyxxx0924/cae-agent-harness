#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the G.14.3 assessment-region schematic SVG from head-barycenter
points. The four rounded-quadrant centers are the dummy head CoG coordinates;
this draws them on a side (X-Z) and top (X-Y) view so the report can show
WHERE the assessment regions sit relative to the curtain head-height band.

Usage:
    python make_assessment_region_svg.py --out assessment_region.svg \
        --heads '{"1ROW@60":[3197.2,-449.4,1405.2,160.9], ...}'

heads json: { name: [X, Y, Z, IC_thickness_mm], ... }
"""
import argparse
import json
import xml.sax.saxutils as su


def panel(pts, xkey, ykey, xlabel, ylabel, xr, yr, ox, oy, w, h, title):
    def mx(v):
        return ox + 60 + (v - xr[0]) / (xr[1] - xr[0]) * (w - 100)

    def my(v):
        return oy + h - 50 - (v - yr[0]) / (yr[1] - yr[0]) * (h - 90)

    s = []
    s.append(f'<rect x="{ox}" y="{oy}" width="{w}" height="{h}" fill="#ffffff" stroke="#cccccc"/>')
    s.append(f'<text x="{ox+w/2}" y="{oy+22}" font-size="15" font-family="Arial" font-weight="bold" text-anchor="middle" fill="#1f3a5f">{su.escape(title)}</text>')
    s.append(f'<text x="{ox+w/2}" y="{oy+h-12}" font-size="12" font-family="Arial" text-anchor="middle" fill="#555">{su.escape(xlabel)}</text>')
    s.append(f'<text x="{ox+14}" y="{oy+h/2}" font-size="12" font-family="Arial" text-anchor="middle" fill="#555" transform="rotate(-90 {ox+14} {oy+h/2})">{su.escape(ylabel)}</text>')
    for i in range(5):
        tx = xr[0] + (xr[1] - xr[0]) * i / 4
        px = mx(tx)
        s.append(f'<line x1="{px}" y1="{oy+h-50}" x2="{px}" y2="{oy+h-45}" stroke="#999"/>')
        s.append(f'<text x="{px}" y="{oy+h-38}" font-size="9" font-family="Arial" text-anchor="middle" fill="#777">{tx:.0f}</text>')
        ty = yr[0] + (yr[1] - yr[0]) * i / 4
        py = my(ty)
        s.append(f'<line x1="{ox+60}" y1="{py}" x2="{ox+65}" y2="{py}" stroke="#999"/>')
        s.append(f'<text x="{ox+58}" y="{py+3}" font-size="9" font-family="Arial" text-anchor="end" fill="#777">{ty:.0f}</text>')
    for name, (x, y, z, t) in pts.items():
        X = x if xkey == "x" else (y if xkey == "y" else z)
        Y = y if ykey == "y" else (z if ykey == "z" else x)
        px, py = mx(X), my(Y)
        s.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="#c0392b" stroke="#7b241c" stroke-width="1.5"/>')
        s.append(f'<text x="{px+9:.1f}" y="{py-7:.1f}" font-size="10" font-family="Arial" fill="#1f3a5f">{su.escape(name)}</text>')
        s.append(f'<text x="{px+9:.1f}" y="{py+5:.1f}" font-size="9" font-family="Arial" fill="#2e7d32">IC {t}mm</text>')
    return "\n".join(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--heads", required=True, help='json {name:[X,Y,Z,thk]}')
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    heads = json.loads(args.heads)

    xs = [v[0] for v in heads.values()]
    ys = [v[1] for v in heads.values()]
    zs = [v[2] for v in heads.values()]
    xr = (min(xs) - 120, max(xs) + 120)
    zr = (min(zs) - 80, max(zs) + 80)
    yr = (min(ys) - 120, max(ys) + 120)

    W, H = 900, 520
    b = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
    b.append('<rect width="100%" height="100%" fill="#f7f9fc"/>')
    b.append(f'<text x="{W/2}" y="28" font-size="17" font-family="Arial" font-weight="bold" text-anchor="middle" fill="#15233b">G.14.3 评估区域锚点 — 假人头部重心(CoG)坐标 (车辆坐标系, mm)</text>')
    b.append('<text x="20" y="48" font-size="11" font-family="Arial" fill="#666">圆心 = 参考报告头部重心坐标; 标注 = 该点处充气厚度(来自参考报告静态充气分析 @35kPa)</text>')
    b.append(panel(heads, "x", "z", "X 纵向 (mm)", "Z 高度 (mm)", xr, zr, 20, 60, 420, 430, "侧视图 (X–Z): 前后排头部高度带"))
    b.append(panel(heads, "x", "y", "X 纵向 (mm)", "Y 横向 (mm)", xr, yr, 460, 60, 420, 430, "俯视图 (X–Y): 左右侧乘员头部分布"))
    b.append('</svg>')
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(b))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
