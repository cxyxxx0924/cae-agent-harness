#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tether_conn_check.py — 拉带↔布带连接质量自检
============================================
用户 2026-10-22 沉淀需求: "拉带连接检查"。

检查目标 (基于 5P-BAG_004 参考模型实证 + NEW_CAB 两轮返工, P21/P22/P23/P24/P29/P30):
  1) 每个拉带连通组分都必须与【单层布带 PID2】共节点 (至少 1 个, 最好成一条边)。
     参考模型: 拉带与气腔双层共节点 = 0, 拉带只接布带。
  2) 拉带【绝不】应与气腔 PID3 / 缝线 PID4 共节点 (误连 = 错乱)。
  3) 连接必须是【一条边啮合】, 不是整面重叠:
     早期把 3mm 内所有拉带节点无差别并到布带 -> 重叠区全捏合, 用户 2026-10-20 明确否决
     ("与部件层整个区域全部网格啮合, 这肯定有问题, 你只要找一条平行边")。
     判据: 共节点占该组分周长节点比例应 < 50% (否则判 FULL_OVERLAP FAIL)。
  4) 凸台连接边 = 顶帽水平边 (该组分靠布带节点中最高 Z 附近 EDGE_BAND 内, 平行布带长度方向);
     长条连接边 = 末端竖边 (最右/最左端 END_BAND 内, 垂直布带长度方向)。
     (soft-warn: 若实际带位置不符期望 band, 报警但不硬 FAIL —— 因为几何千变万化)
  5) 捏合后【无退化单元】(单元内 <3 独立节点) 与【无零厚度重合伪单元】(节点集与布带完全相同)。
     退化是 1-to-1 贪心漏做或跨文件 id 错位(P29 飞丝)的典型症状。

输入: 最终 K 文件 (含 PID2 布带 / PID3 气腔 / PID4 缝线 / PID5 拉带)。
      --map xy (默认): 图纸x=模型X, 图纸y=模型Z (NEW_CAB/cab1 都用此映射)
      --belt-pid / --tether-pid 可改 (默认 2 / 5)。
可选: --rings ring_spec.json 提供每个拉带组分的 type(boss/strap) 以启用 band 软校验。
      --render png 出连接特写图 (belt灰/strap橙/共节点红)。
