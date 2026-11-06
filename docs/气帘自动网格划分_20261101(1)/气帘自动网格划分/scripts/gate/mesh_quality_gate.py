# -*- coding: utf-8 -*-
"""mesh_quality_gate.py — 通用碰撞壳网格质量门禁（与分区/项目无关）

设计目标：任何"布带/气腔/缝线/拉带"这类分区壳网格 K 文件，都能用同一套口径打分，
输出 PASS/WARN/FAIL + 不合格区聚类坐标，用于"划完即判、判完再修"的自动闭环。

判据（可按 config 覆盖；默认取整车碰撞壳单元常用值）
------------------------------------------------------
  四边形最小内角   min_angle_quad  >= 30°      (WARN 若 <35° 占比>1%)
  三角形最小内角   min_angle_tria  >= 20°
  长宽比           aspect          <= 3.0
  雅可比           jacobian        >= 0.6
  翘曲             warp            <= 5°
  三角形占比       tria_ratio      <= 8%      (过渡区允许三角形，但不能成片)
  相邻单元尺寸比   size_gradient   <= 2.0     (可选)

用法
----
  python mesh_quality_gate.py model.k                        # 全部 PID 一起看
  python mesh_quality_gate.py model.k --pids 2,3,4,5
  python mesh_quality_gate.py model.k --cfg q.json --out q.json --png q.png
  python mesh_quality_gate.py model.k --ref ref.key          # 与参考模型并排比

退出码: 0 = PASS, 1 = WARN, 2 = FAIL（便于流水线串接）

本文件零第三方依赖（matplotlib 仅出图时用，没有就跳过）。
"""
import argparse, collections, json, math, os, sys

DEFAULT = {
    "min_angle_quad": 30.0,
    "min_angle_tria": 20.0,
    "aspect_max": 3.0,
    "jacobian_min": 0.6,
    "warp_max": 5.0,
    "tria_ratio_max": 0.08,
    "size_gradient_max": 2.0,
    "warn_ratio": 0.01,          # 超限单元占比 > warn_ratio -> WARN; > fail_ratio -> FAIL
    "fail_ratio": 0.05,
}


# ---------------------------------------------------------------- 读 K
def read_k(path):
    """通用 LS-DYNA K 读取：认 *NODE / *ELEMENT_SHELL，逗号或定宽 8/10 列都能吃。"""
    nodes, els = {}, []
    sec = None
    with open(path, encoding="ascii", errors="ignore") as f:
        for line in f:
            if line.startswith("*"):
                sec = line.strip().upper()
                continue
            if not line.strip() or line.lstrip().startswith("$"):
                continue
            toks = [t for t in line.replace(",", " ").split() if t]
            if not toks:
                continue
            # 定宽 8 列且无分隔符时 split 会得到 1~2 个巨串
            if len(toks) < 3 and sec in ("*NODE", "*ELEMENT_SHELL"):
                w = 8
                toks = [line[i:i + w].strip() for i in range(0, len(line.rstrip("\n")), w)]
                toks = [t for t in toks if t]
            try:
                if sec == "*NODE" and len(toks) >= 4:
                    nodes[int(toks[0])] = (float(toks[1]), float(toks[2]), float(toks[3]))
                elif sec == "*ELEMENT_SHELL" and len(toks) >= 5:
                    pid = int(toks[1])
                    ns = [int(t) for t in toks[2:] if int(t) > 0]
                    if len(ns) >= 3:
                        els.append((pid, ns))
            except ValueError:
                continue
    return nodes, els


# ---------------------------------------------------------------- 单元度量
def elem_metrics(pts):
    m = len(pts)
    amin = 180.0
    for i in range(m):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % m]
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - b[0], c[1] - b[1], c[2] - b[2])
        nu = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
        nv = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
        if nu < 1e-9 or nv < 1e-9:
            return 0.0, 1e9, 0.0, 0.0
        cs = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1] + u[2] * v[2]) / (nu * nv)))
        amin = min(amin, math.degrees(math.acos(cs)))
    L = [math.dist(pts[i], pts[(i + 1) % m]) for i in range(m)]
    asp = max(L) / max(min(L), 1e-9)
    if m == 4:
        mx1 = [(pts[0][k] + pts[1][k]) / 2 for k in range(3)]
        mx2 = [(pts[2][k] + pts[3][k]) / 2 for k in range(3)]
        my1 = [(pts[1][k] + pts[2][k]) / 2 for k in range(3)]
        my2 = [(pts[3][k] + pts[0][k]) / 2 for k in range(3)]
        ax = [mx2[k] - mx1[k] for k in range(3)]
        ay = [my2[k] - my1[k] for k in range(3)]
        cr = (ax[1] * ay[2] - ax[2] * ay[1], ax[2] * ay[0] - ax[0] * ay[2], ax[0] * ay[1] - ax[1] * ay[0])
        den = math.sqrt(sum(t * t for t in ax)) * math.sqrt(sum(t * t for t in ay))
        jac = math.sqrt(sum(t * t for t in cr)) / den if den > 1e-12 else 0.0
        nn = math.sqrt(sum(t * t for t in cr)) or 1.0
        d = [[pts[i][k] - pts[0][k] for k in range(3)] for i in range(4)]
        h = [abs(sum(d[i][k] * cr[k] for k in range(3))) / nn for i in range(4)]
        warp = math.degrees(math.atan((max(h) - min(h)) / max(min(L), 1e-9)))
    else:
        jac, warp = 1.0, 0.0
    return amin, asp, jac, warp


