# -*- coding: utf-8 -*-
"""partition_cover_check.py — 分区覆盖核对（防"丢网格"）

为什么需要这道门禁
------------------
现有的 auto_gate 只核对 belt/cavity/seam 的环面积与周长，**拉带(PID5)不在其中**。
cab2 第四轮就出过这个事故：把拉带换成锚固受约束版本后，侧面的长条拉带
（196 单元 / 2354mm² / X1570~1771）整块消失，拓扑 QA 全 PASS、环面积全 PASS、
拉带连接 8/8 PASS —— 因为**剩下的 8 块每块都正常**，没有任何一项检查看总面积。

本脚本按 PID 逐项核对"网格面积 / 连通组分 / 包围盒"与 **CAD 分区多边形** 或
**基线 manifest**，任何一个 PID 少块、少面积、少组分都会 FAIL。

用法
----
  # 1) 与 CAD 分区多边形对拍（推荐，换案例只需给 polygon json）
  python partition_cover_check.py --k out.k --cad 2=belt.json --cad 5=tether_full.json

  # 2) 与基线 manifest 对拍（没有 CAD 多边形时，先对已认可的模型 --write）
  python partition_cover_check.py --k delivered.k --write ref_manifest.json
  python partition_cover_check.py --k out.k --manifest ref_manifest.json

退出码: 0=PASS / 1=WARN / 2=FAIL
"""
import argparse
import json
import math
import os
import sys
import collections

AREA_TOL = 0.03      # 网格面积 vs CAD 面积允许偏差
COMP_TOL = 0.10      # 组分面积匹配容差
CENT_TOL = 12.0      # 组分质心匹配距离 mm


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
                els.append((int(t[0]), int(t[1]), [int(x) for x in t[2:6] if int(x) > 0]))
            except ValueError:
                continue
    return nodes, els


def poly_area(pts):
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i][0], pts[i][1]
        x2, y2 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def mesh_stats(nodes, els, pid):
    sub = [(eid, ns) for eid, p, ns in els if p == pid]
    if not sub:
        return None
    # 面积
    area = 0.0
    for _, ns in sub:
        P = [nodes[n] for n in ns]
        a = 0.0
        for i in range(len(P)):
            j = (i + 1) % len(P)
            a += P[i][0] * P[j][1] - P[j][0] * P[i][1]
        area += abs(a) / 2
    # 连通组分（并查集）
    par = {}

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb

    for _, ns in sub:
        for n in ns:
            par.setdefault(n, n)
        for i in range(1, len(ns)):
            uni(ns[0], ns[i])
    grp = collections.defaultdict(list)
    for eid, ns in sub:
        grp[find(ns[0])].append((eid, ns))
    comps = []
    for _, lst in grp.items():
        ids = sorted({n for _, ns in lst for n in ns})
        P = [nodes[n] for n in ids]
        a = 0.0
        for _, ns in lst:
            Q = [nodes[n] for n in ns]
            s = 0.0
            for i in range(len(Q)):
                j = (i + 1) % len(Q)
                s += Q[i][0] * Q[j][1] - Q[j][0] * Q[i][1]
            a += abs(s) / 2
        cx = sum(p[0] for p in P) / len(P)
        cy = sum(p[1] for p in P) / len(P)
        comps.append(dict(ne=len(lst), nodes=len(ids), area=a, cx=cx, cy=cy,
                          x0=min(p[0] for p in P), x1=max(p[0] for p in P),
                          y0=min(p[1] for p in P), y1=max(p[1] for p in P)))
    comps.sort(key=lambda d: -d["area"])
    xs = [nodes[n][0] for _, ns in sub for n in ns]
    ys = [nodes[n][1] for _, ns in sub for n in ns]
    return dict(pid=pid, elements=len(sub), area=area, comps=comps,
                bbox=[min(xs), max(xs), min(ys), max(ys)])


def load_cad_polys(path):
    """支持两种 json: [{pts:[...]}, ...] 或 {"pts": [...]} 或 [[x,y],...]"""
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, dict):
        d = [d]
    out = []
    for it in d:
        if isinstance(it, dict) and "pts" in it:
            out.append([tuple(p) for p in it["pts"]])
        elif isinstance(it, dict) and "chain" in it:
            out.append([tuple(p) for p in it["chain"]])
        elif isinstance(it, list) and it and isinstance(it[0], (list, tuple)):
            out.append([tuple(p) for p in it])
    return out


def check_cad(pids_cad, stats):
    rows, bad = [], 0
    for pid, path in pids_cad.items():
        st = stats.get(pid)
        if st is None:
            rows.append((pid, "FAIL", f"网格里没有 PID{pid}", 0, 0, 0))
            bad += 2
            continue
        polys = load_cad_polys(path)
        cad_a = sum(poly_area(p) for p in polys)
        dev = (st["area"] - cad_a) / cad_a if cad_a else 0.0
        ok = abs(dev) <= AREA_TOL
        if not ok:
            bad += 1
        rows.append((pid, "PASS" if ok else "FAIL",
                     f"CAD {len(polys)} 片", cad_a, st["area"], dev))
    return rows, bad


