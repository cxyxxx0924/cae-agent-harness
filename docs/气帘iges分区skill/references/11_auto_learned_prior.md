# 11 · 全自动模式：学到的气帘研判先验（tree_model.json）

> 对应 `scripts/auto_partition.py` + `scripts/tree_model.json` + `scripts/featurize.py`。
> 目标：把"视觉—功能—组别—曲线连贯性"综合研判**自动化、通用化、可沉淀**。

## 1. 思路（不是改权重，是显式知识工程）

用户强调"沉淀 ≠ 训练"。本模块的"学习"是：用**一份专家认可结果**（newcab v14 金标准）
作为监督样本，把"几何/连贯性/位置特征 → 四分类"的映射拟合成一棵**可解释决策树**并序列化。
特征是纯几何量（无线号），所以树对同类气帘图纸通用——这正符合"资产 = 规则条目/脚本模块"的框架。

## 2. 特征（featurize.compute_features）

对每条线计算（全部相对全局质心/包络归一化，故尺度/位置无关）：

| 特征 | 含义 | 区分什么 |
|---|---|---|
| `len_n` | 线长 / 最长线 | 长线=结构(布带/气腔/缝线)，短线=硬件细节(TETHER/符号) |
| `maxr_n/midr_n/minr_n` | 到质心半径(最大/中点/最小) | 外层=布带/硬件，内层=气腔/缝线 |
| `dhull_n` | 到凸包距离 | 是否贴最外轮廓 |
| `shell_rank` | 角向 15° 邻域内径向排序(0=最外) | **BELT=最外闭环** vs 内缩气腔 |
| `aspect` | 长宽比 log | 窄长=缝线/边界 |
| `closed` | 端点焊接闭合 | 闭环符号/小环 |
| `comp_size_n` | 连通分量规模 log | 硬件多片 vs 大环 |
| `cx_n/cy_n` | 位置(归一化) | 顶边凸台/左充气口/右补丁 |
| `sin_ang/cos_ang` | 角度 | 区域方向 |
| `n_tan` | 切线连续邻居数 | 是否在连续链上(连贯性) |
| `w_n/h_n` | 包围盒宽高 | 形态 |
| `is_long` | 是否长线(≥25mm) | 结构 vs 细节初分 |
| `onhull` | 是否在凸包上 | 最外轮廓 |

## 3. 模型与验收

- 训练：`train_joint.py` 用**三金标准**——newcab（828 线 = 721 分类 + 107 lines0）+
  cab1（338 线 = 314 分类 + 24 lines0）+ cab3（911 线 = 802 分类 + 109 lines0）——联合拟合
  `DecisionTreeClassifier`（POOLED 2077 条，depth=20，269 节点），训练准确率 **100%**（三张图都精确复现认可结果）。
- 序列化：`tree_model.json`（269 节点，含 `feature_order/classes/nodes/trained_on`），纯 Python 遍历即可应用，**零 sklearn 运行时依赖**。
- 应用：`auto_partition.py` 对目标图重算特征 → 树推理 → `classify_final.json`（仅 4 类，lines0 不写入）。
- **目标图验收**：
  - `Drawing0904ZHEDIETU.iges`(NEW_CAB 源)：逐线 **721/721，VERIFY_FAIL=0**（认可结果零回退）。
  - `cab1.hm` 人工金标准（5P-BAG 图）：自动产出 `cap1.hm`，与人工分组**逐 id 314/314 相同，VERIFY_FAIL=0**。
  - `cab3.hm` 人工金标准（6P 图）：自动产出 `cap3.hm`，与人工分组**逐 id 802/802 相同，VERIFY_FAIL=0**。
  - `5P-BAG.igs`（同图自动导入）：**BELT=7/CAVITY=2/SEAM=56/TETHER=249**，与人工 cab1 吻合（包络误判已修正）。

## 4. 泛化边界（诚实记录，含 5P-BAG 实测）

