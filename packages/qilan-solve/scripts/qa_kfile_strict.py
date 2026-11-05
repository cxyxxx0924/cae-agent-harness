#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LS-DYNA K 文件独立严格校验器
=============================
铁律(2026-10-19 翻车教训): 本校验器**独立解析**, 绝不与写入脚本共享字段假设。
上次事故: 写入器把 *ELEMENT_SHELL 写成 "pid,n1,n2,n3,n4" (漏 eid),
          诊断脚本与写入器用同一切片假设 -> 回读永远"正确" -> 客户/HM 打开直接卡死。
本脚本按 LS-DYNA 官方字段顺序独立读取, 且**比任何读取器更严**。

用法: python qa_kfile_strict.py <file.k> [file2.k ...]
退出码: 0=全部通过  1=存在致命错误
"""
import sys
import collections

# LS-DYNA 官方字段顺序 (本校验器的唯一真值来源, 手写硬编码)
ELEM_SHELL_FIELDS = ["eid", "pid", "n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"]
NODE_FIELDS = ["nid", "x", "y", "z"]
PART_FIELDS = ["pid", "secid", "mid", "eosid", "hgid", "grav", "adpopt", "tmid"]

FATAL = 0
WARN = 0


def fail(msg):
    global FATAL
    FATAL += 1
    print(f"  [FATAL] {msg}")


def warn(msg):
    global WARN
    WARN += 1
    print(f"  [WARN ] {msg}")


def check(path):
    global FATAL, WARN
    FATAL = WARN = 0
    print(f"\n{'='*66}\n检查: {path}\n{'='*66}")

    raw = open(path, "rb").read()
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as e:
        fail(f"文件非纯 ASCII (第 {e.start} 字节 0x{raw[e.start]:02x}) — HM/LS-DYNA 读入可能异常")
        text = raw.decode("utf-8", errors="replace")

    lines = text.split("\n")

    # ---------- 1. 分段解析 ----------
    sections = collections.OrderedDict()   # kw -> [line_no, fields]
    cur = None
    parts = {}          # pid -> title
    nodes = {}          # nid -> (x,y,z)
    elems = []          # (line_no, fields)
    secids, mids = set(), set()

    for ln, line in enumerate(lines, 1):
        s = line.rstrip()
        if not s.strip() or s.lstrip().startswith("$"):
            continue
        if s.lstrip().startswith("*"):
            cur = s.strip().upper().split()[0]
            sections.setdefault(cur, []).append(ln)
            continue
        if cur is None:
            fail(f"第 {ln} 行有数据但无关键字: {s[:60]}")
            continue
        f = [x.strip() for x in s.split(",")]

        if cur == "*NODE":
            if len(f) < 4:
                fail(f"第 {ln} 行 *NODE 字段不足(需 nid,x,y,z): {s[:60]}")
                continue
            try:
                nid = int(float(f[0]))
            except ValueError:
                fail(f"第 {ln} 行 *NODE nid 非整数: {f[0]}")
                continue
            if nid <= 0:
                fail(f"第 {ln} 行 *NODE nid<=0: {nid}")
            if nid in nodes:
                fail(f"第 {ln} 行 *NODE nid 重复: {nid} (首次出现于前序行)")
            nodes[nid] = (float(f[1]), float(f[2]), float(f[3]))

        elif cur in ("*ELEMENT_SHELL", "*ELEMENT_SHELL_THICKNESS"):
            elems.append((ln, f))

        elif cur == "*PART":
            # PART 卡 = title 行 + 数据行。数据行**可能无逗号**(定宽/空格分隔),
            # 必须先按数值判定, 否则会被误当成 title -> 漏掉全部 pid
            cols = s.split(",") if ("," in s and len(f) >= 3) else s.split()
            nums = []
            for c in cols[:3]:
                try:
                    nums.append(int(float(c)))
                except ValueError:
                    nums = None
                    break
            if nums and len(nums) >= 2:
                pid = nums[0]
                parts[pid] = parts.get("_title", "")
                if len(nums) >= 2: secids.add(nums[1])
                if len(nums) >= 3: mids.add(nums[2])
            else:
                parts["_title"] = s.strip()      # title 行

    # ---------- 2. 单元卡严格检查 (核心) ----------
    print(f"  *NODE           : {len(nodes)} 个")
    print(f"  *ELEMENT_SHELL  : {len(elems)} 个")
    print(f"  *PART           : pid={sorted(p for p in parts if isinstance(p, int))}")

    if not elems:
        fail("没有任何单元")

    eids = []
    inner_dup = []
    pid_seen = set()
    nid_missing = collections.Counter()
    node_count = collections.Counter()
    dup_shape = collections.Counter()

    for ln, f in elems:
        if len(f) < 5:
            fail(f"第 {ln} 行 *ELEMENT_SHELL 字段数 {len(f)} < 5 (至少 eid,pid,n1,n2,n3)")
            continue
        try:
            eid = int(float(f[0])); pid = int(float(f[1]))
            ns = [int(float(x)) for x in f[2:6] if x]
        except ValueError:
            fail(f"第 {ln} 行 *ELEMENT_SHELL 含非数值: {','.join(f)[:60]}")
            continue

        # eid 唯一性 —— 本次事故的核心
        eids.append(eid)
        if eid <= 0:
            fail(f"第 {ln} 行 eid<=0: {eid}")

        pid_seen.add(pid)
        if parts and isinstance(pid, int) and pid not in parts:
            pass  # 汇总后统一报
        for n in ns:
            if n not in nodes:
                nid_missing[n] += 1
        node_count[len(ns)] += 1
        # 单元内重复节点 (退化四边形: n4==n3, 汇总报, 不刷屏)
        if len(set(ns)) != len(ns):
            inner_dup.append((ln, ns))
        dup_shape[tuple(sorted(ns))] += 1

    # eid 重复统计
    dup = [e for e, c in collections.Counter(eids).items() if c > 1]
    if dup:
        fail(f"单元 ID 重复: {len(dup)} 个不同 eid 被重复使用, "
             f"总重复行 {len(eids)-len(set(eids))} (样例 {dup[:5]})")
    else:
        print(f"  eid 唯一性      : OK (1 ~ {max(eids) if eids else 0}, 无重复)")

    # pid 有效性
    valid_pids = set(p for p in parts if isinstance(p, int))
    if valid_pids:
        ghost = pid_seen - valid_pids
        if ghost:
            fail(f"单元引用了 {len(ghost)} 个未定义的 PID (幽灵 part, 样例 {sorted(ghost)[:5]}) "
                 f"— 这会让 HM 读入时卡死")
        else:
            print(f"  pid 有效性      : OK (全部落在 {sorted(valid_pids)})")
    else:
        fail("未解析到任何 *PART 卡")

    # 节点引用有效性
    if nid_missing:
        fail(f"单元引用了 {len(nid_missing)} 个不存在的节点 (样例 {list(nid_missing)[:5]})")
    else:
        print(f"  节点引用        : OK (全部存在)")

    if inner_dup:
        n_tria_style = sum(1 for _, ns in inner_dup if len(ns) == 4 and ns[2] == ns[3])
        fail(f"单元内部有重复节点: {len(inner_dup)} 行 "
             f"(其中 n4==n3 退化四边形 {n_tria_style} 个; 样例 行{inner_dup[0][0]} {inner_dup[0][1]})")
    else:
        print(f"  单元内重复节点  : OK (0)")

    # 重复单元 (同节点集)
    dups = [k for k, c in dup_shape.items() if c > 1]
    if dups:
        fail(f"重复单元(同节点集): {len(dups)} 组 (样例 {dups[:3]})")
    else:
        print(f"  重复单元        : OK (0)")

    print(f"  单元类型分布    : " +
          ", ".join(f"{k}节点={v}" for k, v in sorted(node_count.items())))

    # ---------- 3. 引用完整性 ----------
    if secids and not any(k.startswith("*SECTION") for k in sections):
        fail(f"*PART 引用 secid={sorted(secids)} 但无 *SECTION_SHELL 卡")
    if mids and not any(k.startswith("*MAT") for k in sections):
        fail(f"*PART 引用 mid={sorted(mids)} 但无 *MAT_* 卡")

    # ---------- 4. 结论 ----------
    print(f"\n  致命错误 {FATAL} 个, 警告 {WARN} 个 -> "
          f"{'PASS 可安全读入' if FATAL == 0 else 'FAIL 禁止交付'}")
    return FATAL


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    total = 0
    for p in sys.argv[1:]:
        try:
            total += check(p)
        except FileNotFoundError:
            print(f"\n文件不存在: {p}")
            total += 1
    sys.exit(0 if total == 0 else 1)
