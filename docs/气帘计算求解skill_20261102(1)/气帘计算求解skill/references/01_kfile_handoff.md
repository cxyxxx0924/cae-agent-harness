# 01 · K 文件交付 → 求解 衔接铁律

> 网格交付的 `.k` 是求解的入口。这一关出错，下游求解全部白跑（HM 死机 / 求解器读错拓扑 / 飞丝）。
> 本文件沉淀 NEW_CAB 与 cab1 两轮踩过的 K 文件坑。**网格生成脚本在 CURVEtoMESH 技能，本文件只讲"交付前的最后门禁"。**

## 1. 格式铁律（2026-10-19 用户二次进坑，已修复）

- **薄片 ≠ 视角问题，是写入格式错**。4 位数坐标（如 `1601.2793`）+ 6 位小数，定宽 10 字符格式会把
  `1601.2793` 写成 9 字符后补位错列，**一律用逗号自由格式**（首选，零歧义）或严格 10 字符定宽。
- **QA 验证器必须比真实读取器更严**，绝不能和写入器共享字段假设（翻车主因：写入器以为自己写对了，
  验证器用同一套假设 → 假 PASS）。`qa_kfile_strict.py` 是独立解析器，不复用组装脚本逻辑。
- 注释行去非 ASCII（— / ± / 中文），否则某些读取器按字节错位。

## 2. 血泪坑位（来自网格→K 阶段，跨技能沉淀）

### P39（★★★）单元卡漏写 eid → HM2026/2020 读文件死机
- 现象：HM 读我生成的文件死机，用户自己的十几兆模型秒读。
- 根因：assembly 把 `*ELEMENT_SHELL` 写成 `pid,n1,n2,n3,n4`，漏掉 eid。
  LS-DYNA 官方顺序 = `eid,pid,n1..n4`，错位后 eid 全表重复、n1 被读成 pid → 63058 个幽灵 part → 拓扑崩。
- 修复：eid 从 1 唯一递增，三角 5 列 / 四边 6 列；`SECTION_SHELL` 改 `elform=2 shrf=1.0`。
- 加固：交付门禁 `qa_kfile_strict.py`（独立解析，退出码门禁）。

### P40 退化四边形 / 伪单元
- 零面积 / 近零面积单元（`T1=374mm²`、`T2=3.6mm²` 类）在 automesh 阶段就该剔除；
  组装后靠 `qa_kfile_strict.py` 查"n1==n2 或节点不共线"。
- 拉带伪单元（节点集与布带完全相同）→ 按**节点集无序比对** `tuple(sorted(ns))` 剔除。

### P29（★★★）跨文件 id 引用飞丝 → 导出 txt 的 nid ≠ K 的 gid
- 现象：HM 读入 `.k` 后全模型拉丝（十几~几十 mm 斜线），但 qa_kfile_strict PASS（QA 只查拓扑合法性）。
- 根因：组装写 K 时 **gid 重编号**（sorted(txt nid)→1..N），导出 txt 的 nid 不连续 → 两 id 空间整体错位。
  后续拉带捏合拿 txt 的 nid+坐标当 K 的 gid → 每个合并指到"隔壁"节点 → 飞丝。
- 修复：拉带装配的目标节点**直接从 K 文件解析**（*NODE 坐标 + PID2 单元节点集），不碰中间 txt。
- **铁律**：引用 K 文件节点的后续装配，id+坐标必须从**目标 K 本身**解析；中间导出只用于渲染/统计。
- 交付门禁加 `diag_long_edges.py`（XZ>20mm / 3D>30mm 必须为 0；本会话实测 1174 条长边→0）。

### P58 per-PID 自由边误判
- 逐 PID 算自由边会把**跨 PID 共享边**误判为自由（缝线曾显示 848"自由边"）。
- 自由边必须**全局计一次数**再按 PID 归属；写 K **前**就剔退化（先写后剔 = deck 带病）。

### P59 写 K 前就要剔退化
- 退化单元在组装阶段就过滤（先写后剔 = deck 带病交付）；`qa_kfile_strict.py` 是最后一道关。

## 3. 交付前最后门禁（脚本，镜像自 CURVEtoMESH 技能）

```bash
PY="C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
# 1) K 严格校验（eid 唯一 / pid 合法 / 无退化 / 无重复单元 / 三角+四边数）
$PY scripts/qa_kfile_strict.py newcab_step1.k
# 2) 几何匹配自检：IGES 线段 vs 网格几何，逐环空间/形状/面积对拍（按 mesh_pid 分层防面积翻倍）
$PY scripts/geom_match_check.py --workdir <ws>
# 3) 拉带连通检查：须接 PID2、共节点占周长 <50%
$PY scripts/tether_conn_check.py --workdir <ws>
# 4) 长边门禁（飞丝铁证）
$PY scripts/diag_long_edges.py newcab_step1.k   # XZ>20mm / 3D>30mm 必须为 0
# 格式修整（如定宽残留）
$PY scripts/fix_kfile_format2.py newcab_step1.k   # 回读比对 1e-12
```

> 这三道几何/拓扑门禁脚本在 CURVEtoMESH 技能里维护，本技能**镜像副本**仅供求解阶段独立调用。
> 上游技能更新时，覆盖本目录 `scripts/qa_kfile_strict.py`、`fix_kfile_format2.py`、
> `geom_match_check.py`、`tether_conn_check.py` 即可。

## 4. 自检清单（交付前逐条勾）

- [ ] `qa_kfile_strict.py` 退出码 0：eid 1~N 唯一、pid ∈ 合法集、无退化、无重复单元
- [ ] 自由边：充气口/外轮廓合法自由边除外，其余应为 0
- [ ] 长边（XZ>20 / 3D>30） = 0（飞丝铁证）
- [ ] 拉带连通全 PASS（接 PID2、共节点占比合理）
- [ ] 几何匹配全 PASS（凸包比≈1.000、质心偏≈0）
- [ ] 坐标 + id 引用全部从目标 K 解析（不混用中间 txt）
