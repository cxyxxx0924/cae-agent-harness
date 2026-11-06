---
name: qilan-iges-partition
description: 气帘 CAD 四分区端到端技能——从**原始 IGES/IGS/DXF** 出发，导入 HyperMesh 2026（全部 2D 曲线通常挤在 1 个 component），产出 4 个 component（布带 BELT / 气腔 CAVITY / 缝线 SEAM / 拉带 TETHER）的 partitioned.hm。两种用法：**① 全自动 v2**（默认推荐，2026-10-31）——"视觉—功能—连贯性"先验：轮廓内向深度 + 切向链 + 局部密集度特征 + 两阶段随机森林 + 物理规则兜底，一键 S0→AUTO2→S8 零人工确认；**留一图交叉验证（LODO）条数准确率 0.961、结构长度加权 0.943**（三张真实图纸互测，训练时没见过被留出那张）；**② 人工精炼模式**——种子分类+逐版 delta+渲染人眼复核，适合与样例结构差异极大的新图。当用户说"气帘分区 / IGS 曲线分类 / 布带气腔缝线拉带 / 曲线归环 / 分区识别 / 充气口误入拉带 / 水滴源头回归 / 缝线哑铃两头圆圈 / 小圆圈符号剔除 / 自动分区 / 一键分区 / 交叉验证"时使用。沉淀自 2026-10-21 NEW_CAB 实战，2026-10-23 做全自动模块，2026-10-31 用三图 LODO 驱动重构特征与模型（v1→v2）。
---

# 气帘 CAD 四分区（原始 IGES → BELT / CAVITY / SEAM / TETHER）

> **本目录是"原始 CAD → 四分区"的唯一维护点。**
> 分区之后的网格化（裁切建面 → automesh → Y 分层 → K → 门禁）在
> `E:\work\skill\hypermesh2026_CURVEtoMESH_skill`，**本技能止于 `partitioned.hm`**。
> 项目里只保留路径指向 + 调用本目录脚本，不要在具体项目里另写一份。

**基线**：HyperWorks 2026.0.0.27，`D:\Program Files\Altair\2026`
hmbatch：`D:\Program Files\Altair\2026\hwdesktop\hm\bin\win64\hmbatch.exe`
Python：`C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe`（numpy/matplotlib）
用户模板：`LsDyna Keyword971_R16.0`（Tcl 开头必须加载，见 §9）

---

## 0. 一句话链路

```
原始 IGES ──S0 导入──> curves.hm(1 comp) ──S1/S2 导出──> geom_features.txt + lines_pts.txt
   ──S3 人工种子分类──> classify_v8.json ──S4 delta 累积(v9…v14)──> classify_final.json
   ──S5 渲染+终检报告(人眼确认)──> ──S6 导出 id 列表──> ──S7 搬线建 4 comp──>
   ──S8 独立回读校验(唯一真门禁)──> partitioned.hm
```

**一键**：`WORKDIR=<工作区> IGES=<原始图纸> SEED=<种子json> DELTA=v14 SKIP_CONFIRM=1 bash scripts/run_full.sh`

---

## 0.5 全自动模式 v2（视觉—功能—连贯性先验，零人工确认）★★ 当前推荐

> 2026-10-31 重构。用 `E:/work/AI_CAB/分区训练/` 的三套「原始 IGES + 人工分区 .hm」做
> **留一图交叉验证**（LODO）驱动设计：先证明旧方案不可泛化，再按物理语义重做特征与模型。

**为什么必须重做**：旧 v1 决策树在**同图**上 100% 拟合，但留一图盲测只有
0.71~0.82 条数准确率——**低于"全部猜 TETHER"的朴素基线（0.73~0.79）**，等于没学到可迁移规律。
病根：① 用了 `cx_n/cy_n/sin_ang/cos_ang` 等**绝对位置**特征（树在背布局）；
② 用**凸包距离**衡量"离边界多远"——气帘细长，82% 的线都贴凸包，无判别力；
③ 线长按**最大线长**归一，被个别超长线带偏。

**v2 的三条物理量**（`featurize2.py`，全部尺度无关、跨图可比）：

| 量 | 含义 | 为什么能分开四类 |
|---|---|---|
| `dep_min/dep_med`（轮廓内向深度）| 全部线栅格化 → 形态学闭运算 + 填洞 → 布片实体轮廓 → 距离变换 | 布带贴轮廓 ≈0.001；气腔环内缩 ≈0.02；缝线在腔体深处 ≈0.07 |
| `ch_*`（切向连续链）| 按切向顺滑（dot>0.7）把线串成链，取链的周长/包围盒/闭合性/中位深度 | 气腔环是绕整圈的长链（`ch_len`≈1.3~2.8）；缝线是小闭环（`ch_len`≈0.5，`ch_dep`深）；硬件是 1 条线的碎链（`ch_len`≈0.01） |
| `dens_cnt/cl_size`（局部密集度）| 中点邻域内其它线条数 + 短线互焊得到的符号簇规模 | 充气口/安装件是极短线段挤成的簇（dens 15~26、簇 4~16 条）；结构线不挤 |

外加**图内百分位**（`rk_*`）与 `dep_rel`，消除"不同图整体深度水平不同"导致的阈值漂移。