退出码: 0 = 全部通过; 1 = 存在 FAIL。
"""
import argparse, json, math, re, sys, collections


def parse_k(path, draw_map):
    nodes = {}; elems = collections.defaultdict(list)
    sec = None
    for raw in open(path, encoding="utf-8", errors="replace"):
        s = raw.strip()
        if s.startswith("*"):
            sec = s.upper().split()[0]; continue
        if not s or s.startswith("$"):
            continue
        f = [x.strip() for x in s.split(",")]
        if sec == "*NODE" and len(f) >= 4:
            try:
                gid = int(float(f[0])); x = float(f[1]); y = float(f[2]); z = float(f[3])
            except ValueError:
                continue
            dx = x; dy = (z if draw_map == "xy" else y)
            nodes[gid] = (dx, dy)
        elif sec in ("*ELEMENT_SHELL", "*ELEMENT_SHELL_THICKNESS") and len(f) >= 5:
            try:
                pid = int(float(f[1])); ns = [int(float(x)) for x in f[2:6] if x.strip()]
            except ValueError:
                continue
            if len(ns) >= 3:
                elems[pid].append(ns)
    return nodes, elems


def connected_components(elems_list):
    """把单元集按共享节点聚类, 返回 list[ list[elem_index] ]"""
    node_elems = collections.defaultdict(list)
    for i, ns in enumerate(elems_list):
        for n in ns:
            node_elems[n].append(i)
    seen = set(); comps = []
    for i in range(len(elems_list)):
        if i in seen:
            continue
        stack = [i]; seen.add(i); members = []
        while stack:
            cur = stack.pop(); members.append(cur)
            for n in elems_list[cur]:
                for ej in node_elems[n]:
                    if ej not in seen:
                        seen.add(ej); stack.append(ej)
        comps.append(members)
    return comps


def perimeter_nodes(elems_list, members):
    ec = collections.Counter()
    for ei in members:
        u = list(dict.fromkeys(elems_list[ei]))
        for i in range(len(u)):
            a, b = u[i], u[(i + 1) % len(u)]
            ec[(min(a, b), max(a, b))] += 1
    pn = set()
    for (a, b), c in ec.items():
        if c == 1:
            pn.add(a); pn.add(b)
    return pn


def best_fit_line_dev(points):
    """返回点集到其主成分拟合直线的最大垂直偏差 (判断"是否一条线")"""
    if len(points) < 2:
        return 0.0
    n = len(points)
    cx = sum(p[0] for p in points) / n; cy = sum(p[1] for p in points) / n
    sxx = sum((p[0] - cx) ** 2 for p in points)
    syy = sum((p[1] - cy) ** 2 for p in points)
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in points)
    # 主方向
    if sxx + syy < 1e-9:
        return 0.0
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)
    dx, dy = math.cos(theta), math.sin(theta)
    dev = 0.0
    for p in points:
        d = abs((p[0] - cx) * (-dy) + (p[1] - cy) * dx)
        dev = max(dev, d)
    return dev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True, help="最终 K 文件")
    ap.add_argument("--map", default="xy", choices=["xy", "xz"])
    ap.add_argument("--belt-pid", type=int, default=2)
    ap.add_argument("--cav-pid", type=int, default=3)
    ap.add_argument("--seam-pid", type=int, default=4)
    ap.add_argument("--tether-pid", type=int, default=5)
    ap.add_argument("--edge-band", type=float, default=8.0, help="凸台顶帽连接带 mm")
    ap.add_argument("--end-band", type=float, default=3.0, help="长条末端连接带 mm")
    ap.add_argument("--rings", default=None, help="可选 ring_spec.json (含 type 以启用 band 软校验)")
    ap.add_argument("--render", default=None, help="可选 连接特写 PNG")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    nodes, elems = parse_k(a.mesh, a.map)
    tlist = elems.get(a.tether_pid, [])
    beltn = set(n for ns in elems.get(a.belt_pid, []) for n in ns)
    cavn = set(n for ns in elems.get(a.cav_pid, []) for n in ns)
    seamn = set(n for ns in elems.get(a.seam_pid, []) for n in ns)
    print(f"节点 {len(nodes)} | 拉带(PID{a.tether_pid}) {len(tlist)} 单元 | "
          f"布带 {len(beltn)} / 气腔 {len(cavn)} / 缝线 {len(seamn)} 节点")

    comps = connected_components(tlist)
    print(f"拉带连通组分: {len(comps)}")

    # ring type 映射 (按组分顺序难以对应, 这里仅当 rings 提供 tether 组分顺序时启用)
    rtypes = []
    if a.rings:
        try:
            spec = json.load(open(a.rings, encoding="utf-8"))
            rtypes = [r.get("type", "tether") for r in spec.get("rings", [])]
        except Exception:
            rtypes = []

    ring_type_of = {}
    # 若 rings 里 type 标注为 tether_boss/tether_strap, 尝试按质心 X 匹配 strap; 否则全部 boss
    strap_xmin, strap_xmax = 1e18, -1e18
    for r in (json.load(open(a.rings, encoding="utf-8")).get("rings", []) if a.rings else []):
        if r.get("type") == "tether_strap":
            # 用 iges_lines 反查不可行 (strap 常是构造件), 此处仅记录存在 strap 类型
            pass

    results = []
    total_shared_belt = 0
    total_shared_cav = 0
    total_shared_seam = 0
    n_unconnected = 0
    n_degen = 0
    n_dup = 0
    seen_sets = set()
    shared_node_all = set()

    for cid, members in enumerate(comps):
        comp_nodes = set()
        for ei in members:
            comp_nodes.update(tlist[ei])
        pn = perimeter_nodes(tlist, members)
        shared_belt = [n for n in comp_nodes if n in beltn]
        shared_cav = [n for n in comp_nodes if n in cavn]
        shared_seam = [n for n in comp_nodes if n in seamn]
        total_shared_belt += len(shared_belt)
        total_shared_cav += len(shared_cav)
        total_shared_seam += len(shared_seam)
        shared_node_all.update(shared_belt)
        # 周长占比
        perim_frac = (len(shared_belt) / len(pn)) if pn else 0.0
        # 退化 / 重合伪单元
        degen = sum(1 for ei in members if len(set(tlist[ei])) < 3)
        n_degen += degen
        n_dup_local = 0
        for ei in members:
            key = tuple(sorted(set(tlist[ei])))
            if key in seen_sets:
                n_dup_local += 1
            else:
                seen_sets.add(key)
        n_dup += n_dup_local
        # band 位置 (soft)
        band_note = ""
        if shared_belt:
            zs = [nodes[n][1] for n in shared_belt]
            xs = [nodes[n][0] for n in shared_belt]
            ztop = max(nodes[n][1] for n in comp_nodes if n in pn)
            xend = max(nodes[n][0] for n in comp_nodes if n in pn)
            if (ztop - max(zs)) <= a.edge_band:
                band_note = "顶帽边(高Z带)"
            elif (xend - min(xs)) <= a.end_band or (max(xs) - xend) <= a.end_band:
                band_note = "末端竖边(端X带)"
            else:
                band_note = f"带位置不明确(z距顶{ztop-max(zs):.1f} x距端{xend-min(xs):.1f})"
        # 单条边判定: 共节点是否近似共线 (一条线)
        line_dev = best_fit_line_dev([nodes[n] for n in shared_belt]) if len(shared_belt) >= 2 else 0.0
        # 判定
        fails = []
        if not shared_belt:
            fails.append("未连接布带(浮层)")
            n_unconnected += 1
        if shared_cav:
            fails.append(f"误连气腔 {len(shared_cav)} 节点")
        if shared_seam:
            fails.append(f"误连缝线 {len(shared_seam)} 节点")
        if perim_frac > 0.5:
            fails.append(f"整面重叠(共节点占周长 {perim_frac*100:.0f}%>50%)")
        if degen:
            fails.append(f"退化单元 {degen}")
        if n_dup_local:
            fails.append(f"重合伪单元 {n_dup_local}")
        results.append({
            "cid": cid, "elems": len(members), "nodes": len(comp_nodes),
            "shared_belt": len(shared_belt), "shared_cav": len(shared_cav),
            "shared_seam": len(shared_seam), "perim_frac": perim_frac,
            "line_dev": line_dev, "band": band_note, "degen": degen,
            "dup": n_dup_local, "fails": fails,
        })

    # 报告
    out = []
    out.append("=" * 84)
    out.append(f"拉带↔布带连接自检  (mesh={a.mesh})")
    out.append("=" * 84)
    out.append(f"  {'组分':>4} {'单元':>5} {'节点':>5} {'接布带':>6} {'接气腔':>6} {'接缝线':>6} "
               f"{'周长占比':>8} {'线偏差':>7}  连接带        结论")
    out.append("  " + "-" * 80)
    npass = 0
    for r in results:
        verdict = "PASS" if not r["fails"] else "FAIL"
        if not r["fails"]:
            npass += 1
        extra = ""
        if r["fails"]:
            extra = "  | " + "; ".join(r["fails"])
        elif r["band"]:
            extra = "  | " + r["band"]
        out.append(f"  {r['cid']:>4} {r['elems']:>5} {r['nodes']:>5} {r['shared_belt']:>6} "
                   f"{r['shared_cav']:>6} {r['shared_seam']:>6} {r['perim_frac']*100:>6.0f}% "
                   f"{r['line_dev']:>6.1f}  {r['band'] or '-':<12} {verdict}{extra}")
    out.append("  " + "-" * 80)
    out.append(f"  组分 {len(results)} | PASS {npass} | FAIL {len(results)-npass} | "
               f"未连接 {n_unconnected}")
    out.append(f"  拉带↔布带 共节点合计: {total_shared_belt}")
    out.append(f"  拉带↔气腔 误连接点: {total_shared_cav}  (期望 0)")
    out.append(f"  拉带↔缝线 误连接点: {total_shared_seam}  (期望 0)")
    out.append(f"  退化单元合计: {n_degen} (期望 0) | 重合伪单元: {n_dup} (期望 0)")
    all_ok = (len(results) - npass == 0) and total_shared_cav == 0 and \
             total_shared_seam == 0 and n_degen == 0 and n_dup == 0 and n_unconnected == 0
    out.append(f"  总判定: {'全部 PASS ✅' if all_ok else '存在 FAIL ❌'}")
    report = "\n".join(out)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(report + "\n")
    print(report)

    if a.render:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.collections import PolyCollection
            fig, ax = plt.subplots(figsize=(16, 6.5))
            # belt
            bp = [[(nodes[g][0], nodes[g][1]) for g in ns] for ns in elems.get(a.belt_pid, [])]
            ax.add_collection(PolyCollection(bp, facecolors="none", edgecolors="#888888", lw=0.3))
            tp = [[(nodes[g][0], nodes[g][1]) for g in ns] for ns in tlist]
            ax.add_collection(PolyCollection(tp, facecolors="none", edgecolors="#ff7f0e", lw=0.4))
            sx = [nodes[n][0] for n in shared_node_all]; sz = [nodes[n][1] for n in shared_node_all]
            ax.scatter(sx, sz, s=10, c="red", zorder=5, label="拉带↔布带共节点")
            ax.autoscale(); ax.set_aspect("equal"); ax.grid(True, lw=0.3)
            ax.set_title("tether-belt connection (red=shared nodes)")
            ax.legend(fontsize=8)
            fig.savefig(a.render, dpi=110, bbox_inches="tight"); plt.close(fig)
            print(f"渲染: {a.render}")
        except Exception as e:
            print(f"渲染跳过: {e}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
