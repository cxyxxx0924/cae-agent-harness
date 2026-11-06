#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kio.py — 零依赖 LS-DYNA K 解析器 (auto_gate 共用)

自动识别两种格式:
  * 自由/逗号格式  (我方 assemble 产出):  1, 2, n1, n2, n3, n4
  * 经典 80 列定宽  (ANSA/参考模型):      eid[0:8] pid[8:16] n1[16:24] ...
  * NODE 既可能是逗号也可能是空白分隔, 两者都吃。

只解析 *NODE / *ELEMENT_SHELL / *PART / *SECTION_SHELL / *MAT_*, 其余忽略。
"""
import re
from collections import defaultdict


def _num(s):
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_kfile(path):
    """返回 dict: nodes{nid:(x,y,z)}, elems{pid:[(n1..n4)]},
       parts{pid:{sec,mid}}, mats{mid:type}, title"""
    nodes = {}
    elems = defaultdict(list)
    parts = {}
    mats = {}
    title = ""
    state = "idle"
    pending_part = None  # (pid) awaiting its data line
    with open(path, encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\n")
            s = line.strip()
            U = s.upper()
            if s.startswith("*TITLE"):
                state = "title"; continue
            if s.startswith("*NODE"):
                state = "node"; continue
            if s.startswith("*ELEMENT_SHELL"):
                state = "elem"; continue
            if s.startswith("*PART"):
                state = "part"; pending_part = None; continue
            if s.startswith("*SECTION_SHELL"):
                state = "sec"; continue
            if U.startswith("*MAT_"):
                state = "mat"; continue
            if s.startswith("*"):
                state = "idle"; continue
            if s.startswith("$") or not s:
                continue

            if state == "title":
                if not title:
                    title = s
                continue
            if state == "node":
                if "," in line:
                    p = [x.strip() for x in s.split(",")]
                else:
                    p = s.split()
                if len(p) >= 4:
                    nid = _num(p[0]); x = _num(p[1]); y = _num(p[2]); z = _num(p[3])
                    if None not in (nid, x, y, z):
                        nodes[int(nid)] = (x, y, z)
                continue
            if state == "elem":
                ns = None; pid = None
                if "," in line:
                    p = [x.strip() for x in s.split(",")]
                    if len(p) >= 5:
                        pid = _num(p[1])
                        ns = [_num(p[2]), _num(p[3]), _num(p[4]),
                              _num(p[5]) if len(p) >= 6 else 0.0]
                elif len(line) >= 40:
                    pid = _num(line[8:16])
                    ns = [_num(line[16:24]), _num(line[24:32]),
                          _num(line[32:40]), _num(line[40:48])]
                if pid is not None and ns and None not in ns:
                    elems[int(pid)].append(tuple(int(v) for v in ns))
                continue
            if state == "part":
                # *PART -> (optional title line) -> "pid sec mid ..."
                if pending_part is None:
                    # first non-title data line carries pid
                    toks = s.split()
                    pid = _num(toks[0])
                    if pid is not None:
                        pending_part = int(pid)
                        sec = _num(toks[1]) if len(toks) > 1 else None
                        mid = _num(toks[2]) if len(toks) > 2 else None
                        parts[pending_part] = {"sec": int(sec) if sec else None,
                                               "mid": int(mid) if mid else None}
                continue
            if state == "sec":
                # *SECTION_SHELL -> title -> "sec mid ..."; we only need existence
                continue
            if state == "mat":
                toks = s.split()
                mid = _num(toks[0])
                if mid is not None:
                    mats[int(mid)] = U.split("_", 1)[-1] if False else state
                continue
    return {"nodes": nodes, "elems": dict(elems), "parts": parts,
            "mats": mats, "title": title}


# ---------- 拓扑分析 helper ----------

def edge_use_map(elems_by_pid):
    """全局边使用次数: {(a,b):count}"""
    from collections import defaultdict
    use = defaultdict(int)
    for pid, els in elems_by_pid.items():
        for ns in els:
            m = len([n for n in ns if n != 0])
            nodes = [n for n in ns if n != 0]
            for i in range(m):
                a, b = nodes[i], nodes[(i + 1) % m]
                if a == b:
                    continue
                use[(a, b) if a < b else (b, a)] += 1
    return use


def free_edges_by_pid(elems_by_pid, use=None):
    """每 PID 的自由边数(全局只用一次的边)。返回 {pid:count}"""
    if use is None:
        use = edge_use_map(elems_by_pid)
    out = {}
    for pid, els in elems_by_pid.items():
        c = 0
        for ns in els:
            nodes = [n for n in ns if n != 0]
            m = len(nodes)
            for i in range(m):
                a, b = nodes[i], nodes[(i + 1) % m]
                if a == b:
                    continue
                if use[(a, b) if a < b else (b, a)] == 1:
                    c += 1
        out[pid] = c
    return out


def node_pids(elems_by_pid):
    """节点 -> 所属 pid 集合"""
    np_ = defaultdict(set)
    for pid, els in elems_by_pid.items():
        for ns in els:
            for n in ns:
                if n != 0:
                    np_[n].add(pid)
    return np_


def shared_nodes_between(a, b, np_):
    return [n for n, ps in np_.items() if a in ps and b in ps]


def min_edge_by_pid(elems_by_pid, nodes):
    """每 PID 最小/最大边长(mm)。返回 {pid:(emin,emax)}"""
    import math
    out = {}
    for pid, els in elems_by_pid.items():
        emin, emax = 1e18, 0.0
        for ns in els:
            nn = [n for n in ns if n != 0]
            m = len(nn)
            for i in range(m):
                a, b = nn[i], nn[(i + 1) % m]
                if a == b or a not in nodes or b not in nodes:
                    continue
                ax, ay, az = nodes[a]; bx, by, bz = nodes[b]
                d = math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)
                emin = min(emin, d); emax = max(emax, d)
        out[pid] = (emin, emax)
    return out


def connectivity(elems_by_pid):
    """每 PID 连通分量数(按共节点)。返回 {pid:ncomp}；单分量=整块连通。"""
    from collections import defaultdict, deque
    out = {}
    for pid, els in elems_by_pid.items():
        adj = defaultdict(set)
        alln = set()
        for ns in els:
            nn = [n for n in ns if n != 0]
            alln.update(nn)
            for i in range(len(nn)):
                adj[nn[i]].add(nn[(i + 1) % len(nn)])
                adj[nn[(i + 1) % len(nn)]].add(nn[i])
        seen = set(); ncomp = 0
        for start in alln:
            if start in seen:
                continue
            ncomp += 1
            dq = deque([start]); seen.add(start)
            while dq:
                u = dq.popleft()
                for v in adj[u]:
                    if v not in seen:
                        seen.add(v); dq.append(v)
        out[pid] = ncomp
    return out


if __name__ == "__main__":
    import sys, json
    k = parse_kfile(sys.argv[1])
    print("title:", k["title"])
    print("nodes:", len(k["nodes"]), "pids:", {p: len(e) for p, e in k["elems"].items()})
    print("parts:", k["parts"])
    print("min_edge:", min_edge_by_pid(k["elems"], k["nodes"]))
    print("free_edges:", free_edges_by_pid(k["elems"]))
    print("connectivity:", connectivity(k["elems"]))