**模型：两阶段森林**（`train_v2.py` → `tree_model_v2.json`，运行期纯 Python，不依赖 sklearn）
- A 段：symbol(TETHER+lines0) vs structure(BELT/CAVITY/SEAM)　← 粗分，极稳
- B 段：structure 内部分 BELT / CAVITY / SEAM　← 细分，靠深度层级
- 物理兜底规则：`ch_dep > 0.055 且 ch_len < 0.90 → SEAM`（深且不绕整圈 = 气腔内部缝线环）。
  三图实测零有害误判，只误伤 lines0 散碎线。

**一键**：
```bash
WORKDIR=<工作区> IGES=<原始图纸> bash scripts/run_auto2.sh
```
（自动判平面 X-Y/X-Z；跳 t01 规避 2026 JUNC 崩；末段 p06→t07→t08 与标准链路一致；
v2 不产生 lines0 残线——所有线都落类，t08 的 TOTAL 即全图线数）

**留一图交叉验证 LODO（唯一的诚实泛化口径）**：

| 留出图 | 条数准确率 | 结构长度加权 | BELT 长度召回 | CAVITY | SEAM | TETHER |
|---|---|---|---|---|---|---|
| cab1（5P-BAG，338 线，X-Z）| 0.971 | 0.919 | 0.97 | 1.00 | 0.88 | 0.87 |
| cab2（NEW_CAB，828 线，X-Y）| 0.964 | 0.944 | 0.96 | 0.87 | 1.00 | 0.97 |
| cab3（6P，911 线，X-Y）| 0.949 | 0.964 | 0.94 | 0.93 | 1.00 | 1.00 |
| **平均** | **0.961** | **0.943** | | | | |

三个绘图风格、三张不同图纸、**训练时没见过被留出那张**——这才叫泛化。
（同图拟合口径另有记录：cab1 314/314、cab2 692/696、cab3 797/802 逐线一致，
差异全部是"金标准 lines0 → 被判成某类"，即把本不分类的散碎线也归了类，视觉无害。
复现：`python scripts/eval_vs_golden.py`）

> **2026-10-31 修订 (9)**：用户指出 `cab2.hm` 的 `L5`（18 条）不是拉带，已并入 `lines0`
> （新版 `.hm`：`_lines0_Wireframe` 114→132，`L5` 消失，总 828 线不变）。
> 只改 `--map` 重解构、**特征 md5 不变、零重算**，重训后 LODO 0.957→**0.961**（长度加权 0.936→0.943）。
> 该 18 条实为 20~30mm 的碎线簇（`len_diag≈0.01`、`cl_size 6~8`），此前一直在教模型"碎线簇可以是结构件"。
> 详见 `references/13_vision_prior_v2.md` §2.1。

**自包含（整个文件夹复制即带走，已实测）**：
```bash
python scripts/rebuild_from_golden.py   # 只用 golden/ 离线重算 32 维特征 → 三图 max|Δ|=0（不需要 HyperMesh）
python scripts/train_v2.py              # 只读 golden/ → 先打印 LODO，再导出 tree_model_v2.json
python scripts/eval_vs_golden.py        # 读 cases/ 里冻结的三图结果 → 逐线对金标准
bash scripts/run_auto2.sh               # 有 HyperMesh 时：新图纸一键分区
```
`golden/<name>/` 自带 `source.iges` + `<name>.hm` + `comp_lines.json` + `comp_agg.json` +
`golden_panels.png` + `lines_pts.txt` + 标签/特征，**解构过程与判据可回放**；
`cases/v2_<name>/` 是当年交付的 `partitioned.hm` 与渲染/校验报告快照。

> **唯一权威源 = 本目录**。技能实际加载的是 `~/.workbuddy/skills/qilan-iges-partition`，
> 改完这里记得 `bash scripts/sync_to_install.sh`（自动备份旧副本并校验 md5）。

**已知边界（诚实栏）**
- 密集硬件符号内部的碎线，人工标注本身就不一致（cab3 同一类符号里混标了 BELT 30 条 / lines0 49 条 /
  CAVITY 8 条，cab2 同位置全标 TETHER）。这类样本无法互相满足，是当前主要残余误差来源。
- `BELT` 按**条数**的召回偏低（0.57~0.89）——被硬件符号切碎的短布带段易判成 TETHER；
  但按**线长**召回 0.94~0.97，即主包络永远是对的。
- 与三张图纸结构差异极大的新图（如全新气帘构型），仍建议跑完先看渲染图，必要时按 §2 交互铁律做
  幂等 delta，并把新金标准并入 `golden/` 重训（五步法见 `golden/README.md`）。

---

## 0.5b 历史：全自动模式 v1（单棵决策树，已被 v2 取代，仅留档）

> ⚠️ 下面这套（`tree_model.json` + `auto_process.py`/`auto_partition.py`）在同一张图上能到 100%，
> 但 LODO 实测 0.71~0.82、低于朴素基线，**不要用于新图纸**。保留它是为了可追溯早期做法与坑位。

### v1 详情（留档）

> 把"视觉—功能—组别—曲线连贯性"综合研判**自动化**：以金标准 `newcab/partitioned.hm`(v14)
> 为监督样本，拟合一棵决策树作为"气帘研判先验"（`tree_model.json`），对同类气帘 IGS
> **一键**产出四分区，全程无人工逐步确认。目标图（NEW_CAB）逐线精确匹配验收基准。

```
原始 IGES ──S0 导入──> curves.hm(1 comp) ──S2 导出──> lines_pts.txt
   ──AUTO 自动分类──> classify_final.json ──S6 导出──> class_lists.tcl
   ──S7 搬线建 4 comp──> partitioned.hm ──S8 校验(VERIFY_FAIL=0)──> 交付
```

