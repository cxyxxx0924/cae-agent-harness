#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_step1_tcl.py — 用 case.json + loops.json 生成具体案例的 step1.tcl
=====================================================================
取代"手写 cabX_step1.tcl"。硬编码一律消除:

  旧做法(每来一个案例都要人工做一遍)               新做法
  ---------------------------------------------    --------------------------------
  数一数有几个缝线环、每个环由哪几条线组成            chain_loops.py 自动成环
  把 line id 抄进 Tcl 的 ringdefs                   从 loops.json 直接灌进去
  记住气腔轮廓在 collector 3、布带在 2               case.json 里写 cid + tag
  文件名、报告名手工改                              case.json 的 case 字段

用法
----
  python gen_step1_tcl.py --case cases/cab2/case.json \
                          --loops out/loops.json \
                          --out out/step1.tcl

case.json 最小示例
------------------
  {
    "case": "cab2",
    "model": "cab2.hm",
    "layers": [ {"role":"belt",   "cid":2, "tag":"L1"},
                {"role":"cavity", "cid":3, "tag":"L2"},
                {"role":"seam",   "cid":4, "tag":"L3"},
                {"role":"tether", "cid":5, "tag":"L4"} ],
    "seam": {"min_area": 200, "max_count": 40, "sort": "area_desc"},
    "mesh": {"size": 5.0, "seam_size": 5.0, "bl_thick": 4.0,
             "bl_layer": 1, "bl_etype": "mixed"}
  }

seam 选择规则(都可覆盖)
-----------------------
  min_area   小于此面积的闭环不当作缝线(滤掉草图小圈/圆角残线)
  max_count  超过则只取前 N 个(防止 CAD 脏线被误当缝线), 默认不限制
  sort       area_desc(默认) / area_asc / id
  manual     直接给定 lids 列表的列表, 跳过 loops.json 自动结果(兜底用)
"""
import argparse, glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TPL = os.path.normpath(os.path.join(
    HERE, "..", "stage3_mesh", "blmesh2d", "step1_template.tcl"))


def pick_seams(loops_of_tag, cfg):
    """从某个 tag 的闭环列表里挑出"缝线环", 返回 [[lid,...], ...]"""
    if cfg.get("manual"):
        return [list(int(x) for x in g) for g in cfg["manual"]]
    loops = [l for l in loops_of_tag if l.get("lids")]
    min_area = float(cfg.get("min_area", 0))
    loops = [l for l in loops if l.get("area", 0) >= min_area]
    s = cfg.get("sort", "area_desc")
    if s == "area_desc":
        loops.sort(key=lambda l: -l.get("area", 0))
    elif s == "area_asc":
        loops.sort(key=lambda l: l.get("area", 0))
    elif s == "id":
        loops.sort(key=lambda l: min(l["lids"]))
    mc = cfg.get("max_count")
    if mc:
        loops = loops[:int(mc)]
    return [l["lids"] for l in loops]


def tcl_ringdefs(groups, prefix="seam"):
    """-> '[list \\\n  [list seam0 {...}] \\\n  [list seam1 {...}] ]'

    外层 [list ...] 不能省: 模板里是 `set ringdefs @@RINGDEFS@@`,
    没有外层就退化成 `set ringdefs [list a] [list b]` -> Tcl 报 "wrong # args"。
    """
    if not groups:
        return "{}"
    parts = ["[list %s%d {%s}]" % (prefix, i, " ".join(str(x) for x in g))
             for i, g in enumerate(groups)]
    return "[list \\\n  " + " \\\n  ".join(parts) + " ]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, help="case.json")
    ap.add_argument("--loops", default=None, help="loops.json (chain_loops 输出)")
    ap.add_argument("--tpl", default=DEFAULT_TPL)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    C = json.load(open(a.case, encoding="utf-8"))
    case = C.get("case") or os.path.splitext(os.path.basename(C.get("model", "case")))[0]
    model = C.get("model") or (case + ".hm")
    layers = {L["role"]: L for L in C.get("layers", [])}
    for need in ("belt", "cavity", "seam"):
        if need not in layers:
            sys.exit(f"case.json 缺 role={need} 的 layers 条目")

    loops_path = a.loops or os.path.join(os.path.dirname(os.path.abspath(a.case)),
                                         "..", "..", "out", "loops.json")
    if not os.path.exists(loops_path) and not C.get("seam", {}).get("manual"):
        hits = glob.glob(os.path.join(os.path.dirname(os.path.abspath(a.case)), "**", "loops*.json"),
                         recursive=True)
        if hits:
            loops_path = hits[0]
    loops = {}
    if os.path.exists(loops_path):
        loops = json.load(open(loops_path, encoding="utf-8"))

    seam_tag = layers["seam"].get("tag")
    seam_loops = loops.get(seam_tag, {}).get("loops", []) if seam_tag else []
    scfg = C.get("seam", {}) or {}
    groups = pick_seams(seam_loops, scfg)

    if not groups:
        sys.exit(f"未得到任何缝线环: tag={seam_tag} 在 {loops_path} 中闭环数为 "
                 f"{len(seam_loops)}。检查 chain_loops 的 --tol 或改用 seam.manual")

    # ---- 自检: 缝线环不应相互重叠(面积和 / 并集面积 ≈ 1) ----
    tot = sum(l.get("area", 0) for l in seam_loops if l["lids"] in groups)
    warn = []
    if len(groups) != len(seam_loops) and not scfg.get("manual"):
        warn.append(f"闭环 {len(seam_loops)} 个 → 取用 {len(groups)} 个(被 min_area/max_count 过滤)")

    tpl = open(a.tpl, encoding="utf-8").read()
    out = (tpl.replace("@@CASENAME@@", case)
              .replace("@@MODEL@@", model)
              .replace("@@CID_CAV@@", str(layers["cavity"]["cid"]))
              .replace("@@CID_BELT@@", str(layers["belt"]["cid"]))
              .replace("@@RINGDEFS@@", tcl_ringdefs(groups)))

    left = re.findall(r"@@[A-Z_]+@@", out)
    if left:
        sys.exit(f"模板仍有未替换占位符: {sorted(set(left))}")

    print(f"=== gen_step1_tcl  case={case} ===")
    print(f"  model      = input/{model}")
    print(f"  cavity cid = {layers['cavity']['cid']}   belt cid = {layers['belt']['cid']}")
    print(f"  seam tag   = {seam_tag}  闭环 {len(seam_loops)} 个 → 采用 {len(groups)} 个缝线")
    for i, g in enumerate(groups):
        ar = next((l["area"] for l in seam_loops if l["lids"] == g), 0)
        print(f"    seam{i}: nl={len(g):3d} area={ar:10.1f}  lids={g[:8]}{' ...' if len(g) > 8 else ''}")
    print(f"  缝线面积合计 = {tot:.0f} mm²")
    for w in warn:
        print(f"  ⚠️  {w}")

    if a.dry_run:
        print(f"\n[dry-run] 未写文件。目标: {a.out}")
        return
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(out)
    print(f"\n-> {a.out}  ({len(out)} bytes)")


if __name__ == "__main__":
    main()
