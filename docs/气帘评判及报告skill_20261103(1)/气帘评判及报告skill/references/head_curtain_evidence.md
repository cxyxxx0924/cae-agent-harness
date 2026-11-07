# 头型 vs 展开气帘：离线几何证据管线（重叠图 / 断面 / 厚度）

> 来源：2026-11-03 这轮报告新增的能力。法规要求「数字对」还不够，报告必须给
> **头型与展开后气帘叠在一起的图、断面、气垫厚度剖面**这类直观图。
> 这套离线管线（不依赖 GUI）生成 P12–P15 的图，比 HV 渲染更可控、能标尺寸。

工程师常用路子（也在这套里复用）：
**HyperView 把某时刻气帘展开态导出成 k → 与头型 .key 一起读入 → 做断面 / 量厚度 / 布置。**

---

## 0. 为什么不直接用 HyperView 出这些图

| | HV 渲染（`render_model_shots`） | 本离线管线（matplotlib） |
| --- | --- | --- |
| 配色 | 默认部件色，不可控 | 完全可控 |
| 尺寸/文字标注 | 无 | 有（厚度双箭头、CoG 十字、评估区） |
| 断面/厚度数值 | 要二次量 | 直接算、图数一致 |
| 依赖 | 必须 GUI + bridge 在线 | 只依赖 numpy/scipy/matplotlib |
| 适用 | 「原始 CAE 对照」 | **进报告的最终图** |

结论：**形态对照用 HV，进报告的标注图用离线管线。** 两者都进报告（P12 并列）。

---

## 1. 输入与产物

| 输入 | 说明 |
| --- | --- |
| 气帘 deck `5P-BAG_005.key` | 含 pids 4/6/7/8（88184 shells / 87265 nodes） |
| HV 导出的末态节点坐标 `nodes_last.json` | `rows=[[id,[x,y,z]],...]`，某时刻（本例 t=200ms / state 82）气帘变形后坐标 |
| 头型 `head_area/*.key` | `HIII_5F_Head.key` / `..._Rear.key` / `HIII_95M_Head.key` / `..._Rear.key` |
| 头型布置 `main_dummy.key` 的 TRANSL | 4 组平移（前/后 + 5F/95M），决定头型在整车系的位置 |

产物：`heads_vs_curtain.key`（合并 deck，保留原始节点 ID）+ `heads_vs_curtain.npz`（离线渲染缓存）
+ 4 张图（`fig_overlap / fig_sections_yz / fig_zone / fig_thickness_x`）+ `sections.json`（数值表）。

**保留原始节点 ID 是关键**：这样合并 deck 还能再被 HyperView 与 `2974.h3d` 一起读，
头型作为「无结果几何」叠在云图上；而 npz 供离线渲染。

---

## 2. 三步脚本（见 `scripts/g14_headcurtain_*.py`）

### 步骤 1：`g14_headcurtain_build.py` —— 合并 deck + 写 npz
- 解析气帘 deck（固定列宽：`%8d%16.6f%16.6f%16.6f` 读 node，`%8d%8d...` 读 shell），
  只取 pids 4/6/7/8；用 `nodes_last.json` 的变形坐标替换节点位置。
- 解析 4 个头型 .key，按 TRANSL 平移；头型节点/单元/part **ID 偏置** `10M/20M/30M/40M` 避免撞车，
  part id 用 `9001..9004`。
- 写出 `*KEYWORD` deck，**`*PART`/`*SECTION_SHELL` 必须写全三段**（title 行 + `$#` 字段行 + 数据行），
  少一行 HyperView 加载即崩。
- 同时写 `heads_vs_curtain.npz`：气帘节点/单元/pid + 各头型节点/单元/offset（0-based 索引，供渲染）。

### 步骤 2：`g14_headcurtain_sections.py` —— 断面 + 厚度 + 间隙
- `plane_segments(pts, tri, axis, value)`：三角面汤与 `pts[:,axis]==value` 平面求交，逐边插值，
  返回 `(N,2,3)` 线段（按面收集交点，每面取前两点）。
- 厚度 = YZ 断面在头型 CoG 高度 **±30 mm 窗**内的 Y 跨度。
  ⚠️ 窗宽以前试过 ±10 mm，会在腔间喉部退化成 0.8 mm（假薄）→ **必须用 ±30 mm**。
