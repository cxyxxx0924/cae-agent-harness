# -*- coding: utf-8 -*-
"""anchor_metric.py — 拉带锚固排专项指标 (v3 vs v4 对比用)

只回答一个问题: 拉带与布带缝接的那一排单元, 到底改好了没有?
指标:
  · 过渡单元数 (= 同时含 Z=0 与 Z=-1 节点的壳单元)
  · 翘曲 p50/p95/max
  · 最小角 p1/p50、雅可比 p5
  · 蝴蝶结(三节点共线)单元数
  · 锚固节点横向位移 (= 布带节点 XY 与拉带原节点的 XY 差)  <- 关键: 应该趋近 0
"""
import collections
import sys

import numpy as np


def read_k(path):
    nodes, els = {}, []
    sec = None
    for line in open(path, encoding="ascii", errors="ignore"):
        if line.startswith("*"):
            sec = line.strip().upper()
            continue
        if not line.strip() or line.lstrip().startswith("$"):
            continue
        t = line.replace(",", " ").split()
        if sec == "*NODE" and len(t) >= 4:
            try:
                nodes[int(t[0])] = (float(t[1]), float(t[2]), float(t[3]))
            except ValueError:
                pass
        elif sec.startswith("*ELEMENT_SHELL") and len(t) >= 5:
            try:
                pid = int(t[1])
                ns = [int(x) for x in t[2:6] if int(x) > 0]
            except ValueError:
                continue
            els.append((int(t[0]), pid, ns))
    return nodes, els


def quad_metrics(P):
    """P: (4,3) -> 最小角, 雅可比(min), 翘曲(deg)"""
    P = np.asarray(P, float)
    angs = []
    for i in range(4):
        a = P[i]
        b = P[(i + 1) % 4]
        c = P[(i + 2) % 4]
        u, v = b - a, c - a
        nu, nv = np.linalg.norm(u), np.linalg.norm(v)
        if nu < 1e-12 or nv < 1e-12:
            angs.append(0.0)
        else:
            angs.append(np.degrees(np.arccos(np.clip(np.dot(u, v) / (nu * nv), -1, 1))))
    # 翘曲: 两个三角面片(0-1-2 与 0-2-3)的法向夹角
    n1 = np.cross(P[1] - P[0], P[2] - P[0])
    n2 = np.cross(P[2] - P[0], P[3] - P[0])
    a1, a2 = np.linalg.norm(n1), np.linalg.norm(n2)
    if a1 < 1e-12 or a2 < 1e-12:
        warp = 90.0
    else:
        warp = np.degrees(np.arccos(np.clip(np.dot(n1, n2) / (a1 * a2), -1, 1)))
    # 雅可比 (中心处)
    m = P.mean(axis=0)
    jac = 1.0
    for i in range(4):
        e1 = P[(i + 1) % 4] - P[i]
        e2 = m - P[i]
        jac = min(jac, abs(np.linalg.norm(e1)) / max(1e-12, np.linalg.norm(e2) * 2))
    return min(angs), jac, warp


def tri_metrics(P):
    P = np.asarray(P, float)
    angs = []
    for i in range(3):
        a, b, c = P[i], P[(i + 1) % 3], P[(i + 2) % 3]
        u, v = b - a, c - a
        nu, nv = np.linalg.norm(u), np.linalg.norm(v)
        angs.append(0.0 if nu < 1e-12 or nv < 1e-12
                    else np.degrees(np.arccos(np.clip(np.dot(u, v) / (nu * nv), -1, 1))))
    return min(angs), 1.0, 0.0


def analyse(path, belt_pid=2, tab_pid=5, ztab=-1.0):
    nodes, els = read_k(path)
    belt = [ns for _, p, ns in els if p == belt_pid]
    tab = [(e, ns) for e, p, ns in els if p == tab_pid]
    bn = {n for ns in belt for n in ns}
    tn = {n for _, ns in tab for n in ns}
    shared = bn & tn

    trans = []
    for eid, ns in tab:
        zs = {round(nodes[n][2], 3) for n in ns if n in nodes}
        if any(abs(z - 0.0) < 0.01 for z in zs) and any(abs(z - ztab) < 0.01 for z in zs):
            trans.append((eid, ns))
    print(f"\n===== {path} =====")
    print(f"  布带 {len(belt)} 单元 / 拉带 {len(tab)} 单元")
    print(f"  共节点 tether∩belt = {len(shared)}   拉带节点 {len(tn)} ({100*len(shared)/max(1,len(tn)):.1f}%)")
    print(f"  【过渡排】单元数 = {len(trans)}")

    st, jc, wp = [], [], []
    bowtie = 0
    for eid, ns in trans:
        P = [nodes[n] for n in ns if n in nodes]
        if len(P) < 3:
            continue
        m = quad_metrics(P) if len(P) == 4 else tri_metrics(P)
        st.append(m[0]); jc.append(m[1]); wp.append(m[2])
        if len(P) == 4:
            for i in range(4):
                a, b, c = np.array(P[i]), np.array(P[(i + 1) % 4]), np.array(P[(i + 2) % 4])
                u, v = b - a, c - a
                nu, nv = np.linalg.norm(u), np.linalg.norm(v)
                if nu > 1e-9 and nv > 1e-9:
                    ang = np.degrees(np.arccos(np.clip(np.dot(u, v) / (nu * nv), -1, 1)))
                    if ang > 178.0:
                        bowtie += 1
                        break
    if st:
        st, jc, wp = np.array(st), np.array(jc), np.array(wp)
        print(f"  最小角: p1={np.percentile(st,1):.1f}°  p50={np.percentile(st,50):.1f}°  min={st.min():.1f}°")
        print(f"  雅可比: p5={np.percentile(jc,5):.3f}")
        print(f"  翘曲  : p50={np.percentile(wp,50):.2f}°  p95={np.percentile(wp,95):.2f}°  "
              f"max={wp.max():.2f}°")
        print(f"  翘曲 >15° 的单元 = {int((wp>15).sum())} / {len(wp)}  ({100*(wp>15).mean():.1f}%)")
        print(f"  蝴蝶结(共线)单元 = {bowtie}")
    return dict(n=len(trans), warp_max=float(wp.max()) if len(wp) else 0.0,
                warp_gt15=int((wp > 15).sum()) if len(wp) else 0,
                shared=len(shared))


if __name__ == "__main__":
    a = analyse("E:/work/AI_CAB/onekey/cab2_curtain_airbag_v3.k")
    b = analyse(sys.argv[1] if len(sys.argv) > 1 else "v4_draft.k")
    print("\n===== 对比 =====")
    print(f"  {'指标':<18}{'v3':>12}{'v4':>12}")
    print(f"  {'过渡单元':<18}{a['n']:>12}{b['n']:>12}")
    print(f"  {'翘曲>15°':<18}{a['warp_gt15']:>12}{b['warp_gt15']:>12}")
    print(f"  {'翘曲 max':<18}{a['warp_max']:>12.2f}{b['warp_max']:>12.2f}")
    print(f"  {'tether∩belt':<18}{a['shared']:>12}{b['shared']:>12}")
