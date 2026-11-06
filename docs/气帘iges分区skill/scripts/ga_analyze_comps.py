# -*- coding: utf-8 -*-
"""金标准组件分析器（通用）：<workdir> -> 每组件几何聚合 + 逐组件高亮渲染

用法:
  python ga_analyze_comps.py <workdir> [--no-render]

输入:
  <workdir>/out/features.json    (feat_driver.py 产出，str 键)
  <workdir>/out/comp_lines.json  (t09_dump_comps.tcl 产出，comp -> [line ids])
  <workdir>/out/lines_pts.txt    (t02_export_pts.tcl 产出，渲染用)
输出:
  终端打印聚合表（每组件：线数 / 中位线长 / 中位凸包距 / 中位半径 / 外壳序 / n_tan / 闭合率 / 角覆盖）
  <workdir>/out/golden_panels.png  （若渲染）
"""
import os, sys, json, math
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import featurize as F


def med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else float("nan")


def ang_cover(angs, bin_deg=10):
    if not angs:
        return 0
    nbin = int(360 / bin_deg)
    hit = [0] * nbin
    for a in angs:
        hit[int((a + 180) // bin_deg) % nbin] = 1
    # 最长连续覆盖段（环向）
    best = cur = 0
    for i in range(2 * nbin):
        if hit[i % nbin]:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return min(best, nbin) * bin_deg


def main():
    wd = sys.argv[1].rstrip("/\\")
    do_render = "--no-render" not in sys.argv[2:]

    feat = json.load(open(wd + "/out/features.json"))["features"]
    comp = json.load(open(wd + "/out/comp_lines.json"))
    meta = json.load(open(wd + "/out/features.json"))["__meta__"]

    print("### %s  plane=%s  lines=%d  comps=%d" % (
        wd, "X-Z" if meta.get("use_z") else "X-Y", len(feat), len(comp)))
    hdr = "%-22s %5s %8s %8s %8s %7s %7s %6s %7s" % (
        "comp", "n", "lenMed", "dhullMd", "midrMd", "shell", "nTan", "close%", "angCov")
    print(hdr)
    print("-" * len(hdr))
    rows = {}
    for cn in sorted(comp):
        ls = [l for l in comp[cn] if str(l) in feat]
        if not ls:
            print("%-22s %5d  (no features)" % (cn, len(comp[cn])))
            continue
        agg = defaultdict(list)
        angs = []
        for l in ls:
            f = feat[str(l)]
            for k in ("len_n", "dhull_n", "midr_n", "minr_n", "shell_rank", "n_tan", "closed"):
                agg[k].append(f[k])
            angs.append(math.degrees(math.atan2(f["cy_n"], f["cx_n"])))
        n = len(ls)
        rows[cn] = dict(n=n, len=med(agg["len_n"]), dhull=med(agg["dhull_n"]),
                        midr=med(agg["midr_n"]), shell=med(agg["shell_rank"]),
                        ntan=med(agg["n_tan"]), closed=sum(agg["closed"]) / n,
                        cover=ang_cover(angs), minr=min(agg["minr_n"]))
        r = rows[cn]
        print("%-22s %5d %8.4f %8.4f %8.4f %7.2f %7.1f %6.0f%% %6d" % (
            cn, r["n"], r["len"], r["dhull"], r["midr"], r["shell"], r["ntan"],
            r["closed"] * 100, r["cover"]))

    json.dump(rows, open(wd + "/out/comp_agg.json", "w"), indent=1)
    if not do_render:
        return

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    meta2 = meta
    use_z = meta2["use_z"]
    iz = 2 if use_z else 1     # X-Z 平面取 (x,z)，X-Y 平面取 (x,y)
    P = {}
    for line in open(wd + "/out/lines_pts.txt", encoding="utf-8", errors="ignore"):
        if not line.startswith("L "):
            continue
        try:
            lid = int(line.split()[1])
            seg = line.split("|", 1)[1].strip()
            pts = []
            for t in seg.split(";"):
                v = t.split()
                if len(v) >= 3:
                    pts.append((float(v[0]), float(v[iz])))
            if len(pts) >= 2:
                P[lid] = pts
        except Exception:
            continue

    lid2comp = {}
    for cn, ls in comp.items():
        for l in ls:
            lid2comp[l] = cn
    names = sorted(comp)
    palette = ["tab:red", "tab:green", "tab:blue", "tab:orange", "tab:purple", "tab:brown", "k"]
    cmap = {cn: palette[i % len(palette)] for i, cn in enumerate(names)}

    k = len(names)
    ncol = 2 if k <= 4 else 3
    nrow = int(math.ceil(k / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(7 * ncol, 5 * nrow))
    if k == 1:
        axes = [[axes]]
    axes = [axes] if nrow == 1 and ncol == 1 else axes
    flat = []
    for a in (axes if isinstance(axes, list) else axes.ravel()):
        flat.append(a)
    for i, cn in enumerate(names):
        ax = flat[i]
        for lid, pts in P.items():
            c = lid2comp.get(lid)
            if c == cn:
                ax.plot([p[0] for p in pts], [p[1] for p in pts], color=cmap[cn], lw=1.6, zorder=3)
            else:
                ax.plot([p[0] for p in pts], [p[1] for p in pts], color="0.85", lw=0.6, zorder=2)
        ax.set_aspect("equal")
        ax.set_title("%s  (n=%d)" % (cn, len(comp[cn])), fontsize=11)
        ax.set_xticks([]); ax.set_yticks([])
    for j in range(len(names), len(flat)):
        flat[j].axis("off")
    plt.tight_layout()
    out = wd + "/out/golden_panels.png"
    plt.savefig(out, dpi=120, facecolor="white")
    print("panels ->", out)


if __name__ == "__main__":
    main()