- CAVITY / SEAM / 内部结构：跨图泛化良好（5P-BAG 抽检验证）。
- **BELT vs 最外硬件（充气口/凸台）**：单金标准(newcab-only)时二者半径同层、纯几何阈值难以二分，
  曾把 5P-BAG 外包络整圈误判成 TETHER。**已由双金标准联合拟合根治**（见 §4.4）。

### 4.1 5P-BAG 跨图实测（2026-10-23）

`E:/work/AI_CAB/5P-BAG.igs`（338 线，X-Z 平面，同一棵树零重训）跑 `run_auto.sh` 基线：

```
BELT=45  CAVITY=50  SEAM=54  TETHER=147  lines0=42   (VERIFY_FAIL=1 仅为未分配组件命名边角, 四类 COUNT 全 OK)
```
CAVITY/SEAM 与内部结构合理；但**最外层大包络整圈被误判成 TETHER**——
5P-BAG 外包络是切成很多短段、段间有间隙的，与 newcab 的长段外包络不同，
决策树把"短+外圈→TETHER"的统计规律套了上去（same reason newcab 训练时 TETHER 多为短硬件线）。

### 4.2 补"最外整圈→BELT"增量规则的尝试与失败（关键证据）

为修这道缝，试了三条纯几何路线，全失败：

| 路线 | 结果 |
|---|---|
| 半径 / 凸包距离阈值 | 气帘是细长形，82% 线都贴着凸包 → 分不出外包络 |
| 切向闭合环追踪（链式） | 短段间有间隙，非拓扑闭合 → 识别出 **0 个**闭合环 |
| 端点焊接 + 角度跨度最大分量 | 外包络碎片化成多块，挑中的是中部带钩回环的内部分量 |

且该规则会把 **newcab 的 10 条外接硬件 TETHER 误并进 BELT**，使 721/721 掉到 695/721。
——充分证明这道缝纯几何无法二分，硬规则必回退认可结果。

### 4.3 决定：不给自动流水线打脆性增量规则

- 外包络 vs 外接硬件的归属是**人工语义判据**（用户原话"语义归人，几何归机器"）。
- `scripts/delta_belt_envelope.py` 仅作**诊断实验**保留（默认 `--dry` 不改文件，实测不可靠，**未接入 `run_auto.sh`**）。
- 新图纸出现包络混淆时，按 §2 交互铁律 + 既有 S3–S4 **幂等 delta** 人工精炼：
  渲染标准底图 → 人在图上确认外包络 → 把人工语义判据固化为脚本应用。**不推翻自动基线**。

> **2026-10-23 后续：该路径已走通**——用户提供了 5P-BAG 的人工金标准 `cab1.hm`，已并入训练集联合拟合，见 §4.4。

### 4.4 双金标准联合拟合根治包络边界（2026-10-23，当前方案）

- 用户人工金标准 `E:/work/AI_CAB/气帘CAD数据/cab1.hm`（=5P-BAG 图人工分组）曲线分在
  `component1(7)/component2(2)/component3(56)/component4(249)` + `_5P-BAG_Wireframe(24,→lines0)`。
- **几何+视觉综合研判**定映射：`component1→BELT`(贴凸包最外闭环) / `component2→CAVITY`(内缩闭合环) /
  `component3→SEAM`(内层散弧) / `component4→TETHER`(局部硬件簇)。工具：`dump_comp_lines.tcl`
  + `render_per_component.py`（逐组件单独渲染）+ `analyze_components.py`（按组件聚合特征）。
- 从 cab1.hm 同源提取采样点与金标签（同一 line-id 序，与 t07 对齐）→ featurize → 与 newcab
  **联合拟合** `train_joint.py`（155 节点，双图 100%）。
- **效果**：NEW_CAB 仍 721/721 零回退；cab1 逐 id 314/314；**5P-BAG 自动分类变为
  BELT=7/CAVITY=2/SEAM=56/TETHER=249，与人工 cab1 吻合**——那道"语义归人"缝被正确切分。
- **结论**：BELT-vs-最外硬件的边界靠**增加金标准联合拟合**（监督学习正确切分）解决，而非纯几何硬阈值。

### 4.5 cab3（6P）盲测 → 第三份金标准并入（2026-10-23，当前方案）