**一键**：
```bash
WORKDIR=<工作区> IGES=<原始图纸> bash scripts/run_auto.sh
```
（自动判定坐标平面 X-Y/X-Z；跳 t01 规避 2026 JUNC 段崩溃；末段 p06→t07→t08 与标准链路一致）

**学到的先验是什么**（沉淀自 2026-10-23，已升级为**三金标准联合训练**）：
- `featurize.py` 对每条线算**纯几何+连贯性+位置**特征（长度 / 径向壳层 `shell_rank` /
  凸包距离 / 长宽比 / 分量大小 / 切线连续邻居数 / 角度 …），**不依赖任何线号 → 跨图通用**。
- `tree_model.json` = 在**三份金标准**上联合拟合的决策树（269 节点，三图 100% 拟合）：
  ① NEW_CAB v14（BELT34/CAVITY89/SEAM43/TETHER555/lines0 107，828 线）
  ② cab1 人工金标准（`component1→BELT / component2→CAVITY / component3→SEAM / component4→TETHER`，338 线）
  ③ cab3 人工金标准（同映射规则，911 线；`_lines0_Wireframe`→lines0）
  序列化后纯 Python 遍历应用（零 sklearn 运行时依赖）。
  历史版本备份：`tree_model_v1_newcab.json`（单金标准）/ `tree_model_v2_joint_cab1.json`（双金标准）。
- `auto_partition.py` = 特征提取 + 树推理 → 输出 `classify_final.json`（仅 4 类，lines0 不写入）。
- 重训（换/补金标准）：`feat_driver.py <工作区>` 生成特征 → 在 `train_joint.py` 的 `DRAWS` 登记金标准
  → 重跑生成 `tree_model_joint.json`，**先在老图上验证无回退**再覆盖 `tree_model.json`（见 references/11 §5）。

**验收**：
- NEW_CAB（`Drawing0904ZHEDIETU.iges`）：**逐线 721/721，VERIFY_FAIL=0**（认可结果零回退）。
- cab1（`cab1.hm` 人工金标准）：**逐线 314/314 精确一致，VERIFY_FAIL=0**，自动产出 `cap1.hm`。
- cab3（`cab3.hm` 人工金标准，6P）：**逐线 802/802 精确一致，VERIFY_FAIL=0**，自动产出 `cap3.hm`。
- 5P-BAG（`5P-BAG.igs`，与 cab1 同图，338 线 X-Z）：现在 **BELT=7/CAVITY=2/SEAM=56/TETHER=249**
  ——外层包络正确归 BELT、硬件正确归 TETHER，与人工 cab1 分组吻合。

**泛化边界（已从"语义归人"痛点升级为"多金标准监督"解决）**：
`cab1` 金标准把"最外层布带包络（BELT=component1，贴凸包）vs 最外硬件（充气口/发生器/安装凸台
TETHER=component4，局部簇）"的正确切分教给了先验——这正是早期单金标准(newcab-only)在 5P-BAG 上
把"外包络整圈误判成 TETHER"的那道缝。`cab3` 金标准又补上了 6P 图纸的 TETHER 密集短线网特征
（586 条 88% 闭合、len_med≈0.012）与"中部楔形褶皱区归 TETHER、气腔底挂圆环+杆归 CAVITY"的判据。
**根本解法 = 增加金标准联合拟合，而非纯几何硬阈值**
（早期三条纯几何路线实测全失败，且会把 newcab 721/721 打到 695/721，证据存档于 references/11 §4.2）。
`scripts/delta_belt_envelope.py` 仍仅作诊断实验保留（默认 `--dry`，未接入 `run_auto.sh`）。
未来若遇与三份金标准结构差异极大的新图仍现混淆：沿用 §2 交互铁律 + S3–S4 幂等 delta 人工精炼，
并把新金标准并入 `train_joint.py` 再联合拟合。

---

## 1. 何时用 / 何时不用

**用**：
- 气帘 2D 展开图 IGS 导入 HM 后，所有曲线挤在**一个 component**（IGS 导入只有 1 个 comp）
- 需要按布带/气腔/缝线/拉带四类拆成 4 个 component，供后续裁切建面/分层
- 用户给了口述几何特征（"左下右平直、上方充气口锐角"、"底部水滴"、"哑铃两头圆圈"、"顶部六七个凸台"）

**不用**：
- IGS 本身就带 component 结构（CATIA 预整理过）→ 直接按 comp 名映射，无需本技能
- 3D 几何 / 体网格 → 用 hypermesh2026-curve-to-mesh

---

## 2. 四分区判据（用户口述 → 可执行规则）

| 分区 | 用户口述特征 | 可执行判据 |
|---|---|---|
| **BELT 布带** | 最外闭环；左下右平直+转角圆弧；**上方充气口锐角 30–40°**；宏观连续、导数光滑，大转角只在充气口 | bbox 最大（外包全部）；端点焊接后是最大连通片；切线连续链最长；含 x 范围中上部向上突起的领圈 |
| **CAVITY 气腔** | 左/右/上贴近外环；**底部挂很多水滴**（圆头+茎） | 第二大环；与 BELT **嵌套**（不是互斥）；底边有 ≥3 个闭合小环（水滴）通过短茎连到腔体边界 |
| **SEAM 缝线** | 独立的**内部**窄线 + **两头圆圈 = 哑铃状**，"两头圆圈才能封闭" | 位于 BELT 内部不贴边；窄带（宽 <30mm）两端各一个**闭合圆**（多段弧拼成，见 P37）；每条哑铃 0 悬挂端 |
| **TETHER 拉带** | 顶部 6–7 个凸台 + 左侧革眼 + 右侧补丁；**充气口和水滴源头不是拉带** | 城堡状跨 BELT 顶边的组件；左端 40mm 圆+十字；右端梯带/矩形补丁。**充气口领圈、水滴源头、气腔右腰链必须回归原环**。TETHER 天然是多片（凸台/革眼/补丁各自成片），**不要追求单连通** |

