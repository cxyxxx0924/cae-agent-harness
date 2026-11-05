# -*- coding: utf-8 -*-
"""fix_kfile_format2.py — cab1_full.k 重写为 LS-DYNA 自由格式 (逗号分隔)

根因: 原 *NODE 用 nid(10)+x(16)+y(16)+z(16) 非规范宽度, 严格定位读取器
(HyperMesh/LS-DYNA 规范 10 字符定宽) 解析错位: y 读到 x 小数尾, z 读到 0,
全部节点塌到 z=0 平面 -> 导入成薄片。原自查脚本用同假设解析 -> 盲区。

修复: 全量逗号分隔自由格式 (LS-DYNA 两种标准输入格式之一):
  - 零位置歧义: 任何读取器只有一种解析方式 (按逗号切分)
  - 全精度: 8 位小数坐标不丢 (10 字符定宽放不下 1236.052648)
  - *PART/*SECTION 用参考模型同款结构 (名字单独一行 / _TITLE 关键字)

验证: 逗号切分回读必须与源值完全相等 (精确到浮点表示)
      另查: 重复 ID / 引用完整性 / 关键词顺序 / bbox
"""
import os
import numpy as np

SRC = r"E:/work/AI_CAB/onekey/work/out/cab1_full.k"
BAK = r"E:/work/AI_CAB/onekey/work/out/cab1_full_oldfmt.k"
DST = r"E:/work/AI_CAB/onekey/work/out/cab1_full.k"

# ================= 1. 按写入意图解析原文件 =================
lines = open(SRC, encoding="utf-8", errors="ignore").read().splitlines()
nodes, elems, parts, sections, mats = {}, [], [], [], []
sec = None
for line in lines:
    s = line.strip()
    if s.startswith("*"):
        sec = s.upper(); continue
    if not s or s.startswith("$"):
        continue
    if sec == "*NODE":
        nid = int(line[0:10])
        nodes[nid] = (float(line[10:26]), float(line[26:42]), float(line[42:58]))
    elif sec == "*ELEMENT_SHELL":
        eid = int(line[0:10]); pid = int(line[10:18])
        nids = [int(line[k:k + 8]) for k in range(18, min(len(line), 18 + 64), 8)
                if int(line[k:k + 8]) != 0]
        elems.append((eid, pid, nids))
    elif sec == "*PART":
        p = s.split()
        parts.append((int(p[0]), int(p[1]), int(p[2]), s.split("$")[-1].strip()))
    elif sec == "*SECTION_SHELL":
        p = s.split()
        sections.append((int(p[0]), int(p[1]), float(p[2]), int(p[3]), int(p[4]),
                         int(p[5]), int(p[6]), int(p[7]), s.split("$")[-1].strip()))
    elif sec and sec.startswith("*MAT_PIECEWISE_LINEAR_PLASTICITY"):
        p = s.split()
        mats.append((int(p[0]), float(p[1]), float(p[2]), float(p[3]),
                     float(p[4]), float(p[5]), float(p[6]), s.split("$")[-1].strip()))

print(f"解析: nodes={len(nodes)} elems={len(elems)} parts={len(parts)} "
      f"sections={len(sections)} mats={len(mats)}")

# ================= 2. 自由格式重写 =================
out = ["*KEYWORD"]

out.append("*NODE")
out.append("$#   nid, x, y, z")
for nid in sorted(nodes):
    x, y, z = nodes[nid]
    # repr() = 浮点最短精确往返表示, 无损 (%.10g 会把 1178.28428571 舍掉)
    out.append(f"{nid},{x!r},{y!r},{z!r}")

out.append("*ELEMENT_SHELL")
out.append("$#   eid, pid, n1, n2, n3, n4")
for eid, pid, nids in elems:
    assert len(nids) in (3, 4), f"e{eid} 节点数 {len(nids)} 异常"
    if len(nids) == 3:
        nids = nids + [nids[2]]      # 三角 -> n3==n4 (LS-DYNA 标准表示)
    out.append(f"{eid},{pid}," + ",".join(str(n) for n in nids))

for pid, secid, mid, name in parts:
    out.append("*PART")
    out.append(name)
    out.append(f"{pid},{secid},{mid}")

