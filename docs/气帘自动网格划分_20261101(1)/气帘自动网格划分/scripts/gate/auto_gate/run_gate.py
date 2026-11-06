#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_gate.py — auto_gate 自动校验套件编排器（案例无关，全自动，零人工干预）

用法:
  python run_gate.py --case <case.json> [--rules gate_rules.json] [--figdir <dir>] [--out <report.json>]

case.json 描述一个案例(输入 K / CAD 线 / PID 方案 / 角色 Y 分层 / CAD tag 映射)。
换案例只换 case.json; 门限/口径在 gate_rules.json 迭代完善。脚本内零案例硬编码。

产出:
  * 控制台 PASS/WARN/FAIL 汇总
  * <figdir>/*.svg  自出图审查(环面积/周长/几何匹配/拉带连接/分层)
  * <out> JSON 报告 + <out>.txt 文本报告
退出码: 0=PASS/WARN, 1=FAIL
"""
import argparse
import json
import os
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import kio
import checks


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def expand(p):
    """展开案例配置里的 ${WORKDIR} / $WORKDIR 占位符（未设则取当前目录）。"""
    if not isinstance(p, str):
        return p
    wd = os.environ.get("WORKDIR", ".")
    return p.replace("${WORKDIR}", wd).replace("$WORKDIR", wd)


def remap_axes(K, thickness_axis):
    """把节点坐标重排为 checks.py 约定的内部布局 (u, w, v) = (平面U, 厚度, 平面V)。

    checks.py 全部判据都是按 (x, y, z) -> 平面=(x,z)、厚度=y 写的（沉淀自 cab1：
    气帘几何在 X-Z 平面、Y 为厚度轴）。不同项目厚度轴不同，故在读入后统一重排，
    **不改任何判据逻辑**。
      thickness_axis="Y" (默认, cab1) -> (x, y, z)  原样, 平面=X-Z
      thickness_axis="Z" (cab2)       -> (x, z, y)  平面=X-Y
      thickness_axis="X"              -> (y, x, z)  平面=Y-Z
    返回实际生效的轴名与平面跨度，便于在报告里显式记录（防止轴向猜错静默通过）。
    """
    ax = (thickness_axis or "Y").strip().upper()
    if ax not in ("X", "Y", "Z"):
        raise SystemExit(f"[case] thickness_axis 非法: {thickness_axis!r} (应为 X/Y/Z)")
    if ax == "Y":
        perm = (0, 1, 2)          # 平面 X-Z, 厚度 Y
    elif ax == "Z":
        perm = (0, 2, 1)          # 平面 X-Y, 厚度 Z
    else:
        perm = (1, 0, 2)          # 平面 Y-Z, 厚度 X
    if perm != (0, 1, 2):
        K["nodes"] = {n: (c[perm[0]], c[perm[1]], c[perm[2]])
                      for n, c in K["nodes"].items()}
    return ax, perm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, help="案例配置 JSON")
    ap.add_argument("--rules", default=os.path.join(HERE, "gate_rules.json"))
    ap.add_argument("--figdir", default=None, help="出图目录(默认 <case出目录>/gate_figs)")
    ap.add_argument("--out", default=None, help="JSON 报告路径")
    a = ap.parse_args()

    case = load_json(a.case)
    rules = load_json(a.rules)
    kfile = expand(case["k_file"])
    case["cad_lines_2d"] = expand(case.get("cad_lines_2d"))
    figdir = a.figdir or os.path.join(os.path.dirname(os.path.abspath(kfile)), "gate_figs")
    os.makedirs(figdir, exist_ok=True)
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(kfile)), "gate_report.json")

    print("=" * 74)
    print(f"auto_gate 自动校验套件 | case={case.get('case','?')} | rules={os.path.basename(a.rules)} v{rules.get('_version','?')}")
    print(f"K = {kfile}")
    print("=" * 74)

    K = kio.parse_kfile(kfile)
    print(f"解析: 节点 {len(K['nodes'])} | PID { {p:len(e) for p,e in K['elems'].items()} }")
    ax, perm = remap_axes(K, case.get("thickness_axis", "Y"))
    _u = [c[0] for c in K["nodes"].values()]
    _w = [c[1] for c in K["nodes"].values()]
    _v = [c[2] for c in K["nodes"].values()]
    print(f"轴向: 厚度轴={ax} (内部布局 平面U={_u and round(max(_u)-min(_u),1)}mm / "
          f"厚度={round(max(_w)-min(_w),2)}mm / 平面V={round(max(_v)-min(_v),1)}mm)")
    if max(_w) - min(_w) > max(max(_u) - min(_u), max(_v) - min(_v)) * 0.5:
        print(f"[warn] 厚度轴跨度 {round(max(_w)-min(_w),2)}mm 过大 —— 疑似 thickness_axis 配错，"
              f"分层/几何检查结论不可信")
    cad = checks.parse_cad_lines(case.get("cad_lines_2d"))
    if cad:
        print(f"CAD 线: { {t:len(v) for t,v in cad.items()} }")

    results = []
    results.append(checks.check_topology(K, rules, case))
    results.append(checks.check_layers(K, rules, case))
    if cad:
        results.append(checks.check_ring_area_perimeter(K, rules, case, cad, figdir))
        results.append(checks.check_ring_geometry(K, rules, case, cad, figdir))
    else:
        print("[warn] 无 CAD 线, 跳过环面积/几何匹配(仍跑拓扑/分层/拉带)")
    results.append(checks.check_tether(K, rules, case, figdir))

    # 控制台汇总
    icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}
    for r in results:
        print(f"\n[{icon.get(r['status'],'?')} {r['status']}] {r['name']}: {r['summary']}")
        for row in r["detail"]:
            label, val, st = row
            st_show = icon.get(st, "  ") if st in icon else "·"
            print(f"     {st_show} {label}: {val}")

    overall = checks.overall_status(results)
    print("\n" + "=" * 74)
    print(f"总判定: {icon.get(overall,'?')} {overall}   (PASS {sum(1 for r in results if r['status']=='PASS')} / "
          f"WARN {sum(1 for r in results if r['status']=='WARN')} / FAIL {sum(1 for r in results if r['status']=='FAIL')})")
    all_figs = [f for r in results for f in r["figures"]]
    print(f"自出图审查: {len(all_figs)} 张 -> {figdir}")
    for f in all_figs:
        print(f"   - {os.path.basename(f)}")
    print("=" * 74)

    # 落报告
    report = {
        "case": case.get("case"),
        "k_file": kfile,
        "thickness_axis": ax,
        "rules_version": rules.get("_version"),
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "overall": overall,
        "results": results,
        "figures": [os.path.abspath(f) for f in all_figs],
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(out + ".txt", "w", encoding="utf-8") as f:
        f.write(f"auto_gate 报告 | case={case.get('case')} | 总判定 {overall}\n")
        f.write(f"K={kfile}\nrules v{rules.get('_version')} | {report['timestamp']}\n")
        f.write("=" * 60 + "\n")
        for r in results:
            f.write(f"[{r['status']}] {r['name']}: {r['summary']}\n")
            for label, val, st in r["detail"]:
                f.write(f"    {st:>4} | {label}: {val}\n")
        f.write(f"\n图: {len(all_figs)} 张 -> {figdir}\n")
    print(f"报告: {out} (+ .txt)")

    sys.exit(0 if overall in ("PASS", "WARN") else 1)


if __name__ == "__main__":
    main()
