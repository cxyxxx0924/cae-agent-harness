# -*- coding: utf-8 -*-
"""rebuild_anchor_band.py — 拉带↔布带过渡排重建（两条链带剖分 / two-chain strip）

问题（实测）
------------
拉带在 Z=-1 独立 automesh、布带在 Z=0 独立 automesh，两套 5mm 网格相位无关。
现有做法是"每个拉带第一排节点找最近布带节点，硬映射过去"。实测 v3：
  · 锚固节点 → 拉带本体的平面距离 p50 = 3.51mm（列对齐时应 ≈0）→ 整排横向错位
  · 过渡排 186 个单元里 53 个翘曲 >15°，最差 165.7°（蝴蝶结）
  · 拉带其余 2435 个单元翘曲恒 0°（平面）→ 问题只在这一排

做法
----
不再逐点映射，把过渡带当成"两条链之间的带"来剖：
  N 链 = 布带上的锚固节点（Z=0，沿布带走）
  M 链 = 拉带本体第二排节点（Z=-1，沿拉带走）
两边**按弧长比例同步推进**：谁下一段短谁先走一步。
  · 两侧各走一步 -> 四边形 (N_i, N_i+1, M_j+1, M_j)
  · 一侧连走两步 -> 三角形
每个单元两角在布带、两角在拉带，列严格对应，不会互相跨越。
三角形恒共面 -> 翘曲恒 0；四边形只有厚度向倾斜 -> 翘曲 = atan(ΔZ / 列距)。

链排序必须走**网格邻接**而不是贪心最近邻：锚固节点可能落在布带的两条边上
（侧面拉带就是），贪心会来回跳。

用法
----
  python rebuild_anchor_band.py --k in.k --out out.k            # 重建并写文件
  python rebuild_anchor_band.py --k in.k --out /tmp/x.k --dry   # 只看数字
"""
import argparse, math, collections, re, sys

