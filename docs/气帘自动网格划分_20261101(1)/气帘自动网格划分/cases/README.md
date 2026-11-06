# cases/ — 案例配置（换项目只动这里）

每个子目录 = 一个已交付案例的**全部可变参数**。技能脚本零案例硬编码，
所有案例差异（模型名、PID 方案、分层、必需部件、组装参数、门禁基线路径）都收敛到 `case.json`。

## 目录约定

```
cases/
├── README.md                  本文件
├── <案例名>/
│   ├── case.json              ★该案例的全部参数（run_case.sh 的唯一输入）
│   ├── gate_case_vN.json      auto_gate 校验配置（可保留多个历史基线做回归）
│   └── command1.tcl           （可选）该案例的 HM 会话命令记录，供复现/审计
```

## case.json 字段

| 字段 | 必需 | 含义 | 示例 |
|---|---|---|---|
| `case` | ✅ | 案例名。**STEP2/STEP2B 的缺省文件名由它派生**（`<case>_step2_tether.txt`） | `"cab2"` |
| `model` | ✅ | `$WORK/input/` 下的 HM 库文件名 | `"cab2.hm"` |
| `plane` | ✅ | 图纸→模型映射：`xy` = 图纸X→模型X、图纸Y→模型Z | `"xy"` |
| `thickness_axis` | ✅ | 厚度轴（分层方向）：cab2 几何在 XY 平面 → `"z"`；cab1 在 XZ 平面 → `"y"` | `"z"` |
| `loop_tol` | | 成环端点聚类容差 mm，默认 0.8。闭环数多于缝线条数就调小 | `0.8` |
| `layers[]` | ✅ | 每个角色：`role/cid/tag/pid/z`。`z` 单值=单层，双值=双层 | 见下 |
| `parts[]` | ✅ | **必需部件清单**。缺任何一个，组装阶段直接 `SystemExit`（P48） | `["belt","cavity","seam","tether","side"]` |
| `seam` | | 缝面筛选：`min_area` / `sort` / `max_count` | `{"min_area":200}` |
| `mesh` | ✅ | `size` / `seam_size` / `bl_thick` / `bl_layer` / `bl_etype` | 见下 |
| `quality_gate` | | 质量口径（碰撞网格默认值见 `references/15`） | 见下 |
| `assemble` | ✅ | 组装与锚固定版参数，见下表 | 见下 |
| `gates` | | 门禁基线路径（相对 WORKDIR 或相对技能根） | 见下 |

`layers` 示例（cab2）：
```json
[
  {"role": "belt",   "cid": 2, "tag": "L1", "pid": 2, "z": [0.0]},
  {"role": "cavity", "cid": 3, "tag": "L2", "pid": 3, "z": [-0.5, 0.5]},
  {"role": "seam",   "cid": 4, "tag": "L3", "pid": 4, "z": [0.0]},
  {"role": "tether", "cid": 5, "tag": "L4", "pid": 5, "z": [-1.0]}
]
```
> `cid` 是 .hm 里的 collector id，**必须用 `stage1_survey/survey_comps.tcl` 实测**，
> 不要继承上一个案例（P28：别信 comp 名字，按 spline 面积判）。

`assemble` 字段（全部有默认值，但建议每案例写全）：

| 字段 | 默认 | 含义 |
|---|---|---|
| `anchored_tethers` | `false` | 是否跑 ⑥b 锚固三刀切（有拉带就要开） |
| `tab_tol` | `0.35` | 拉带节点吸附容差 mm。>1 会把错位的节点硬拉过去，产生扭转片 |
| `snap_inside_tol` | `0.0` | 内部锚固（缝在布带里的侧条）二次焊接容差；没有侧条就保持 0 |
| `weak_anchor_min` | `1` | 外边界锚点少于几个就判弱锚。**默认 8 会误伤凸台，设 1**（P53） |
| `edge_band` | `4.0` | 凸台顶帽水平边带宽 mm |
| `tabs_polys` | — | 拉带轮廓 JSON（案例级产物，`tabs_extract.py` 出） |
| `step2` / `step2b` | 由 `case` 派生 | 主拉带 / 侧面拉带网格 txt，**只写文件名，不带 `out/`**（P54） |

`gates` 字段：

| 字段 | 含义 |
|---|---|
| `gate_case` | auto_gate 配置路径（`cases/<案例>/gate_case_vN.json`） |
| `partition_manifest` | 分区覆盖基线（`partition_cover_check.py --write` 生成）。**不写就没有防丢块门禁** |

## 新案例接入三步

1. `cp -r cases/cab2 cases/<新案例名>`，改 `case.json`（`case` / `model` / `plane` / `layers` / `parts`）；
2. 跑 `bash scripts/drivers/run_case.sh --case cases/<新案例名>/case.json --work <项目目录>`；
   首次会在 ⑦d 提示没有基线 → 用认可的那一版 `--write` 建 `out/ref_manifest.json`，
   回填到 `gates.partition_manifest`；
3. 把该案例实测数字加进 `assets/baselines.json` + `references/20_baselines.md`。

> 详细 runbook（含每阶段验收数字、失败分支、该问人的问题）见
> `references/00_RUNBOOK_接新气帘.md`。

## gate_case.json 字段（auto_gate 用）

| 字段 | 含义 | 示例 |
|---|---|---|
| `case` | 案例名（报告/图里标注） | `"cab1_clean"` |
| `k_file` | 待校验 K，支持 `${WORKDIR}` 占位 | `"${WORKDIR}/out/cab1_step1_2026_clean.k"` |
| `cad_lines_2d` | CAD 线采样点云（2 值 `x z`） | `"${WORKDIR}/out/lines_pts_2d.txt"` |
| `map` | 图纸→模型坐标映射 | `"xy"` |
| `pid_scheme` | 角色→PID（**必须实测**，P28） | `{"belt":2,"cavity":3,"seam":4,"tether":5}` |
| `cad_tag` | 角色→CAD 线文件行标签 | `{"belt":"BELT","cavity":"CAV","seam":"SEAM"}` |
| `layers` | 角色→厚度坐标 | `{"belt":0.0,"cavity":[-0.5,0.5],"seam":0.0,"tether":-1.0}` |
| `mesh_nominal_mm` | 标称网格尺寸（弦误差判据用） | `5.0` |

## 已登记案例

| 案例 | 说明 |
|---|---|
| `cab1` / `cab1_clean` | 首个全链验证案例（XZ 平面，PID 2/3/4/5 + 6/7/8）。原始交付含 33,790 孤儿节点（占 29%），是"套件能发现问题"的证据 |
| `cab2` | **当前主力**（XY 平面，厚度轴 Z）。v8 定版：83,808 单元 / 9 个拉带组分 / 不合格 0.10%，MD5 `d8e50902f4a41e8029ba87eb502f18d5`。`gate_case_v3/v4/v8` 保留三代基线做回归 |
| `cab3` | 无人值守链验证（规模约 cab2 的 1/6），配置在 `scripts/drivers/cab3_auto/` |
