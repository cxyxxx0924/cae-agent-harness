# -*- coding: utf-8 -*-
"""由 comp_lines.json + 映射表生成金标签 golden_line_comp.json（通用）

用法:
  python ga_build_golden.py <workdir> --map L1=BELT,L2=CAVITY,L3=SEAM,L4=TETHER,L5=TETHER,_lines0_Wireframe=lines0
      映射可省略：若 comp 名本身已是 BELT/CAVITY/SEAM/TETHER/lines0 则自动采用。

输出:
  <workdir>/out/golden_line_comp.json  {"line_comp": {id: cls}}
并打印每类线数，做健全性检查（未知 comp 名必须显式映射）。
"""
import sys, json, os
from collections import Counter

CLASSES = {"BELT", "CAVITY", "SEAM", "TETHER", "lines0"}


def main():
    wd = sys.argv[1].rstrip("/\\")
    mp = {}
    args = sys.argv[2:]
    specs = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--map" and i + 1 < len(args):
            specs.append(args[i + 1]); i += 2; continue
        if a.startswith("--map="):
            specs.append(a[len("--map="):]); i += 1; continue
        i += 1
    for spec in specs:
        for item in spec.split(","):
            if not item.strip():
                continue
            k, v = item.split("=", 1)
            mp[k.strip()] = v.strip()
    comp = json.load(open(wd + "/out/comp_lines.json"))

    # 自动识别：comp 名本身就是类名
    for cn in comp:
        if cn.upper().replace("_LINES0_WIREFRAME", "LINES0") in CLASSES and cn not in mp:
            u = cn.upper()
            if u in CLASSES:
                mp[cn] = u

    unknown = [cn for cn in comp if cn not in mp]
    if unknown:
        print("[ERROR] 以下组件没有映射，必须显式指定：", unknown)
        print("        现有映射：", mp)
        sys.exit(2)

    gold = {}
    for cn, ls in comp.items():
        cls = mp[cn]
        if cls not in CLASSES:
            print("[ERROR] 未知类别", cls, "于组件", cn)
            sys.exit(2)
        for l in ls:
            gold[str(l)] = cls

    json.dump({"line_comp": gold}, open(wd + "/out/golden_line_comp.json", "w"), indent=0)

    print("mapping:", mp)
    tot = Counter()
    for cn, ls in comp.items():
        tot[mp[cn]] += len(ls)
        print("  %-22s -> %-7s %4d" % (cn, mp[cn], len(ls)))
    print("class totals:", dict(tot), " | total lines:", len(gold))
    # 只统计实际分类（不含 lines0）
    cls_only = {k: v for k, v in tot.items() if k != "lines0"}
    print("classified (excl lines0):", sum(cls_only.values()))


if __name__ == "__main__":
    main()