**交互铁律（用户强调）**：几何/图形类工作用**图像**交互——先渲染标准底图，
人在图上确认，再落脚本；不要用"自动搜索"猜语义。每一版分类都必须出
4 面板 + 总览 + 局部 zoom 图给人看。**用户发标注截图时，必须先渲染一张带坐标
标注的图与其标注逐位核对，再动手改**（v14 明示）。

---

## 3. 端到端链路（S0–S8，脚本全在本目录 scripts/）

| 阶段 | 动作 | 脚本 | 产物 |
|---|---|---|---|
| **S0** | 原始 IGES/IGS/DXF 导入 | `t00_import_iges.tcl`（`IGES=` 图纸路径） | `curves.hm` + `out/t00_import_report.txt` |
| **S1** | 全量几何特征导出 | `t01_export_geom.tcl` | `out/geom_features.txt`（长/起终点/起终切线 + JUNC 夹角 + CIRC 三点圆拟合） |
| **S2** | 采样点导出（渲染底图） | `t02_export_pts.tcl` | `out/lines_pts.txt`（32 段/线） |
| **S3** | **【人工】种子分类** | 判据 §2 + `p03_bridge_scan.py` / `p03b_trace_chain.py` | `out/<SEED>.json`（如 `newcab_classify8.json`） |
| **S4** | 应用修正 delta（幂等累积） | `v9_apply_fix.py` / `v10_*` / `v12_*` / `v13_*` / `v14_*`（`DELTA=` 选） | `out/classify_final.json` + 连通性 QA |
| **S5** | 渲染 + 终检报告（**人眼确认**） | `p05_render_partition.py`、`p07_report.py` | `out/v_partition*.png`、`out/final_report.txt` |
| **S6** | 导出 Tcl id 列表 | `p06_export_class_lists.py` | `out/class_lists.tcl` |
| **S7** | 搬线建 4 comp（hmbatch） | `t07_make_comps.tcl` | `partitioned.hm` + `out/make_comps_report.txt`（需 `ALL_OK=1`） |
| **S8** | 独立回读校验（**唯一真门禁**） | `t08_verify_partitioned.tcl` | `out/verify_partitioned.txt`（需 `VERIFY_FAIL=0`） |

辅助工具：`chain_trace.py`（沿编号+顺滑方向追链，§7.9）、`q09_seam_check.py`（哑铃闭合）、
`q10_region_connect.py`（争议区连通）、`v9_recon*.py`/`v9_render.py`/`v13_render.py`（问题区侦察与特写渲染）。

### 运行方式（**所有脚本认 `WORKDIR` 环境变量，零硬编码**）

```bash
export WORKDIR="E:/work/AI_CAB/onekey/work/newcab"   # 项目工作区（英文路径）
export IGES="E:/work/AI_CAB/onekey/work/input_newcab/newcab.iges"
export SEED="newcab_classify8.json"                  # out/ 下的种子分类
export DELTA="v14"                                   # v9/v10/v12/v13/v14/none
SKIP_CONFIRM=1 bash "E:/work/skill/气帘iges分区skill/scripts/run_full.sh"
```

单步跑（调试/断点续跑）：

```bash
PY="C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
HMBATCH="D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe"

IGES="$IGES" WORKDIR="$WORKDIR" "$HMBATCH" -tcl .../t00_import_iges.tcl
WORKDIR="$WORKDIR" HM_IN=curves.hm  "$HMBATCH" -tcl .../t01_export_geom.tcl
WORKDIR="$WORKDIR"                  "$HMBATCH" -tcl .../t02_export_pts.tcl
V14_SRC="$SEED" WORKDIR="$WORKDIR"  "$PY"      .../v14_remove_tiny_circles.py
WORKDIR="$WORKDIR"                  "$PY"      .../p07_report.py
WORKDIR="$WORKDIR"                  "$PY"      .../p06_export_class_lists.py
rm -f partitioned.hm out/verify_partitioned.txt     # P35 / P49
WORKDIR="$WORKDIR" HM_OUT=partitioned.hm "$HMBATCH" -tcl .../t07_make_comps.tcl
WORKDIR="$WORKDIR" HM_OUT=partitioned.hm "$HMBATCH" -tcl .../t08_verify_partitioned.tcl
```

工作区文件约定（中性名，换项目照抄）：
`curves.hm` / `out/geom_features.txt` / `out/lines_pts.txt` /
`out/<SEED>.json` / `out/classify_final.json` / `out/class_lists.tcl` / `partitioned.hm`。

> **编排脚本**：端到端 = `scripts/run_full.sh`（本次升级新增，含 S0 导入）。
> 老链 `run_all.sh`（v8 初版）/ `run_v9.sh`（v9 单版）保留作参考，**新项目一律用 run_full.sh**。

---

## 4. 核心判据：切线搭接（P36，本技能的命门）

