#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_ring_spec.py — 由分区结果生成 ring_spec.json (geom_match_check.py 的输入)
========================================================================
把"每个环 = 哪些 IGES 线"的声明, 落成 geom_match_check 要的 JSON。

输入 (都可选, 按项目提供):
  --classify  classify_final.json  (含 {"line_comp": {"1":"BELT", "2":"BELT", ...}})
            -> 自动生成 belt / cavity / seam 三个大环 (按 comp 收集线 id)
  --footprints  JSON: {"boss":[[L1,L2,...],[L3,L4,...],...], "strap": true}
            -> 每个 list 是一项"存活的足印环"(凸台矩形环 / 拉带外轮廓), type=tether_boss
               (穹顶等被 drop 的内层片不要放进这里, 它们不在最终网格里)
            -> strap=true 时追加一条 type=tether_strap 的构造件 (无 IGES 基准, 自检跳过几何)
  --mesh-map  xy|xz  (默认 xy, 与 geom_match_check 的 --map 对应)

输出 ring_spec.json:
  {"mesh_map":"xy",
   "rings":[{"name":"belt","type":"belt","iges_lines":[...]},
            {"name":"cavity","type":"cav","iges_lines":[...]},
            {"name":"seam","type":"seam","iges_lines":[...]},
            {"name":"boss0","type":"tether_boss","iges_lines":[...]},
            ...
            {"name":"strap_r","type":"tether_strap","iges_lines":[],"constructed":true}]}

用法示例 (NEW_CAB):
  python scripts/gen_ring_spec.py \
    --classify out/classify_final.json \
    --footprints assets/ringdef_newcab.json \
    --out out/ring_spec.json
"""
import argparse, json, sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classify", default=None)
    ap.add_argument("--footprints", default=None)
    ap.add_argument("--mesh-map", default="xy", choices=["xy", "xz"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    rings = []

    # 1) 大环: 从 classify 的 comp 分组
    if a.classify:
        data = json.load(open(a.classify, encoding="utf-8"))
        lc = data.get("line_comp", {})
        by_comp = {}
        for lid, comp in lc.items():
            by_comp.setdefault(comp, []).append(int(lid))
        # 环面(BELT/CAVITY)与多段细线(SEAM 哑铃)都是"凸包≠真实面积"的几何 ->
        # 关掉面积判据, 只查边界贴合(网格是否覆盖 CAD 曲线) + 位置(凸包质心)
        area_check = {"BELT": False, "CAVITY": False, "SEAM": False}
        pid_of = {"BELT": 2, "CAVITY": 3, "SEAM": 4}
        # 气腔口部是图纸固有开口(充气口领圈缺口, 用户明确不封闭) -> 边界容差放宽到 15mm
        bnd_tol_of = {"BELT": 8, "CAVITY": 15, "SEAM": 10}
        for comp in ("BELT", "CAVITY", "SEAM"):
            if comp in by_comp:
                cname = {"BELT": "belt", "CAVITY": "cavity", "SEAM": "seam"}[comp]
                ctype = {"BELT": "belt", "CAVITY": "cav", "SEAM": "seam"}[comp]
                rings.append({"name": cname, "type": ctype, "iges_lines": sorted(by_comp[comp]),
                             "area_check": area_check[comp], "mesh_pid": pid_of[comp],
                             "bnd_tol": bnd_tol_of[comp]})

    # 2) 拉带足印环 + 构造长条
    if a.footprints:
        fp = json.load(open(a.footprints, encoding="utf-8"))
        for i, grp in enumerate(fp.get("boss", [])):
            rings.append({"name": f"boss{i}", "type": "tether_boss", "iges_lines": sorted(int(x) for x in grp),
                         "mesh_pid": 5})
        if fp.get("strap"):
            rings.append({"name": "strap_r", "type": "tether_strap", "iges_lines": [], "constructed": True,
                         "mesh_pid": 5})

    spec = {"mesh_map": a.mesh_map, "rings": rings}
    open(a.out, "w", encoding="utf-8").write(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
    print(f"ring_spec.json: {len(rings)} 环 -> {a.out}")
    for r in rings:
        nl = len(r["iges_lines"])
        extra = " (constructed)" if r.get("constructed") else ""
        print(f"  {r['name']:<12} {r['type']:<12} iges_lines={nl}{extra}")


if __name__ == "__main__":
    main()