- 间隙 = 头型表面节点到气帘节点 `cKDTree` 最近距离（`min`/`mean`）。
- 输出 `sections.json`：`bag` 包络 + 每个头型的 `bag_y`(Y 跨度)/`thickness`/`gap_min`/`gap_mean`。

本例实测（mm）：5F front 44.2/7.8、5F rear 84.3/0.6、95M front 145.4/0.4、95M rear 74.9/0.4
（前者厚度、后者 min gap）。

### 步骤 3：`g14_headcurtain_figs.py` —— 4 张进报告图
自带正交相机（az=58°/el=22°）+ 画家算法（按深度排序）+ Lambert 着色，不依赖 GUI：

| 图 | 内容 |
| --- | --- |
| `fig_overlap.png` (F1) | 等轴测 4 头型叠气帘，含图例 |
| `fig_sections_yz.png` (F2) | 2×2 同轴 YZ 断面，厚度双箭头 + CoG 十字 |
| `fig_zone.png` (F3) | 乘员侧投影 + G.3 评估区(82/82/82/52, r=82) + 头型落点 |
| `fig_thickness_x.png` (F4) | 气帘 Y 包络沿 X + 各头型处厚度标记 |

坐标事实（写进图前先确认）：
- **+Y = 乘员侧**（Protect_Area 的 Y 只有 50/110 两片；头型平移后 Y 48–192；气帘 Y −127…+117）。
- 头型 CoG：`HEAD_COG` 表（X/Z 用于切 YZ 断面，Y≈120 用于标注）。
- 评估区 `ZONE`：x0=1288, x1=2812, z0=1018, z1=1362（来自 G.3 圆角四边形）。

---

## 3. 跑法

三个脚本默认从仓库的 `docs/file_for_CAB/` 读取 Iter04 模型与四个 HIII 网格，证据写入该算例的 `evidence/` 目录。目录可通过环境变量覆盖：`CAB_CASE_DIR`、`CAB_MODEL_DIR`、`CAB_HEAD_DIR`、`CAB_EVIDENCE_DIR`；步骤 1 的 HyperView 状态导出文件可通过 `CAB_NODES_JSON` 指定，默认是 `docs/file_for_CAB/evidence/nodes_last.json`。

```bash
cd <repo>/docs/气帘评判及报告skill_20261103(1)/气帘评判及报告skill/scripts
python g14_headcurtain_build.py      # -> heads_vs_curtain.key / .npz
python g14_headcurtain_sections.py   # -> sections.json (+ _debug_yz.png)
python g14_headcurtain_figs.py 1 2 3 4   # -> 4 张图
```
运行前需将 HyperView 导出的 `nodes_last.json` 放到默认位置或设置 `CAB_NODES_JSON`。依赖：`numpy scipy matplotlib`（系统 python 即可，venv 里没有 Pillow 也不影响）。

---

## 4. 坑（这轮新踩）

1. **`*PART` 少写一行 → HyperView 加载即崩**：必须 title + `$#` + 数据三行俱全。
2. **厚度窗宽 ±10 mm 退化成 0.8 mm**：切到腔间喉部，假薄；改 ±30 mm。
3. **断面函数旧实现按全局收集交点会错**：要按「面」收集、每面取前两点。
4. **头型单元索引基准错**：记录 `head_bases[label]`，索引 = `m[n] - head_bases[label]`。
5. **2×2 四面板要统一坐标范围**：`XLIM=(-160,230), YLIM=(880,1460)` + `set_aspect("equal", adjustable="box")`，
   否则四张断面无法直接对比；标题用 `fig.text` 左上，别压面板标题。
6. `LineCollection` 传参要 `np.stack([bs[:,:,1], bs[:,:,2]], -1)`（取 Y/Z 列），别写错维度。
7. 合并 deck 要**保留气帘原始节点 ID**，否则无法再与 H3D 叠加出云图对照。
8. `fig_sections` 里的 import 是 `from g14_headcurtain_sections import plane_segments`，
   文件名改了要同步改这个 import（脚本已按 `g14_headcurtain_*` 前缀改名）。