两条线 X（端点 E）和 Y（端点 F）**平滑搭接**（导数同向）的充要条件：

```
(E == 'ep') != (F == 'ep')  ->  dot(tangent_X@E, tangent_Y@F) ≈ +1
(E == 'ep') == (F == 'ep')  ->  dot ≈ -1
```

**只看 `dot < -0.985` 是错的**（会漏掉一半搭接：两端点类型相同时才是 -1，
类型相反时是 +1）。NEW_CAB 第一次扫描就栽在这里：L762（dot=+1）和气腔
底边一族全部漏掉，用户一眼看出"水滴源头跑拉带里去了"。

**桥接候选线** = A 类线，其**两端**都平滑搭接到 B 类线 → 极可能是 B 的环碎片
误分进 A。NEW_CAB 实测找出 12 条（见 references/04_case_newcab_2026.md §修正清单）。

端点焊接容差：距离 < 8mm（NEW_CAB 实测 IGS 断点最大 ~7mm）。

---

## 5. 分类修正的判据顺序（先几何后视觉）

1. **环闭合优先**：与某环切线连续且端点 0 缝隙搭接 → 归该环
   （气腔底边三段 L130/L95/L93 全在 y=−152.554 直线上，就这么找回的）
2. **缺口补段**：环上 <25mm 的缺口，若某游离线正好搭接两端 → 归该环
   （L762 补布带右缘 20.22mm 缺口）
3. **区域规则**：仍在 TETHER 的碎片按位置判（顶部凸台区/左革眼区/右补丁区）
4. **渲染复核**：每版必出图，**人看图确认**才进下一步
5. **闭环 QA**：CAVITY 应 1 个主组分（仅图纸固有缺口有悬挂端）；
   SEAM 各哑铃 0 悬挂端；BELT 主环外允许充气口小区；
   **TETHER 天然多片**（凸台/革眼/补丁各自成片），单连通不是目标

**图纸固有的"不闭环"不要硬凑**：NEW_CAB 气腔顶边在充气口根部有 410mm 缺口
（x 478→888），这是图纸本身的设计（充气口与气腔共边界），补它属于歪曲几何。

**终检报告 `p07_report.py` 必看三件事**（v14 新增，通用无硬编码）：
① 小分量（<30mm，疑符号残留，如三个小圆圈）逐个确认是否移出；
② 主环自由端是否为设计允许的开口；③ 组内重复线对（退化微段强判据）。

---

## 6. 坑位（动手前扫一遍）

| # | 坑 | 对策 |
|---|---|---|
| P35 | `*movemark` 第三参是 comp **名称**不是 id；`*writefile` 目标已存在 → Overwrite? 弹窗 = 不可 catch FatalError | 直接 `*createentity comps name=X` 新建 4 个 comp 再搬；写盘前 `file delete -force` |
| P36 | 切线判据只查 `dot<−0.985` 会漏一半搭接 | 按 §4 的端点类型配对判据 |
| P37 | IGS 圆圈是**多段弧**拼的，端点追踪看像 V/方头 | 查折线点曲率/三点圆拟合（t01 的 CIRC 记录）再判 |
| P38 | 校验不能只比条数 | 用 `by collector name` 拿回 id 集合与分类真值**逐 id 比**；回读重算 bbox + 抽样线长 |
| P39 | `*readfile` 目标不存在 → hmbatch 整体中止、报告不生成，看旧报告会误判成功 | 跑前确认输入存在；跑后检查报告 mtime + exit code |
| P40 | ~~hmbatch `-tcl` 中文路径必挂~~ —— **作废**，2026.0.0.27 实测可正常 source | 直接 `-tcl` 中文路径；定位错误先看错误栈 |
| P41 | Tcl 字符串里 `[` `]` 是命令替换；`puts` 不格式化 | 格式化串走 `format`，方括号改用 `..` |
| P42 | 坐标平面可能是 **X-Y** 不是 X-Z | 导出必须带三轴，先看 z 是否恒 0 再定 2D 平面 |
| P43 | v9 修正必须用**规范 v8 种子**（119/78/59/572），误用变体会审计对不上 | delta 脚本默认源已钉死，`*_SRC` 可覆盖 |
| P44 | delta 脚本对已生成结果重跑 → DROP 的 id 已不在 C → `KeyError` | 列表加 `if lid in C` 保护 + 只读稳定 v8 源（幂等） |
| P45 | v9 起刻意留未参与分区的线在 `lines0`，t08 原 `TOTAL` 假设误报 | t08 已加 `UNASSIGNED={lines0,DROPPED}` 跳过 |
| P46 | 气腔环在充气口**不做往回折闭合**：口部形态=气腔两条上行线沿领圈内侧平行爬到楔顶封闭端停止，右支开口 | 见 §7.9/v13 最终形态 |
| P47 | **白线≠垃圾**：未归档线里端点连续、两端接已分类环的**连续链是真实边界**；只有平行重复线才该 DROP | DROP 前先跑端点搭接连通性扫描；0.29~1.0mm 图纸微缝留给建面/共节点阶段桥接 |
| P48 | **只加用户指的那一根线，勿整链带回**（v11 过度修复倒退） | 改动量以用户指认的线数为准；先渲染同视角对比图逐位吻合 |
| P49 | **t08 漏设 WORKDIR = 读旧报告假 PASS**（v13 首次校验实栽：读到 v12 旧计数 36/84） | 跑 t08 前 `rm -f out/verify_partitioned.txt`；跑后核对 COUNT 与 p06 输出一致 |
| P50 | 端口白线里有**零长度退化线**（L171 len=0） | 追链/分类前过滤 len<0.01mm |
| P51 | 充气口是**近重合线团**，2mm 容差追链会拐进旁支直通错线 L161 | 锁链权威判据=**精确端点衔接（0.00mm 级）+ 编号连续** |
| P52 | QA 严格 0.05mm 容差会把 0.06mm/0.23mm 真实衔接判成开环 | 读 QA 先查断点距离量级，<0.3mm 的"断开"是容差边界效应 |
| P53 | **delta 脚本 `*_SRC` 传裸文件名会 `FileNotFoundError`**（原本按绝对路径 `open`） | 已修：非绝对路径自动拼 `BASE`（`out/`）。传绝对路径或裸名都行 |
| P54 | `set -euo pipefail` 下 `p07_report.py \| head` 触发 SIGPIPE 使整链失败（exit 120） | 报告写文件后 `grep` 回显摘要，不管道截断 |
| P55 | **TETHER 天然多组分**（v14 TETHER 111 个组分），"主环"标签在拉带上无意义 | 拉带按片验收（凸台/革眼/补丁各成片），只看小分量与重复线 |

