#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""case_env.py — 把 case.json 摊平成 shell 变量, 供 run_case.sh 求值
=================================================================
  eval "$(python case_env.py --case cases/cab2/case.json)"
输出形如:
  export CASE=cab2
  export MODEL=cab2.hm
  export COMPS='2 L1 3 L2 4 L3 5 L4'
  export MESHSIZE=5.0
  ...
--comps 只打印 COMPS 串(给 export_lines_pts.tcl 用)。
"""
import argparse, json, sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--comps", action="store_true", help="只打印 'cid tag cid tag ...'")
    a = ap.parse_args()

    C = json.load(open(a.case, encoding="utf-8"))
    layers = C.get("layers", [])
    comps = " ".join(f'{L["cid"]} {L["tag"]}' for L in sorted(layers, key=lambda x: x["cid"]))

    if a.comps:
        print(comps)
        return

    def g(*ks, d=None):
        cur = C
        for k in ks:
            if not isinstance(cur, dict) or k not in cur:
                return d
            cur = cur[k]
        return cur

    mesh = C.get("mesh", {}) or {}
    roles = {L["role"]: L for L in layers}
    out = {
        "CASE": C.get("case") or "case",
        "MODEL": C.get("model") or (C.get("case", "case") + ".hm"),
        "COMPS": comps,
        "LOOP_TOL": C.get("loop_tol", 0.8),
        "MESHSIZE": mesh.get("size", 5.0),
        "SEAMSIZE": mesh.get("seam_size", mesh.get("size", 5.0)),
        "BL_THICK": mesh.get("bl_thick", 4.0),
        "BL_LAYER": mesh.get("bl_layer", 1),
        "BL_ETYPE": mesh.get("bl_etype", "mixed"),
        "PID_BELT": g("belt", "pid", d=roles.get("belt", {}).get("pid", 2)),
        "PID_CAV": roles.get("cavity", {}).get("pid", 3),
        "PID_SEAM": roles.get("seam", {}).get("pid", 4),
        "PID_TETHER": roles.get("tether", {}).get("pid", 5),
        "CID_BELT": roles.get("belt", {}).get("cid", 2),
        "CID_CAV": roles.get("cavity", {}).get("cid", 3),
        "CID_SEAM": roles.get("seam", {}).get("cid", 4),
        "CID_TETHER": roles.get("tether", {}).get("cid", 5),
    }
    z = roles.get("cavity", {}).get("z") or [-0.5, 0.5]
    out["Z_CAV"] = abs(float(z[0])) if z else 0.5
    zt = roles.get("tether", {}).get("z") or [-1.0]
    out["Z_TAB"] = float(zt[0]) if zt else -1.0

    # ---- 部件清单（缺件必须硬失败，防"整块丢"静默通过；references/04 P49）----
    parts = C.get("parts")
    if not parts:
        parts = [L["role"] for L in layers]
    out["REQUIRE_PARTS"] = " ".join(str(p) for p in parts)
    out["SKIP_TETHER"] = 1 if C.get("skip_tether") else 0

    # ---- 组装/锚固参数（案例级定版值，别在脚本里改）----
    asm = C.get("assemble", {}) or {}
    out["TAB_TOL"] = asm.get("tab_tol", 0.35)
    out["SNAP_INSIDE_TOL"] = asm.get("snap_inside_tol", 0.0)
    out["WEAK_ANCHOR_MIN"] = asm.get("weak_anchor_min", 1)
    out["ANCHORED_TETHERS"] = 1 if asm.get("anchored_tethers") else 0
    out["EDGE_BAND"] = asm.get("edge_band", 4.0)
    out["TABS_POLYS"] = asm.get("tabs_polys", "") or ""
    # 拉带网格文件名（相对 out/）。不给就按 <case>_step2*.txt 推。
    out["STEP2"] = asm.get("step2", "") or ""
    out["STEP2B"] = asm.get("step2b", "") or ""

    # ---- 门禁基线（写过基线才有意义；路径相对 WORKDIR）----
    g2 = C.get("gates", {}) or {}
    out["PARTITION_MANIFEST"] = g2.get("partition_manifest", "") or ""
    out["GATE_CASE"] = g2.get("gate_case", "") or ""

    for k, v in out.items():
        print(f"export {k}={v!r}")


if __name__ == "__main__":
    main()