BELT_PID, TETH_PID = 2, 5
_NUM = re.compile(r"-?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


# ---------------------------------------------------------------- 读 K
def read_k(path):
    """兼容逗号分隔 / LS-DYNA 定宽 8 列 / ANSA 8-16-16-16（含字段溢出）。"""
    nodes, els = {}, []
    sec = None
    with open(path, encoding="ascii", errors="ignore") as f:
        for line in f:
            if line.startswith("*"):
                sec = line.strip().upper()
                continue
            if not line.strip() or line.lstrip().startswith("$"):
                continue
            L = line.rstrip("\r\n")
            if sec == "*NODE":
                if "," in L:
                    t = [x.strip() for x in L.split(",") if x.strip()]
                    try:
                        nodes[int(t[0])] = (float(t[1]), float(t[2]), float(t[3]))
                    except (ValueError, IndexError):
                        pass
                    continue
                try:
                    nid = int(L[:8])
                except ValueError:
                    continue
                v = _NUM.findall(L[8:])
                if len(v) >= 3:
                    try:
                        nodes[nid] = (float(v[0]), float(v[1]), float(v[2]))
                    except ValueError:
                        pass
            elif sec == "*ELEMENT_SHELL":
                toks = ([x for x in L.replace(",", " ").split() if x] if "," in L
                        else [L[j:j + 8].strip() for j in range(0, min(len(L), 48), 8)])
                try:
                    ns = [int(x) for x in toks[2:6] if x and int(x) > 0]
                    els.append((int(toks[0]), int(toks[1]), ns))
                except (ValueError, IndexError):
                    pass
    return nodes, els


# ---------------------------------------------------------------- 质量
def quad_metrics(ns, P):
    v = [P[n] for n in ns]
    k = len(v)
    angs = []
    for i in range(k):
        a, b, c = v[i - 1], v[i], v[(i + 1) % k]
        e1 = [a[j] - b[j] for j in range(3)]
        e2 = [c[j] - b[j] for j in range(3)]
        n1 = math.sqrt(sum(x * x for x in e1)) or 1e-12
        n2 = math.sqrt(sum(x * x for x in e2)) or 1e-12
        cs = max(-1.0, min(1.0, sum(e1[j] * e2[j] for j in range(3)) / (n1 * n2)))
        angs.append(math.degrees(math.acos(cs)))
    amin = min(angs)
    if k == 3:
        return amin, 1.0, 0.0
    d1 = [v[2][j] - v[0][j] for j in range(3)]
    d2 = [v[3][j] - v[1][j] for j in range(3)]
    l1 = math.sqrt(sum(x * x for x in d1)) or 1e-12
    l2 = math.sqrt(sum(x * x for x in d2)) or 1e-12
    cr = [d1[1] * d2[2] - d1[2] * d2[1], d1[2] * d2[0] - d1[0] * d2[2],
          d1[0] * d2[1] - d1[1] * d2[0]]
    ac = math.sqrt(sum(x * x for x in cr))
    jac = ac / (l1 * l2) if l1 * l2 > 1e-18 else 0.0

    def nrm(a, b, c):
        u = [b[j] - a[j] for j in range(3)]
        w = [c[j] - a[j] for j in range(3)]
        n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
        m = math.sqrt(sum(x * x for x in n)) or 1e-12
        return [x / m for x in n]
    n1, n2 = nrm(v[0], v[1], v[2]), nrm(v[0], v[2], v[3])
    cs = max(-1.0, min(1.0, sum(n1[j] * n2[j] for j in range(3))))
    return amin, jac, math.degrees(math.acos(cs))


# ---------------------------------------------------------------- 链排序
def order_chain(ids, adj_in, nodes):
    """用网格邻接把一簇节点排成链。

    端点 = 在本集合内邻居数最少的节点（度数 1 = 真端点）。
    从端点出发，每步只走"在本集合内"的邻居，优先方向最顺的那个。
    """
    S = set(ids)
    if len(S) <= 2:
        return list(ids)
    deg = {n: sum(1 for m in adj_in[n] if m in S) for n in S}
    ends = [n for n in S if deg[n] == 1] or [min(S, key=lambda n: deg[n])]

    def walk(start):
        out, used, cur, prev = [start], {start}, start, None
        while True:
            cands = [m for m in adj_in[cur] if m in S and m not in used]
            if not cands:
                break
            if prev is None or len(cands) == 1:
                nxt = cands[0]
            else:   # 方向最顺: 继续往前，不往回拐
                base = [nodes[cur][j] - nodes[prev][j] for j in range(2)]
                nb = math.hypot(*base) or 1e-12
                best, bs = cands[0], -9
                for m in cands:
                    d = [nodes[m][j] - nodes[cur][j] for j in range(2)]
                    nd = math.hypot(*d) or 1e-12
                    s = (base[0] * d[0] + base[1] * d[1]) / (nb * nd)
                    if s > bs:
                        bs, best = s, m
                nxt = best
            out.append(nxt); used.add(nxt); prev, cur = cur, nxt
        return out

    a = walk(ends[0])
    if len(a) == len(S):
        return a
    b = walk(ends[-1])                      # 从另一端点走，取更长的
    return a if len(a) >= len(b) else b


def arc_s(chain, nodes):
    s = [0.0]
    for i in range(len(chain) - 1):
        s.append(s[-1] + math.dist(nodes[chain[i]], nodes[chain[i + 1]]))
    return s


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--tol", type=float, default=0.35, help="四边形判定的弧长占比差阈值")
    a = ap.parse_args()

    nodes, els = read_k(a.k)
    pid_of = {eid: pid for eid, pid, _ in els}

    belt_n, teth_n = set(), set()
    belt_adj = collections.defaultdict(set)
    teth_adj = collections.defaultdict(set)
    teth_elem = []
    for eid, pid, ns in els:
        if pid == BELT_PID:
            belt_n.update(ns)
            for i, x in enumerate(ns):
                for y in ns[i + 1:]:
                    belt_adj[x].add(y); belt_adj[y].add(x)
        elif pid == TETH_PID:
            teth_n.update(ns); teth_elem.append((eid, ns))
            for i, x in enumerate(ns):
                for y in ns[i + 1:]:
                    teth_adj[x].add(y); teth_adj[y].add(x)
    shared = belt_n & teth_n

    # 拉带连通分量
    seen, comps = set(), []
    for n in teth_n:
        if n in seen:
            continue
        st, comp = [n], set()
        seen.add(n)
        while st:
            u = st.pop(); comp.add(u)
            for v in teth_adj[u]:
                if v not in seen:
                    seen.add(v); st.append(v)
        comps.append(comp)
    comps.sort(key=lambda c: -sum(1 for n in c if n in shared))

    rebuild = [(eid, ns) for eid, ns in teth_elem if any(n in shared for n in ns)]
    rebuild_ids = {eid for eid, _ in rebuild}
    print(f"读入: 拉带 {len(teth_elem)} 单元 / {len(teth_n)} 节点, "
          f"锚固节点 {len(shared)}, 待重建过渡排 {len(rebuild)} 单元, {len(comps)} 块")

    new_els, rows = [], []
    for ci, comp in enumerate(comps):
        N = [n for n in comp if n in shared]
        if len(N) < 2:
            continue
        N = order_chain(N, belt_adj, nodes)          # 沿布带走
        Mset = {m for n in N for m in teth_adj[n] if m not in shared}
        if len(Mset) < 2:
            continue
        M = order_chain(Mset, teth_adj, nodes)       # 沿拉带走
        # 走向对齐: 让 M[0] 靠近 N[0]（否则四边形会拧成蝴蝶结）
        if (math.dist(nodes[M[0]], nodes[N[0]]) >
                math.dist(nodes[M[-1]], nodes[N[0]])):
            M = M[::-1]

        sn, sm = arc_s(N, nodes), arc_s(M, nodes)
        Ln, Lm = sn[-1] or 1e-9, sm[-1] or 1e-9
        b = []
        i = j = 0
        while i < len(N) - 1 or j < len(M) - 1:
            if i >= len(N) - 1:
                b.append([M[j], M[j + 1], N[i]]); j += 1; continue
            if j >= len(M) - 1:
                b.append([N[i], N[i + 1], M[j]]); i += 1; continue
            rn = (sn[i + 1] - sn[i]) / Ln
            rm = (sm[j + 1] - sm[j]) / Lm
            if abs(rn - rm) < a.tol:
                b.append([N[i], N[i + 1], M[j + 1], M[j]]); i += 1; j += 1
            elif rn < rm:
                b.append([N[i], N[i + 1], M[j]]); i += 1
            else:
                b.append([M[j], M[j + 1], N[i]]); j += 1
        new_els.extend(b)
        rows.append(dict(ci=ci, N=N, M=M, new=b, comp=comp))

    old_w = [quad_metrics(ns, nodes)[2] for _, ns in rebuild]
    new_w = [quad_metrics(ns, nodes)[2] for ns in new_els]
    old_a = [quad_metrics(ns, nodes)[0] for _, ns in rebuild]
    new_a = [quad_metrics(ns, nodes)[0] for ns in new_els]

    def rep(tag, m):
        s = sorted(m); n = len(s)
        q = lambda p: s[min(n - 1, int(p * (n - 1)))]
        print(f"  {tag}: n={n:3d}  p50={q(.5):6.2f}  p95={q(.95):7.2f}  max={s[-1]:7.2f}  "
              f">15°: {sum(1 for x in s if x > 15):3d} ({100.0*sum(1 for x in s if x > 15)/n:4.1f}%)")

    print("\n过渡排翘曲（度）:")
    rep("旧", old_w); rep("新", new_w)
    print("过渡排最小内角（度，越接近 90 越好）:")
    rep("旧", old_a); rep("新", new_a)

    print(f"\n分块（{len(rows)} 块）:  块  N链  M链  新单元  三角形")
    for r in rows:
        nt = sum(1 for ns in r["new"] if len(ns) == 3)
        print(f"   {r['ci']:>2} {len(r['N']):>4} {len(r['M']):>4} {len(r['new']):>6} {nt:>6}")

    if a.dry:
        print("\n[dry] 未写文件")
        return

    kept = [(eid, pid, ns) for eid, pid, ns in els if eid not in rebuild_ids]
    nid = max(e for e, _, _ in els) + 1
    for ns in new_els:
        kept.append((nid, TETH_PID, ns)); nid += 1
    kept.sort(key=lambda x: x[0])
    with open(a.out, "w", encoding="ascii") as f:
        f.write("*KEYWORD\n*TITLE\nanchor band rebuilt\n")
        f.write("*NODE\n$#   nid               x               y               z\n")
        for n, (x, y, z) in nodes.items():
            f.write(f"{n}, {x:.6f}, {y:.6f}, {z:.6f}\n")
        f.write("*ELEMENT_SHELL\n$#   eid     pid      n1      n2      n3      n4\n")
        for eid, pid, ns in kept:
            p = ns + [0] * (4 - len(ns))
            f.write(f"{eid}, {pid}, {p[0]}, {p[1]}, {p[2]}, {p[3]}\n")
        f.write("*END\n")
    print(f"\n-> {a.out}  单元 {len(els)-len(rebuild_ids)+len(new_els)} "
          f"(原 {len(els)}, 删 {len(rebuild_ids)}, 增 {len(new_els)})")


if __name__ == "__main__":
    main()