---

## 7. NEW_CAB 交付态（端到端回归通过，2026-10-21）

输入 `E:/work/AI_CAB/onekey/work/input_newcab/newcab.iges`（828 线，1 comp）
→ **v14 `partitioned.hm`**：

| comp | 线数 | bbox (mm) | 内容 |
|---|---|---|---|
| BELT | 34 | x[−365.2,1620.2] y[−167.0,497.4] | 外环 + 充气口领圈 + 顶边封口分段 |
| CAVITY | 89 | x[−350.7,1579.3] y[−152.6,497.4] | 气腔主环（含水滴）+ 口部右链 + 封口段 L188/L196 |
| SEAM | 43 | x[137.4,1460.3] y[−40.0,250.0] | 4 条哑铃缝 |
| TETHER | 555 | x[−315.9,1771.3] y[156,456] | 7 凸台 + 2 革眼 + 右梯带 + 右补丁（多片） |
| lines0 | 107 | — | 不参与分区（含三个小圆圈 12 条、重复壁、折叠线等） |

**端到端回归证据**（2026-10-21 19:15，全新工作区 `work/newcab_test`）：
`IGES → t00(828 线/1 comp) → t01 → t02 → SEED v8 → DELTA=v14 → p05/p07 → p06 → t07(ALL_OK=1)
→ t08(COUNT 全 OK、TOTAL 721、VERIFY_FAIL=0)` —— 与既有 `work/newcab` 结果逐位一致。

### 版本链（每版 = 上一版 + delta，delta 脚本均从规范 v8 种子幂等累积）

| 版本 | 变更 | 计数 (B/C/S/T) |
|---|---|---|
| v8 | 初版四分区（种子分类） | 119 / 78 / 59 / 572 |
| v9 | 极简轮廓修正（只留建面闭环边界子集，风格参考 cab1.hm） | 36 / 92 / 43 / 567 |
| v10 | 气腔口部开环（移除气道回路 9 线） | 36 / 83 / 43 / 567 |
| v11 | ~~白链整链回归~~ **过度修复，被推翻**（教训 P47/P48） | 36 / 92 / 43 / 567 |
| v12 | v10 + 仅加 L161（**后被 v13 推翻**：L161 是左边错加的死线） | 36 / 84 / 43 / 567 |
| v13 | 移除 L161 + 右侧编号顺滑链 L168-170-172 + 封口段 L188/L196 并入气腔 | 34 / 89 / 43 / 567 |
| **v14** | **剔除气腔内三个小圆圈（12 条 → lines0）** | **34 / 89 / 43 / 555** |

### 7.5 v9 极简轮廓修正（2026-10-21 下午）

分区曲线只为最终计算模型服务，是裁切建面 / Surface Edge 的**闭环边界轮廓子集**；
不必要的细小 Curve、特征装饰、内部折叠线不放进来。风格参考
`E:\work\AI_CAB\气帘CAD数据\cab1.hm`（最少量外轮廓环；口部布带环与气腔环对应、靠内平行）。
脚本 `v9_apply_fix.py` + 诊断 `v9_recon*.py` / `v9_render.py`；
完整清单见 `references/05_v9_minimal_contour.md`。

### 7.6 v10 气腔口部开环（2026-10-21 15:22）

气腔环在充气口**不往回折闭合**，跟布带环相约在最上面那个斜线段上；
L471/L166 沿领圈内侧平行爬到楔顶 (834.89,497.37) 停止，右支开口。
网格意义：充气口处全是气腔面区域，与布带层自然过渡。见 `references/06`。

### 7.7 v11（教训）、7.8 v12（教训）

- v11 整链回归 = 过度修复（用户："你又倒退了啊，刚才那一步只差一根线了"）→ P48
- v12 只加 L161，但加在**左边**（平行死线）→ 用户："右边（X 大）那一侧应该连通上面的封口段，你在左边弄了两根" → v13

### 7.9 v13 气腔封口链闭合 + **顺滑追链方法论**（用户明示沉淀）

用户："从 167 编号下面就是 168、169，一直到 172，这根线不就慢慢通上去了吗？……
**下次你要把这个作为一个技能啊，要会这么寻找啊，就沿着它顺滑的方向去寻找啊。**"