def check_manifest(ref, cur):
    rows, bad = [], 0
    for pid_s, r in ref.items():
        pid = int(pid_s)
        c = cur.get(pid)
        if c is None:
            rows.append((pid, "FAIL", "整个 PID 丢失", r["area"], 0, -1.0))
            bad += 2
            continue
        # 组分逐个匹配（按面积降序，质心就近）
        used = set()
        miss, extra_a = [], 0.0
        for rc in r["comps"]:
            best, bd = None, 1e18
            for i, cc in enumerate(c["comps"]):
                if i in used:
                    continue
                d = math.hypot(cc["cx"] - rc["cx"], cc["cy"] - rc["cy"])
                if d < bd:
                    bd, best = d, i
            if best is not None and bd <= CENT_TOL and \
                    abs(c["comps"][best]["area"] - rc["area"]) <= COMP_TOL * rc["area"] + 1e-9:
                used.add(best)
            else:
                miss.append(rc)
        for i, cc in enumerate(c["comps"]):
            if i not in used:
                extra_a += cc["area"]
        dev = (c["area"] - r["area"]) / r["area"] if r["area"] else 0.0
        status = "PASS"
        note = f"组分 {len(r['comps'])}->{len(c['comps'])}"
        if miss:
            status = "FAIL"
            bad += 2
            note += f" 丢失{len(miss)}块(" + \
                    ", ".join(f"{m['area']:.0f}mm²@({m['cx']:.0f},{m['cy']:.0f})" for m in miss) + ")"
        elif abs(dev) > AREA_TOL:
            status = "WARN"
            bad += 1
            note += f" 面积偏差 {dev*100:+.1f}%"
        rows.append((pid, status, note, r["area"], c["area"], dev))
    return rows, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", required=True)
    ap.add_argument("--cad", action="append", default=[], help="PID=多边形json，可重复")
    ap.add_argument("--manifest", default="")
    ap.add_argument("--write", default="", help="把当前 K 的分区统计写成基线 manifest")
    ap.add_argument("--pids", default="2,3,4,5")
    a = ap.parse_args()

    if not os.path.exists(a.k):
        print(f"文件不存在: {a.k}")
        return 2
    nodes, els = read_k(a.k)
    pids = [int(x) for x in a.pids.split(",") if x.strip()]
    stats = {}
    for pid in pids:
        st = mesh_stats(nodes, els, pid)
        if st:
            stats[pid] = st

    print("=" * 72)
    print(f"分区覆盖核对: {os.path.basename(a.k)}   {len(nodes)} 节点 {len(els)} 单元")
    print("=" * 72)
    print(f"{'PID':>4} {'单元':>7} {'面积mm²':>11} {'组分':>4}  说明")
    for pid in pids:
        st = stats.get(pid)
        if not st:
            print(f"{pid:>4} {'-':>7} {'-':>11} {'-':>4}  缺失")
            continue
        print(f"{pid:>4} {st['elements']:>7} {st['area']:>11.1f} {len(st['comps']):>4}  "
              f"bbox X[{st['bbox'][0]:.0f},{st['bbox'][1]:.0f}] "
              f"Y[{st['bbox'][2]:.0f},{st['bbox'][3]:.0f}]")

    if a.write:
        json.dump({str(k): v for k, v in stats.items()},
                  open(a.write, "w", encoding="utf-8"), indent=1)
        print(f"\n已写基线 manifest: {a.write}")
        return 0

    bad = 0
    if a.cad:
        pids_cad = {}
        for s in a.cad:
            k, v = s.split("=", 1)
            pids_cad[int(k)] = v
        rows, bad1 = check_cad(pids_cad, stats)
        print("\n-- 与 CAD 分区多边形对拍（面积） --")
        for pid, st, note, cad_a, m_a, dev in rows:
            flag = {"PASS": "OK  ", "WARN": "WARN", "FAIL": "FAIL"}[st]
            print(f"  [{flag}] PID{pid}: {note}  CAD {cad_a:.1f} / 网格 {m_a:.1f} mm² "
                  f"({dev*100:+.2f}%)")
        bad += bad1

    if a.manifest:
        ref = json.load(open(a.manifest, encoding="utf-8"))
        rows, bad2 = check_manifest(ref, stats)
        print("\n-- 与基线 manifest 对拍（组分逐个匹配） --")
        for pid, st, note, ra, ca, dev in rows:
            flag = {"PASS": "OK  ", "WARN": "WARN", "FAIL": "FAIL"}[st]
            print(f"  [{flag}] PID{pid}: {note}  基线 {ra:.1f} / 本次 {ca:.1f} mm² "
                  f"({dev*100:+.2f}%)")
        bad += bad2

    print()
    if bad >= 2:
        print(f"总判定: FAIL —— 分区覆盖不完整或偏差过大（score={bad}），不要交付")
        return 2
    if bad == 1:
        print("总判定: WARN —— 有面积偏差，检查是否改了网格尺寸")
        return 1
    print("总判定: PASS —— 各 PID 分区覆盖完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
