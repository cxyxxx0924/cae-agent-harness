# -*- coding: utf-8 -*-
"""tab_anchor_stat.py — 逐凸台统计锚固过渡排几何（宽度/错位/三角形/退化）"""
import json, sys
import numpy as np
sys.path.insert(0, ".")
from render_anchor_side import read_k


def blocks(path, anchors="anchors_v4.json"):
    nodes, els = read_k(path)
    out = []
    for c in json.load(open(anchors, encoding="utf-8")):
        ch = np.array(c["chain"])
        d = ch[-1] - ch[0]
        d = d / (np.linalg.norm(d) + 1e-12)
        n = np.array([-d[1], d[0]])
        rows = []
        for eid, pid, ns in els:
            if pid != 5 or len(ns) < 3:
                continue
            P = np.array([nodes[x] for x in ns])
            zs = P[:, 2]
            if not ((np.abs(zs) < 1e-6).any() and (np.abs(zs + 1.0) < 1e-6).any()):
                continue
            # 只取落在该凸台链附近（沿链方向 ±0.8*span、法向 ±40mm）的单元
            rel = P[:, :2] - ch.mean(axis=0)
            s = rel @ d
            t = rel @ n
            L = c["span"]
            if np.abs(s).max() > L * 0.85 or np.abs(t).max() > 45.0:
                continue
            top = P[np.abs(P[:, 2]) < 1e-6]
            bot = P[np.abs(P[:, 2] + 1.0) < 1e-6]
            if len(top) < 2 or len(bot) < 2:
                continue
            st, sb = (top[:, :2] @ d), (bot[:, :2] @ d)
            rows.append((len(ns), sb.max() - sb.min(), st.max() - st.min(),
                         (sb.mean() - st.mean()), t.mean()))
        if not rows:
            continue
        A = np.array(rows)
        out.append(dict(blk=c["blk"], n=len(rows),
                        tri=int((A[:, 0] == 3).sum()),
                        wb_min=A[:, 1].min(), wb_max=A[:, 1].max(),
                        wt_min=A[:, 2].min(), wt_max=A[:, 2].max(),
                        off_min=A[:, 3].min(), off_max=A[:, 3].max(),
                        off_std=A[:, 3].std()))
    return out


def main():
    for tag, f in [("v3", sys.argv[1]), ("v4", sys.argv[2])]:
        print(f"\n===== {tag} =====")
        print(f"{'blk':>3} {'过渡':>4} {'三角':>4} {'下边宽':>13} {'上边宽':>13} "
              f"{'错位':>16} {'σ':>5}")
        T = []
        for b in blocks(f):
            T.append(b)
            print(f"{b['blk']:>3} {b['n']:>4} {b['tri']:>4} "
                  f"{b['wb_min']:>6.2f}~{b['wb_max']:<6.2f} "
                  f"{b['wt_min']:>6.2f}~{b['wt_max']:<6.2f} "
                  f"{b['off_min']:>+7.2f}~{b['off_max']:<+7.2f} {b['off_std']:>5.2f}")
        n = sum(t["n"] for t in T)
        tri = sum(t["tri"] for t in T)
        deg = sum(1 for t in T for _ in range(0))
        wide = [t["wb_max"] for t in T] + [t["wt_max"] for t in T]
        stds = [t["off_std"] for t in T]
        print(f"合计 过渡 {n}  三角 {tri}  最宽 {max(wide):.2f}mm  "
              f"σ 均值 {np.mean(stds):.2f}")


if __name__ == "__main__":
    main()