- v13 = v12 + delta：`CAVITY -= {161}`；`CAVITY += {168,169,170,172}`（实测端点
  0.00/0.00/0.00/0.06mm 衔接）；`CAVITY += {188,196}`（封口段，原 BELT，方便网格切割）
- 气腔环闭合路径：L168→L167→外层大弧→L134→L471→L166→楔顶→L196→L188→(13mm 图纸缝)→L172→L170→L169→L168
- 工具 `scripts/chain_trace.py`：种子两端都接线时优先走「邻居线号=seed+1」方向；
  之后按 **方向连续 0.6 + 偏好方向 0.2 + 编号接近 0.2** 三因子打分
- 详见 `references/09_v13_seal_chain_and_chain_trace.md`

### 7.10 v14 剔除气腔内三个小圆圈（**当前交付态**，2026-10-21 19:01）

- 三者为 **~6.1mm 退化重复微段**（bbox 2.8×5.3mm）：A=L229+L230 @(580.1,260.3)；
  B=L231/232/235/236/239/240/243/244 @(894.1,263.6)；C=L247+L248 @(878.3,320.7)
- 识别：归档类端点融合 union-find → 小 bbox 分量过滤 → 「集合内互为重复线」= 符号残留强判据
- v14 = v13 + delta：`TETHER -= 12 条`；脚本 `v14_remove_tiny_circles.py`
- **流程强化（用户明示）**：标注截图 → 带坐标确认图 → 逐位吻合 → 幂等 delta →
  p06→t07→t08 → 结果渲染图（被移除元素醒目虚线保留显示供核对）
- 详见 `references/10_v14_remove_tiny_circles.md`

---

## 8. 换项目 Playbook（新图纸 checklist）

1. **建工作区**（英文路径）：`mkdir -p <WORKDIR>/out`
2. **S0 导入**：`IGES=<图纸> WORKDIR=<WORKDIR> hmbatch -tcl t00_import_iges.tcl`
   → 确认报告里 `comps 1`（多 comp 说明图纸自带结构，可省本技能）
3. **S1/S2 导出**：确认坐标平面（P42，z 恒 0 则按 X-Y 处理）
4. **S3 种子分类**：按 §2 判据初分，可先跑 `p03_bridge_scan.py` 找跨类桥接候选；
   **渲染图人眼确认**后才写成 `out/<SEED>.json`
5. **S4 修正**：新项目先用 `DELTA=none`（直接采用种子）；用户每反馈一版，
   写一个**幂等 delta 脚本**（从种子累积，禁止就地改产物）——照 `v14_*.py` 模板
6. **S5 终检**：`p07_report.py` 看小分量/自由端/重复线；出图给用户目检
7. **S6–S8 落地**：p06 → t07（需 `ALL_OK=1`）→ t08（需 `VERIFY_FAIL=0`）；
   跑 t08 前必 `rm` 旧报告（P49）
8. **交付**：`partitioned.hm` + `out/verify_partitioned.txt` + 渲染图；
   把本轮 delta 与坑位写进 `references/` 与 `CHANGELOG.md`

### 硬性 checklist

- [ ] 坐标平面确认（XY 还是 XZ，P42）
- [ ] 导入后 comp 结构确认（1 个 comp 才需要本技能）
- [ ] 种子分类 → bridge_scan → **渲染人眼确认** → 才落 FIX
- [ ] 端点容差 8mm；切线判据按 P36
- [ ] 充气口/水滴/共边界逐一在图上确认，不硬凑闭环
- [ ] 缝线端头查曲率，别把弧端当 V/方头（P37）
- [ ] 搬线 `*movemark lines 1 <comp名>`；写盘前 `file delete`（P35）
- [ ] 校验逐 id 比 + 回读 bbox/线长（P38）；查报告 mtime 防旧报告误判（P39）
- [ ] delta 脚本幂等、从种子累积（P43/P44/P53）
- [ ] 每版出图，用户目检通过才落地（§2 交互铁律）

---

## 9. HyperWorks 2026 批处理铁律（Tcl 通用）

1. **Tcl 开头必须加载用户模板**：
   `hm_framework loaduserprofile LsDyna Keyword971_R16.0`
   （2020 不用；2026 漏了报 `No user profile or template file loaded` /
   `data-name "pid" is not valid`）。只写 `LsDyna`（不带模板文件）无效。
2. **`*writefile` 前必须 `file delete -force` 目标文件**（P35），否则 Overwrite? 交互
   在批处理里是不可 catch 的 FatalError。
3. **所有 Tcl/Python 只认 `WORKDIR`（+ 可选 `HM_IN`/`HM_OUT`/`*_SRC`）环境变量**，
   换项目不改脚本（P49）。
4. **hmbatch 导入只有 1 个 comp**：`*geomimport "iges_altair" <file>`（失败退回 `*import`）；
   组件结构靠本技能的 Python 聚类恢复。
5. **hmbatch 建不了元素**（`*createentity elems` 无效），建元素是网格化阶段
   （hypermesh2026_CURVEtoMESH_skill）的事，本技能只搬运曲线、不动几何。

---

## 10. 目录