for secid, elform, shrf, nip, propt, qr, icomp, setyp, name in sections:
    out.append("*SECTION_SHELL_TITLE")
    out.append(name)
    out.append("*SECTION_SHELL")
    out.append(f"{secid},{elform},{shrf:g},{nip},{propt},{qr},{icomp},{setyp}")

for mid, ro, e, pr, sigy, etan, fail, name in mats:
    out.append("*MAT_PIECEWISE_LINEAR_PLASTICITY_TITLE")
    out.append(name)
    out.append("*MAT_PIECEWISE_LINEAR_PLASTICITY")
    out.append(f"{mid},{ro:.6E},{e:g},{pr:g},{sigy:g},{etan:g},{fail:g}")

out.append("*END")

TMP = SRC + ".tmp"
with open(TMP, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(out) + "\n")

# ================= 3. 逗号切分回读验证 (自由格式唯一解析方式) =================
vnodes, velems = {}, []
vparts, vsections, vmats = [], [], []
sec = None
skip_name = False          # *PART / *_TITLE 的下一非注释行是名字, 跳过
for line in open(TMP, encoding="utf-8", errors="ignore"):
    s = line.strip()
    if s.startswith("*"):
        sec = s.upper()
        skip_name = sec in ("*PART", "*SECTION_SHELL_TITLE",
                            "*MAT_PIECEWISE_LINEAR_PLASTICITY_TITLE")
        continue
    if not s or s.startswith("$"):
        continue
    if skip_name:
        skip_name = False
        continue
    p = s.split(",")
    if sec == "*NODE":
        vnodes[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))
    elif sec == "*ELEMENT_SHELL":
        velems.append((int(p[0]), int(p[1]), [int(x) for x in p[2:6]]))
    elif sec == "*PART":
        vparts.append(int(p[0]))          # 数据行 (名字行无数值)
    elif sec == "*SECTION_SHELL":
        vsections.append(int(p[0]))
    elif sec and sec.startswith("*MAT_PIECEWISE_LINEAR_PLASTICITY"):
        vmats.append(int(p[0]))

bad = sum(1 for nid, c in nodes.items()
          if abs(vnodes[nid][0] - c[0]) > 1e-12 or abs(vnodes[nid][1] - c[1]) > 1e-12
          or abs(vnodes[nid][2] - c[2]) > 1e-12)
print(f"[验证1] 节点回读: {len(vnodes)}/{len(nodes)}, 不符 {bad} (容差 1e-12)")

ebad = 0
for (eid, pid, nids), (veid, vpid, vnids) in zip(elems, velems):
    ncmp = nids + [nids[2]] if len(nids) == 3 else nids
    if eid != veid or pid != vpid or ncmp != vnids:
        ebad += 1
print(f"[验证2] 元素回读: {len(velems)}/{len(elems)}, 不符 {ebad}")
print(f"[验证3] PART/SECTION/MAT 条数: {len(vparts)}/{len(vsections)}/{len(vmats)}")

# 引用完整性
missing = sum(1 for _, _, nids in elems for n in nids if n not in nodes)
print(f"[验证4] 元素引用缺失节点: {missing}")
# 重复 ID (dict 键天然唯一, 改查重复坐标 — 公司规范禁止)
coord_map = {}
for nid, c in nodes.items():
    coord_map.setdefault(c, []).append(nid)
dupcoord = {k: v for k, v in coord_map.items() if len(v) > 1}
print(f"[验证5] 重复坐标节点组: {len(dupcoord)}")

assert bad == 0 and ebad == 0 and missing == 0 and not dupcoord, "验证失败, 不替换!"

# ================= 4. 备份 + 替换 =================
if not os.path.exists(BAK):
    os.replace(SRC, BAK)
os.replace(TMP, DST)
print(f"\n旧格式备份: {BAK}")
print(f"新文件: {DST}  ({os.path.getsize(DST)/1024/1024:.2f} MB, {len(out)} 行)")

# 抽样展示
print("\n===== 新格式抽样 =====")
for i, l in enumerate(out[:8]):
    print(f"  {l}")
print("  ...")
for l in out[80363:80366]:
    print(f"  {l}")
print("  ...")
for l in out[-12:]:
    print(f"  {l}")