- **盲测**：双金标准先验跑未见图纸 `S31 CAB_AIR BAG ASSY_6P_20240827.iges`（911 线，X-Y）：
  BELT=83/CAVITY=236/SEAM=20/TETHER=461/lines0=111——结构大体合理，但放大检查发现**同类件不同判**：
  ① 顶排 9 个"房子+方框"充气口单元被拆成 TETHER/CAVITY/lines0 三种；
  ② 右下"圆环+杆"有 CAVITY 与 lines0 两种分法；③ 中部楔形区整体未分配。
- **用户手工精分**为 `cab3.hm`（911 线 = `component1(67)/component2(109)/component3(40)/component4(586)`
  + `_lines0_Wireframe(109→lines0)`）。映射（几何聚合+逐组件渲染研判，工具同 §4.4）：
  `component1→BELT`(最外整圈闭合包络) / `component2→CAVITY`(大气腔环+右下圆环+杆腔室) /
  `component3→SEAM`(3 个内层孤立闭合环) / `component4→TETHER`(顶排充气口+右簇+密集短线网：
  586 条 88% 闭合、len_med≈0.012、ntan≈17)。
- **三金标准联合拟合**：`train_joint.py` 的 `DRAWS` 加入 cab3 → POOLED 2077 条，depth=20，269 节点，三图 hold-in 100%。
- **验证**：NEW_CAB 721/721 零回退；cab1 314/314；cab3 802/802（`cap3.hm` 与人工五组逐 id 相同）；
  5P-BAG 仍 7/2/56/249。
- **结论**：先验靠"金标准增量"自我完善——每张新图的盲测不一致，就是下一轮训练的监督信号。
  用户侧流程：盲测 → 图上人工精分 → 并入 `train_joint.py` → 联合拟合 → 验证零回退 → 覆盖默认树。

## 5. 怎么重训 / 扩展

**训练集已全部沉淀在技能目录 `golden/` 下**（三份金标准：`newcab/`、`cab1/`、`cab3/`，
各含金标签 + 同源 features.json + 源图纸 + 出处说明 source.txt；总览见 `golden/README.md`）。
`train_joint.py` 只读 `golden/`（路径相对脚本自身计算，**技能文件夹整体复制即带走全部训练能力**）。

1. 在新图纸上获得专家金标准（人工/既有 `partitioned.hm` 回读成 `classify_*.json`；
   若金标准是带 comp 名的 .hm，用 `dump_comp_lines.tcl` 枚举 comp→线，再按几何/视觉映射到 4 类）。
2. `python feat_driver.py <工作区>` 生成该图 `out/features.json`。
3. 在 `train_joint.py` 的 `DRAWS` 列表登记 `(label, features.json, golden_line_comp.json)`；
   并把金标准文件按 `golden/<name>/` 布局收拢（源图纸 + .hm + 标签 + features + source.txt）。
4. 重跑 `train_joint.py` → 生成 `tree_model_joint.json`；**先在老图上验证无回退**
   （auto_partition 后与各 `golden/<name>/*.json` 逐线比对）再覆盖 `tree_model.json`。`auto_partition.py` 无需改动。

> 复现精度的两个口径（诚实记录）：**同会话内**（从金标准 .hm 自身提特征）逐线 100%；
> **全新导入**（源 IGES 重新导入后再推理）受导入会话差异影响有少量边界线波动——
> 如 cab3 源图全新导入复现 798/800（99.75%）：L774/L778 金标准 BELT→判 CAVITY（BELT/CAVITY 边界灰带）、
> L342/L781 落 lines0。newcab/cab1 源图全新导入均为 100% 复现。

## 6. 踩过的坑

- `train.py` 导出树时 `leaf` 字段是 numpy.bool，不可 JSON 序列化 → 转原生 `bool`。
- 管道 `| head` 触发 SIGPIPE（P54）截断 `json.dump` → 输出落盘规避。
- 坐标平面必须自动判定（P42）：5P-BAG 是 X-Z（y≡0），newcab 是 X-Y；渲染/特征统一按判定平面取 2D 坐标。
