#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chain_trace.py — 气帘分区「沿顺滑方向追链」工具
================================================
给定种子线，沿其几何顺滑方向（最小转向角、可指定偏好方向）自动追踪
属于同一边界环的连续线链。用于气腔/布带/拉带等「闭环边界轮廓」的
自动补全，避免逐根肉眼点名。

方法论（用户，2026-10-21）：
  1) 边界线在 IGES 中通常按绘制顺序连续编号（167→168→169→...）；
  2) 真正边界是「顺滑」的——相邻段转向角小、大致同向；
  3) 从种子线出发：两端都接其他线时，优先沿「邻居线号=seed+1」的方向
     （即编号顺序）进入；之后在容差内找下一根线，优先方向最顺滑且
     朝偏好方向（如 +Y 向上）的那根；直到撞到另一条已分类环线 /
     回到起点 / 无可续接 / 达步数上限。

用法示例：
  python chain_trace.py --geom out/geom_features.txt --classify out/classify_v12.json \
      --seed 167 --pref "0,1" --number-order --stoppts "834.9,497.4"
"""
import json, math, argparse, sys

def load_geom(path):
    feat = {}
    for ln in open(path, encoding="utf-8"):
        if not ln.startswith("LINE "):
            continue
        p = ln.split("|"); f = p[0].split()
        lid = int(f[1])
        sp = tuple(map(float, p[1].split()[:2]))
        ep = tuple(map(float, p[2].split()[:2]))
        feat[lid] = (sp, ep)
    return feat

def load_classify(path):
    if not path:
        return {}
    d = json.load(open(path, encoding="utf-8"))
    return {int(k): v for k, v in d.get("line_comp", {}).items()}

def d(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def neighbors(feat, pt, tol, exclude=None):
    """返回端点接近 pt(容差tol)的线号列表"""
    res = []
    for l, (s, e) in feat.items():
        if exclude and l in exclude:
            continue
        if d(s, pt) < tol or d(e, pt) < tol:
            res.append(l)
    return res

def other(lid, pt, feat):
    s, e = feat[lid]
    return e if d(s, pt) < d(e, pt) else s

def trace(feat, C, seed, entry_pt, prefs, tol, maxsteps, stoppts, number_order):
    """从 seed 的 entry_pt 端点进入，直接踏进相邻线并向其远端延伸。
    返回 (path, end_pt)。path 含 seed 及其后的相邻线。"""
    nbrs = neighbors(feat, entry_pt, tol, exclude={seed})
    path = [seed]; visited = {seed}; cur = None; prev_dir = (0.0, 0.0)
    if nbrs:
        nb = nbrs[0]
        path.append(nb); visited.add(nb)
        cur = other(nb, entry_pt, feat)
        prev_dir = (cur[0]-entry_pt[0], cur[1]-entry_pt[1])
    else:
        # 自由端：从 seed 另一端出发
        cur = other(seed, entry_pt, feat)
        prev_dir = (cur[0]-entry_pt[0], cur[1]-entry_pt[1])
    if any(d(cur, p) < tol for p in stoppts):
        return path, cur
    for _ in range(maxsteps):
        cands = []
        for l, (s, e) in feat.items():
            if l in visited:
                continue
            if d(s, cur) < tol or d(e, cur) < tol:
                nxt = other(l, cur, feat)
                v = (nxt[0]-cur[0], nxt[1]-cur[1])
                vl = math.hypot(*v)
                if vl < 1e-6:
                    continue
                vn = (v[0]/vl, v[1]/vl)
                pl = math.hypot(*prev_dir)
                align = 0.0 if pl < 1e-6 else (prev_dir[0]*vn[0]+prev_dir[1]*vn[1])/pl
                pref_score = max(pn[0]*vn[0]+pn[1]*vn[1] for pn in prefs)
                num_score = 0.0
                if number_order and path:
                    num_score = 1.0/(1.0+abs(l-(path[-1]+1)))
                score = align*0.6 + pref_score*0.2 + num_score*0.2
                cands.append((score, l, nxt))
        if not cands:
            break
        cands.sort(reverse=True)
        _, l, nxt = cands[0]
        path.append(l); visited.add(l)
        prev_dir = (nxt[0]-cur[0], nxt[1]-cur[1])
        cur = nxt
        if any(d(cur, p) < tol for p in stoppts):
            break
    return path, cur

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geom", required=True)
    ap.add_argument("--classify", default="")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--pref", default="0,1", help="偏好方向 x,y (多组 0,1;0,0.5)")
    ap.add_argument("--tol", type=float, default=2.0)
    ap.add_argument("--maxsteps", type=int, default=200)
    ap.add_argument("--stoppts", default="", help="x1,y1;x2,y2 到达即停")
    ap.add_argument("--number-order", action="store_true", help="编号顺序偏好")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    feat = load_geom(args.geom)
    C = load_classify(args.classify)
    if args.seed not in feat:
        print(f"seed L{args.seed} not found", file=sys.stderr); sys.exit(1)
    prefs = [tuple(map(float, s.split(","))) for s in args.pref.split(";")]
    stoppts = [tuple(map(float, s.split(","))) for s in args.stoppts.split(";")] if args.stoppts else []

    s, e = feat[args.seed]
    ends = [s, e]
    # 选出发端点：优先「邻居线号=seed+1」的方向（编号顺序）
    best_end, best_score = ends[0], -1e9
    for en in ends:
        nbrs = neighbors(feat, en, args.tol, exclude={args.seed})
        sc = -1e9
        for nb in nbrs:
            sc = max(sc, -abs(nb-(args.seed+1)))   # 越接近 seed+1 越好
        if sc > best_score:
            best_score, best_end = sc, en
    # 另一端点作为 backtrace 起点
    back_end = e if best_end is s else s

    fwd_path, fwd_end = trace(feat, C, args.seed, best_end, prefs, args.tol,
                              args.maxsteps, stoppts, args.number_order)
    bwd_path, bwd_end = trace(feat, C, args.seed, back_end, prefs, args.tol,
                              args.maxsteps, stoppts, args.number_order)

    if args.json:
        print(json.dumps({
            "forward": {"chain": fwd_path, "end": fwd_end,
                        "classes": {l: C.get(l, "未归档") for l in fwd_path}},
            "backward": {"chain": bwd_path, "end": bwd_end,
                         "classes": {l: C.get(l, "未归档") for l in bwd_path}},
        }, ensure_ascii=False, indent=2))
    else:
        for tag, path, end in [("FORWARD(编号+1方向)", fwd_path, fwd_end),
                               ("BACKWARD(另一方向)", bwd_path, bwd_end)]:
            print(f"\n===== {tag} =====")
            print(f"链 ({len(path)} 段): " + " -> ".join(f"L{l}" for l in path))
            print(f"终点: ({end[0]:.2f},{end[1]:.2f})")
            if stoppts:
                print("距停止点: " + ", ".join(f"{d(end,p):.2f}" for p in stoppts))
            for i, l in enumerate(path):
                ss, ee = feat[l]
                print(f"  [{i:2d}] L{l:4d} {C.get(l,'未归档'):8s} "
                      f"({ss[0]:7.2f},{ss[1]:7.2f})->({ee[0]:7.2f},{ee[1]:7.2f})")

if __name__ == "__main__":
    main()