def pct(v, q):
    if not v:
        return float("nan")
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))]


# ---------------------------------------------------------------- 主评估
def evaluate(path, cfg, pids=None):
    nodes, els = read_k(path)
    if pids:
        els = [(p, ns) for p, ns in els if p in pids]
    rec = []
    for pid, ns in els:
        pts = [nodes[n] for n in ns if n in nodes]
        if len(pts) < 3:
            continue
        a, s, j, w = elem_metrics(pts)
        isq = len(ns) == 4
        thr = cfg["min_angle_quad"] if isq else cfg["min_angle_tria"]
        bad = (a < thr) or (s > cfg["aspect_max"]) or (j < cfg["jacobian_min"]) or (w > cfg["warp_max"])
        rec.append(dict(pid=pid, n=len(ns), amin=a, asp=s, jac=j, warp=w, bad=bad,
                        c=(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)),
                        L=sum(math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))) / len(pts)))
    n = len(rec)
    if n == 0:
        return None
    tria = sum(1 for r in rec if r["n"] == 3)
    bad = [r for r in rec if r["bad"]]
    res = {
        "k_file": path, "elements": n, "nodes": len(nodes),
        "tria": tria, "tria_ratio": tria / n,
        "bad": len(bad), "bad_ratio": len(bad) / n,
        "amin_p1": pct([r["amin"] for r in rec], 0.01),
        "amin_p50": pct([r["amin"] for r in rec], 0.50),
        "asp_p95": pct([r["asp"] for r in rec], 0.95),
        "jac_p5": pct([r["jac"] for r in rec], 0.05),
        "warp_p95": pct([r["warp"] for r in rec], 0.95),
        "by_pid": {},
    }
    bp = collections.defaultdict(lambda: [0, 0])
    for r in rec:
        bp[r["pid"]][0] += 1
        if r["bad"]:
            bp[r["pid"]][1] += 1
    res["by_pid"] = {str(k): dict(elems=v[0], bad=v[1]) for k, v in sorted(bp.items())}

    # 不合格聚类
    grid = collections.defaultdict(list)
    for i, r in enumerate(bad):
        grid[(int(r["c"][0] // 15), int(r["c"][1] // 15))].append(i)
    seen, cls = set(), []
    for i in range(len(bad)):
        if i in seen:
            continue
        st = [i]; cl = []
        while st:
            q = st.pop()
            if q in seen:
                continue
            seen.add(q); cl.append(q)
            gx, gy = int(bad[q]["c"][0] // 15), int(bad[q]["c"][1] // 15)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in grid.get((gx + dx, gy + dy), ()):
                        if j not in seen and math.hypot(bad[j]["c"][0] - bad[q]["c"][0],
                                                        bad[j]["c"][1] - bad[q]["c"][1]) < 18:
                            st.append(j)
        cls.append(cl)
    cls.sort(key=len, reverse=True)
    res["clusters"] = [
        dict(n=len(c),
             center=[round(sum(bad[i]["c"][0] for i in c) / len(c), 1),
                     round(sum(bad[i]["c"][1] for i in c) / len(c), 1)],
             worst_angle=round(min(bad[i]["amin"] for i in c), 1),
             pids=sorted({bad[i]["pid"] for i in c}))
        for c in cls[:10]
    ]
    # 尺寸梯度（相邻单元平均边长比）—— 只在同 PID 内、共享边时统计
    edge2e = collections.defaultdict(list)
    for k, r in enumerate(rec):
        pts = None
    # 需要节点集：重扫一次，避免在 rec 里存大对象
    idx = 0
    for pid, ns in els:
        pts = [nodes[n] for n in ns if n in nodes]
        if len(pts) < 3:
            continue
        if idx >= n:
            break
        u = list(dict.fromkeys(ns))
        for i in range(len(u)):
            a, b = u[i], u[(i + 1) % len(u)]
            edge2e[(min(a, b), max(a, b))].append(idx)
        idx += 1
    ratios = []
    for e, lst in edge2e.items():
        if len(lst) == 2:
            l1, l2 = rec[lst[0]]["L"], rec[lst[1]]["L"]
            if min(l1, l2) > 1e-9:
                ratios.append(max(l1, l2) / min(l1, l2))
    res["size_gradient_p99"] = pct(ratios, 0.99) if ratios else float("nan")
    res["size_gradient_viol"] = sum(1 for r in ratios if r > cfg["size_gradient_max"])

    # 判定
    problems = []
    if res["bad_ratio"] > cfg["fail_ratio"]:
        verdict = "FAIL"
    elif res["bad_ratio"] > cfg["warn_ratio"]:
        verdict = "WARN"
    else:
        verdict = "PASS"
    if res["tria_ratio"] > cfg["tria_ratio_max"]:
        verdict = "FAIL" if verdict == "PASS" else verdict
        problems.append(f"三角形占比 {100*res['tria_ratio']:.1f}% > {100*cfg['tria_ratio_max']:.0f}%")
    res["verdict"] = verdict
    res["problems"] = problems
    return res


def show(tag, r):
    print(f"\n===== {tag} =====")
    print(f"  单元 {r['elements']}  节点 {r['nodes']}  三角形 {r['tria']} ({100*r['tria_ratio']:.2f}%)")
    print(f"  最小角 p1={r['amin_p1']:.1f}° p50={r['amin_p50']:.1f}°   aspect p95={r['asp_p95']:.2f}"
          f"   jac p5={r['jac_p5']:.3f}   warp p95={r['warp_p95']:.2f}°")
    print(f"  尺寸梯度 p99={r['size_gradient_p99']:.2f}  超限 {r['size_gradient_viol']} 对相邻单元")
    print(f"  ** 不合格 {r['bad']} = {100*r['bad_ratio']:.2f}%  -> {r['verdict']}")
    print("     按 PID: " + ", ".join(f"PID{k}: {v['bad']}/{v['elems']}" for k, v in r["by_pid"].items()))
    if r["clusters"]:
        print("     不合格区(前5):")
        for c in r["clusters"][:5]:
            print(f"       n={c['n']:4d} @({c['center'][0]:.0f},{c['center'][1]:.0f})"
                  f" 最差 {c['worst_angle']:.1f}° PID{c['pids']}")
    for p in r["problems"]:
        print(f"     ! {p}")


def render(path, r, out_png):
    try:
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt, matplotlib as mpl
        from matplotlib.collections import PolyCollection
    except Exception:
        return
    nodes, els = read_k(path)
    polys, cols = [], []
    sm = mpl.cm.ScalarMappable(norm=mpl.colors.Normalize(20, 90), cmap=mpl.colormaps["RdYlGn"])
    for pid, ns in els:
        pts = [nodes[n] for n in ns if n in nodes]
        if len(pts) < 3:
            continue
        a = elem_metrics(pts)[0]
        polys.append(np.array([(p[0], p[1]) for p in pts]))
        cols.append(a)
    fig, ax = plt.subplots(figsize=(16, 8))
    ax.add_collection(PolyCollection(polys, facecolors=sm.to_rgba(np.array(cols)),
                                     edgecolor="none", linewidth=0))
    ax.set_aspect("equal"); ax.autoscale_view(); ax.grid(alpha=.1, lw=.3)
    ax.set_title(f"{os.path.basename(path)}   {r['verdict']}   bad {100*r['bad_ratio']:.2f}%   tria {100*r['tria_ratio']:.1f}%",
                 fontsize=11)
    fig.colorbar(sm, ax=ax, label="min interior angle (deg)")
    plt.tight_layout(); plt.savefig(out_png, dpi=130); plt.close()
    print(f"  图: {out_png}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("k")
    ap.add_argument("--pids", default="")
    ap.add_argument("--cfg", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--png", default="")
    ap.add_argument("--ref", default="")
    a = ap.parse_args()
    cfg = dict(DEFAULT)
    if a.cfg and os.path.exists(a.cfg):
        cfg.update(json.load(open(a.cfg, encoding="utf-8")))
    pids = [int(x) for x in a.pids.split(",") if x.strip()] if a.pids else None
    r = evaluate(a.k, cfg, pids)
    if not r:
        print("没有可评估的单元"); return 2
    show(os.path.basename(a.k), r)
    if a.ref and os.path.exists(a.ref):
        rr = evaluate(a.ref, cfg, pids)
        if rr:
            show("REF " + os.path.basename(a.ref), rr)
    if a.png:
        render(a.k, r, a.png)
    if a.out:
        json.dump({"cfg": cfg, "result": r}, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"  报告: {a.out}")
    return {"PASS": 0, "WARN": 1, "FAIL": 2}[r["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
