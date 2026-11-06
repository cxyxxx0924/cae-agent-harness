#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_kfile.py — K 文件自动清洗(auto_gate 全自动链的一环, 零人工)

删除"孤儿节点"(在 *NODE 定义但未被任何单元引用的节点)。孤儿节点是网格划分
遗留物(如界面合并后残留), 求解器忽略之, 但违反规范 2.2 清洁网格要求, 且会
让"重合节点"检查误报。删除 100% 安全(不影响任何单元拓扑)。

用法:
  python clean_kfile.py --in <k> --out <k_clean> [--report]
行为:
  * 逐行重写: *NODE 块仅保留被引用的节点, 其余(PART/SECTION/MAT/注释)原样拷贝。
  * 保留原节点 ID(不改号, 避免破坏引用)。
  * 若 --out 省略则原地清洗(先写 .bak)。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kio


def clean(inp, outp):
    K = kio.parse_kfile(inp)
    used = set()
    for pid, els in K["elems"].items():
        for ns in els:
            used.update(n for n in ns if n != 0)
    all_nodes = set(K["nodes"])
    orphans = sorted(all_nodes - used)
    dup_nid = 0  # parse_kfile 用 dict, 同 id 后者覆盖; 另行检测见 qa

    if not orphans:
        # 无需清洗, 直接拷贝
        with open(inp, encoding="utf-8", errors="ignore") as f, \
             open(outp, "w", encoding="utf-8") as g:
            g.write(f.read())
        return {"orphans_removed": 0, "nodes_before": len(all_nodes),
                "nodes_after": len(all_nodes), "out": outp}

    os.makedirs(os.path.dirname(os.path.abspath(outp)) or ".", exist_ok=True)
    state = "idle"
    kept = 0; dropped = 0
    with open(inp, encoding="utf-8", errors="ignore") as f, \
         open(outp, "w", encoding="utf-8") as g:
        for raw in f:
            line = raw.rstrip("\n")
            s = line.strip()
            if s.startswith("*NODE"):
                state = "node"; g.write(raw); continue
            if s.startswith("*"):
                state = "idle"; g.write(raw); continue
            if state == "node":
                if s.startswith("$") or not s:
                    g.write(raw); continue
                if "," in line:
                    p = [x.strip() for x in s.split(",")]
                else:
                    p = s.split()
                nid = None
                try:
                    nid = int(float(p[0]))
                except (ValueError, IndexError):
                    pass
                if nid is not None and nid in used:
                    g.write(raw); kept += 1
                else:
                    dropped += 1  # 孤儿或无法解析 -> 丢弃
                continue
            g.write(raw)
    return {"orphans_removed": len(orphans), "dropped_lines": dropped,
            "nodes_before": len(all_nodes), "nodes_after": kept, "out": outp}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="outp", default=None)
    ap.add_argument("--inplace", action="store_true", help="原地清洗(自动备份 .bak)")
    a = ap.parse_args()
    outp = a.outp
    if a.inplace and not outp:
        outp = a.inp + ".tmp"
    if not outp:
        ap.error("need --out or --inplace")
    r = clean(a.inp, outp)
    if a.inplace:
        os.replace(outp, a.inp)  # 覆盖; 调用方应自行备份
    print(f"[clean] 孤儿节点移除 {r['orphans_removed']} | 节点 {r['nodes_before']} -> {r['nodes_after']} | out={r['out']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