```
SKILL.md                  本文件（入口：端到端链路 + 判据 + 坑位 + 换项目 playbook）
CHANGELOG.md              版本记录
config.json               配置
assets/                   交付态渲染图 / 报告样例
cases/                    ★端到端验收快照（冻结证据，勿改）：v2_cab1/ v2_cab2/ v2_cab3/
  README.md               三图验收表 + 每目录文件说明 + 复现命令 + 可复现性证据
  v2_<name>/              partitioned.hm + classify_final.json + render_v2.png +
                          render_golden.png + verify_partitioned.txt + 建 comp/导入报告
golden/                   ★金标准库（监督样本：标签+特征+源图纸+出处，技能自包含重训的唯一数据源）
  README.md               金标准总览 + 布局 + 重训流程 + 新增金标准五步法
  cab1/                   5P-BAG 侧视（314 分类）
  cab2/                   NEW_CAB 8P（组件 L1~L4 + lines0，696 分类）★v2 新增
  cab3/                   6P（802 分类）
    ↑ 每个目录统一含 7 件：
      source.iges          原始图纸          <name>.hm       人工分区结果
      golden_line_comp.json 金标签          features2.json  v2 特征（32 维，存档）
      comp_lines.json      comp→线 id（解构原始证据）
      comp_agg.json        组件几何聚合表（定映射时的判据）
      golden_panels.png    逐组件面板图（视觉定案用）
      lines_pts.txt        采样点 → 可离线重算特征，不依赖 HyperMesh
      source.txt           出处 + 映射 + 依据 + 纠错记录
  newcab/                 【留档】NEW_CAB 早期 v14 标注（与 cab2 同一张图，已被 cab2 的人工版取代，不进 v2 训练）
references/
  01_partition_rules.md       四分区判据细则
  02_tangent_continuity.md    切线搭接判据（P36）
  03_hm2026_geometry_queries.md  HM2026 几何查询 API
  04_case_newcab_2026.md       NEW_CAB v8 初版案例全过程
  05_v9_minimal_contour.md     v9 极简轮廓
  06_v10_cavity_open_port.md   v10 气腔口部开环
  07_v11_cavity_port_chain.md  v11 教训（过度修复）
  08_v12_add_l161.md           v12 教训（加错边）
  09_v13_seal_chain_and_chain_trace.md  v13 封口链 + 顺滑追链方法论
  10_v14_remove_tiny_circles.md          v14 小圆圈剔除 + 图像反馈流程
scripts/
  run_full.sh               ★端到端一键链（S0–S8）
  t00_import_iges.tcl       S0 原始 CAD 导入
  t01_export_geom.tcl       S1 几何特征   t02_export_pts.tcl  S2 采样点
  p03_bridge_scan.py        S3 切线搭接扫描   p03b_trace_chain.py 单链追踪
  v9_apply_fix.py ... v14_remove_tiny_circles.py   S4 各版 delta（幂等累积）
  chain_trace.py            顺滑追链工具
  p05_render_partition.py   S5 渲染   p07_report.py ★终检报告（通用）
  p06_export_class_lists.py S6 导出
  t07_make_comps.tcl        S7 建 comp  t08_verify_partitioned.tcl S8 校验
  q09_seam_check.py / q10_region_connect.py / v9_recon*.py / v13_render.py  辅助
  # —— 全自动模式 v2（2026-10-31，当前推荐；见 §0.5）——
  featurize2.py             ★特征 v2：轮廓内向深度 / 切向链 / 局部密集度 / 图内百分位
  train_v2.py               ★两阶段森林 + LODO 交叉验证报告 → tree_model_v2.json
  tree_model_v2.json        ★v2 先验（两阶段森林 + SEAM 规则，纯 Python 可推理）
  auto_partition2.py        ★v2 自动四分类（纯 Python 推理 → classify_final.json）
  run_auto2.sh              ★v2 端到端一键链（S0→S2→AUTO2→p06→t07→t08）
  t09_dump_comps.tcl        ★[组件 → 线 id] 导出 JSON（解构新金标准必用）
  ga_analyze_comps.py       金标准组件分析：几何聚合表 + 逐组件高亮渲染
  ga_build_golden.py        comp_lines.json + 映射表 → golden_line_comp.json
  eval_vs_golden.py         ★逐线比对预测 vs 金标准（校验 id 空间 / 报结构互换 / 规则命中）
  rebuild_from_golden.py    ★自包含校验：只用 golden/ 离线重算特征并与存档比对
  sync_to_install.sh        ★把本目录同步到 ~/.workbuddy/skills/qilan-iges-partition（自动备份）
  cv_lodo.py                留一图交叉验证（v1 特征版，留档对照）
  # —— 全自动模式 v1（2026-10-23，已被 v2 取代，仅留档；见 §0.5b）——
  featurize.py              v1 通用特征提取（含绝对位置/凸包距离，LODO 差）
  feat_driver.py            <工作区> → out/features.json
  auto_partition.py         v1 自动四分类（加载 tree_model.json → classify_final.json）
  train.py                  单金标准(newcab)训练；train_joint.py 多金标准联合训练
  train_joint.py            多金标准(newcab+cab1+cab3)联合拟合 → tree_model_joint.json
  tree_model.json           v1 先验（三金标准联合决策树，269 节点）
  tree_model_v1_newcab.json 备份：单金标准(newcab-only)先验
  tree_model_v2_joint_cab1.json 备份：双金标准(newcab+cab1)先验
  tree_model_joint.json     联合先验中间产物（验证无回退后覆盖 tree_model.json）
  render_auto_partition.py  按 classify JSON 渲染分区图（自动判平面，v1/v2 通用）
  run_auto.sh               v1 端到端一键链
  delta_belt_envelope.py    【诊断实验，未接入】"最外整圈→BELT"候选规则，已证实不可靠（见 §0.5b）
```
