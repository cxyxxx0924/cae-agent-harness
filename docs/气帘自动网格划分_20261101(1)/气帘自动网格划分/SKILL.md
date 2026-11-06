---
name: curtain-airbag-auto-meshing
description: 气帘（curtain airbag）自动网格划分全链路技能——从 CAD 曲线分区（布带/气腔/缝线/拉带四分区）到 HyperMesh 2026 裁切拓扑三面网格（界面天然共节点）、Y 分层组装、拉带节点捏合、充气口封口，到 LS-DYNA K 导出与 auto_gate 自动校验套件（拓扑/分层/环面积/节点路程/逐环几何匹配/拉带连接，零第三方依赖、纯 Python SVG 自出图、门禁规则可持续迭代）。当用户要"气帘网格划分/自动网格/多环共节点/网格边界贴合 CAD 曲线/拉带连接/hmbatch 2026/读 K 卡死/全自动无人值守网格流水线/训练通用网格技能"时使用。沉淀自 cab1/cab3/NEW_CAB 三案实战，案例无关（换项目只改 cases/ 配置与 gate_rules.json），全链路见 references/08_full_pipeline.md，无人值守链见 references/11_cab3_auto_pipeline.md，校验套件见 references/12_auto_gate.md；**气腔 washer 边界层 + 拉带凸台栅格并集 + 侧面拉带（穿布带端面缺口）**见 references/13_washer_and_tether_union.md（`scripts/stage3_mesh/add_washer.py`、`scripts/stage2_partition/tether_union.py`、`tether_side_outline.py`、`gen_side_tab.py`）；**washer 新做法（首选）**：划网格阶段用 `*blmesh_2d2` 一次成型，见 references/14_blmesh2d_washer_preroll.md；**通用质量口径**（要方正四边不要全四边、`element_type: mixed`、拉带连接三性质）见 references/15_mesh_quality_and_tether_connection.md；**换案例不改脚本**（`case.json` 驱动 + `chain_loops.py` 自动成环替代手抄 line id）见 references/16_generic_pipeline.md；**拉带锚固边受布带约束（三刀切，锚固排 5.000mm 等距共节点）**见 references/18_tether_anchor_three_cut.md（`scripts/stage3_mesh/plan_anchors.py` + `gen_tabs_anchored.py`）。**接新气帘先读 references/00_RUNBOOK_接新气帘.md**（端到端 runbook：每步命令/验收数字/失败分支）；坑位全集 P1–P60 见 references/04_pitfalls.md；未闭环清单见 references/19_open_issues.md；数字台账与回归基线见 references/20_baselines.md + assets/baselines.json。
agent_created: true
---

# 气帘自动网格划分（分区 → 网格 → 校验 全链路）

> **本目录是全链路的唯一维护点**：从客户 CAD 曲线到过门禁的 LS-DYNA K，
> 含分区归类、裁切拓扑网格、Y 分层组装、拉带捏合、充气口封口、自动校验。
> 项目里只放输入/输出，不要在具体项目里另写一份流程脚本。
>
> **设计定位（训练目标）**：案例无关、全自动无人值守、门禁可持续迭代、自己出图审查。
> 换任何一个新气帘几何，只改 `cases/<案例>/gate_case.json` + 少数项目几何参数，
> 流水线脚本与门禁规则原样复用。

**版本基线**：HyperWorks **2026.0.0.27**（`D:\Program Files\Altair\2026`，不带 hwsolvers；
OptiStruct/Radioss 求解器在 2020 版）。交付链锁死一个 HM 版本（2026 与 2020 网格结果不等价，P4）。

---

## 0. 先读这三份（工作流入口）

> **新来一个气帘项目？不要从头读这个文件，按下面三份走。**

| 什么时候读 | 读哪份 |
|---|---|
| **要接一个新气帘、要跑完整条链** | `references/00_RUNBOOK_接新气帘.md` ← **主入口**：0 准备 → 7 阶段，每步命令/验收数字/失败分支/该查哪条坑 |
| **出问题了，或动手前想避雷** | `references/04_pitfalls.md`（P1–**P60**） |
| **这一版对不对 / 该不该交** | `references/20_baselines.md`（数字台账）+ `assets/baselines.json`（机器可读） |
| **现在还有哪些没解决** | `references/19_open_issues.md`（未闭环登记册，含"已判定不做"清单） |

**一条命令跑完（案例参数全在 case.json）**：
```bash
bash scripts/drivers/run_case.sh --case cases/<案例>/case.json --work /path/to/<案例>
```
退出码 0 = 可交付；任何 `die` = 不要交付（尤其是 ⑦d 分区覆盖 FAIL，代表有整块丢失）。

> **本技能的三条设计原则**（都踩过坑才定下来）：
> 1. **案例知识只进 `cases/<案例>/case.json`**，脚本零案例硬编码；
> 2. **缺件必须硬失败**，不许静默降级（P48：整块丢侧拉带，五项门禁全 PASS）；
> 3. **改脚本必须 MD5 回归**（P60：看起来等价的重构丢了 `trim_chain()`，间距 5.00→4.73 无任何报警）。

---


## 1. 何时用 / 何时不用

**用**：
- 气帘类 2D 展开图（也可用于钣金展开/垫片/密封条等多环嵌套平面几何）
- 曲线按 component 分组，要求**多环嵌套界面共节点**、**边界严格贴合各环 CAD 曲线**
- 要全自动无人值守流水线，或要交互式逐环操作并目检（MCP live bridge）
- 要导出 LS-DYNA `.k` 并带**可迭代门禁 + 自出图审查**

**不用**：
- 几何已是干净封闭曲面 → 直接 automesh，无需裁切拓扑
- 需要求解 → 本技能不含求解器

---

## 2. 环境与两条通道

| | hmbatch 批处理 | MCP live bridge 交互 |
|---|---|---|
| 形态 | 无 GUI，一条 Tcl 跑到底 | HyperMesh GUI + Bridge 扩展 |
| 用途 | **交付链主用**（确定性、可复现） | 探查、目检、试参数 |
| 入口 | `hmbatch.exe -tcl x.tcl` | `mcp__hyperworks__*` 工具 |
| 前提 | **先加载用户模板**（P2） | GUI 启动 + 扩展开关 + 建 project |

2026 hmbatch 铁律（每条都踩过）：
```tcl
hm_framework loaduserprofile LsDyna Keyword971_R16.0   # ① 开头必须先加载模板
*createmark elems 1 "all" ; llength [hm_getmark elems 1]  # ② 无 hm_entitycount
*elementorder 1 ; *setedgedensitylinkwithaspectratio -1   # ④ automesh 前必设（readfile 之后）
*interactiveremeshsurf 1 $sz 2 2 2 1 1 ; *automesh 0 2 2 ; *storemeshtodatabase 1
```
MCP 配置/live bridge 详见 `references/01_mcp_connection.md`，批处理命令签名速查见 `references/02_hw2026_batch.md`。

---

## 3. 目录结构（按流水线阶段分层）

```
气帘自动网格划分/
├── SKILL.md / CHANGELOG.md / config.json     入口 / 迭代记录 / 环境事实
├── cases/                    ★换项目只动这里
│   ├── README.md              案例配置写法
│   └── <案例>/
│       ├── case.json          ★该案例的全部参数（layers/parts/mesh/assemble/gates）
│       └── gate_case_vN.json  auto_gate 校验案例（可保留多个历史基线）
├── assets/
│   └── baselines.json        ★机器可读回归基线（各案例关键数字，见 references/20）
├── references/               知识沉淀（按需加载，见 §10 索引）
│   ├── 00_RUNBOOK_接新气帘.md  ★★主入口：接新案例的端到端 runbook
│   ├── 04_pitfalls.md         坑位 P1–P60 ★动手前扫一遍
│   ├── 19_open_issues.md      ★未闭环登记册（含"已判定不做"清单）
│   ├── 20_baselines.md        ★数字台账（这一版对不对看这里）
│   ├── 08_full_pipeline.md    全链路：每阶段命令/输出/预期数字/失败分支
│   ├── 09_partition_classify.md 四分区归类 + component 落地
│   ├── 03_trim_topology.md    裁切拓扑（多环共节点的标准解）
│   ├── 07_tab_tether_meshing.md 拉带网格 + 节点捏合
│   └── 12_auto_gate.md        自动校验套件方法论
└── scripts/
    ├── stage0_import/        ① IGS/STEP → .hm（import_igs_2026.tcl / smoke_2026.tcl）
    ├── stage1_survey/        ② 调查：组件清单+spline面积（定 PID 依据）+ 线点云 + 底图
    ├── stage2_partition/     ③ 分区：切线搭接扫描/分类修正/建 comp/回读校验/环定义生成
    ├── stage3_mesh/          ④ 网格：裁切拓扑三面 + 拉带区域提取 + 拉带建面网格
    │                         ⑥b 锚固：plan_anchors.py → gen_tabs_anchored.py（三刀切）
    ├── stage4_assemble/      ⑤⑥ 组装：Y 分层写 K + 拉带捏合 + 充气口封口 + 格式修复
    ├── gate/                 ⑦ 门禁：拓扑 QA / 长边 / 端口 / 末端 + 几何匹配 + 拉带连接
    │   ├── auto_gate/        ★统一自动校验套件（零依赖/自出图/规则可迭代）
    │   ├── mesh_quality_gate.py      质量门禁（碰撞口径，退出码 0/2）
    │   └── partition_cover_check.py  ★分区覆盖（防整块丢，退出码 0/1/2）
    ├── render/               渲染：三面网格/左拉带连接/修复前后对比/拉带组分色块图
    └── drivers/
        ├── run_case.sh       ★★首选：case.json 驱动全链（含 ⑥b 锚固 + ⑦c/⑦d 门禁）
        ├── run_pipeline.sh   旧驱动（案例参数散在脚本里，仅维护兼容）
        └── cab3_auto/        无人值守一键链（S0-S8，门禁驱动网格尺寸自动调优）
```

**WORKDIR 约定**：所有脚本认环境变量 `WORKDIR` = 项目工作目录（含 `input/` 与 `out/`），
缺省当前目录。**路径必须全英文**（中文路径 hmbatch `-tcl` 必挂，P6）。

---

## 4. 全链路工作流（7 阶段）

> 每阶段命令/输入输出/预期数字/失败分支见 `references/08_full_pipeline.md`。
> **一键复现**（换项目只改环境变量）：
> ```bash
> WORKDIR=/path/to/proj bash scripts/drivers/run_pipeline.sh            # 全链
> SKIP_IMPORT=1 GATE_ONLY=1 GATE_CASE=cases/<案例>/gate_case.json \
>   WORKDIR=/path/to/proj bash scripts/drivers/run_pipeline.sh          # 只跑门禁+校验
> ```
>
> **★ 换案例不改脚本（推荐，cab2 验证 MD5 等价）**：全部案例参数进一份 `case.json`，
> 缝线环由 `chain_loops.py` 自动成环，不再手抄 line id。
> ```bash
> bash scripts/drivers/run_case.sh --case cases/<案例>/case.json --work /path/to/proj
> # 接新案例先干跑看缝线环对不对：
> python scripts/drivers/gen_step1_tcl.py --case cases/X/case.json --loops out/loops.json --out out/s.tcl --dry-run
> ```
> 详见 `references/16_generic_pipeline.md`。

```
① 导入      stage0_import/import_igs_2026.tcl     CAD → .hm（已有干净 .hm 可跳）
② 调查      stage1_survey/survey_comps.tcl        组件清单+spline面积 → 定 PID（P28：别信 comp 名字，以面积为准）
            stage1_survey/export_lines_pts.tcl    线点云 → 渲染底图 + 环几何基准
            stage1_survey/export_tabs.tcl         拉带线点云
③ 分区      stage2_partition/（bridge_scan 搭接扫描 → classify 修正 → make_comps 落地 → verify 回读）
            stage3_mesh/tabs_extract.py           拉带 9 区域多边形（聚类→焊接→环提取→boss 分片→simplify）
④ 三面网格  stage3_mesh/build_step1_2026.tcl      裁切拓扑：缝面用"洞内面"（P12），界面共节点由拓扑保证
            stage4_assemble/assemble_step1_2026.py Y 分层写 K（PID2 布带 Y0 / PID3 气腔 Y±0.5 / PID4 缝线 Y0）
⑤ 拉带      stage3_mesh/gen_tabs_tcl.py → build_tabs_2026.tcl → assemble_tabs.py（Y-1 + 捏合 PID2）
            ★ 首选：stage3_mesh/plan_anchors.py → gen_tabs_anchored.py（锚固边受布带约束，三刀切）
⑥ 充气口    stage4_assemble/assemble_port.py      上下唇捏合到 Y0（幂等）
⑦ 门禁      gate/qa_kfile_strict.py 等 + gate/auto_gate/run_gate.py（§6）
```

**Y 分层约定**（用户规范）：布带 = Y0 单层；气腔 = Y±0.5 双层（界面收 Y0）；
缝线 = Y0 单层；拉带 = Y-1（与布带连接处爬坡到 Y0 共节点）。

**cab3 类无人值守链**（全自动、门禁驱动网格尺寸自动调优）：
```bash
WORKDIR=./cab3 REFDIR=./ref MESH_START=5.0 MESH_MIN=2.0 bash scripts/drivers/cab3_auto/run_cab3.sh
```
退出码即交付许可（0=ALL PASS）。详见 `references/11_cab3_auto_pipeline.md`。

---

## 5. 核心方法速查

### 5.1 裁切拓扑（多环共节点的标准解）
一套面切出所有分区，界面由 HM 拓扑保证共节点——**不是**各自建面再投影缝合（P17）：
```
内环 spline 建面(缝面) → 取边线 → 外轮廓建面(BLUE) → BLUE 裁 L3 线 = CAV+BELT
→ CAV 裁 5 缝面边线 = CAV(带洞) + 洞内面×5 → automesh 先小后大 → equivalence2 节点零变化
```
**缝面必须用裁出的"洞内面"**，沿用 spline 面会共节点 0（P12）。

### 5.2 拉带连接铁律（参考模型实证）
- 只并到**单层布带 PID2**，绝不并气腔/缝线（P21）；靠**直接节点捏合**，不是 CNRB（P22）
- **全局 1-to-1 贪心**匹配（零退化丢单元，P24）；节点集去重剔零厚度伪单元（P23）
- 合并目标 id 必须**读 K 本身**（导出 txt 的 nid ≠ K gid，否则飞丝，P29）
- 只连**一条边**不整面重叠（凸台=顶帽水平边 EDGE_BAND 8mm；左长条=末端竖边 END_BAND 3mm，P30）
- **拉带∩气腔共节点若同时属布带且 Y0 = 良性界面节点**（参考模型明确允许，非误连——auto_gate 已按此口径豁免）

### 5.2.1 锚固排必须是「布带的节点相位」（★ cab2 v4 定版做法）

**不要先划拉带再吸附过去**——横向错位最多一整格 5mm，输的那个节点留在 Z=−1 拉出 60~78° 扭转片
（v3 实测翘曲 max 165.7°、最小角 p1 = 0°）。正解是让拉带的网格线**穿过布带的锚固点**：

```
plan_anchors.py   布带自由边(− 气腔界面) ∩ 拉带真实轮廓环 → anchors.json（8 链 / 64 点）
gen_tabs_anchored.py   逐块「建面 → 三刀切 → automesh」
  三刀 = 过链两端沿法向各一刀 + 沿链方向过锚固线一刀（★线必须贯穿面，面内短线报错）
  中间块宽度 = 锚固段长度（被 5mm 整除）→ 间距 5.000mm、偏差 0.000mm
assemble  TAB_TOL=0.35 SNAP_INSIDE_TOL=0   → 吸附位移 3.00mm → 0.26mm
```

验收：`tab_anchor_stat.py`（宽度 5.00/错位 σ 0.00）+ `anchor_metric.py`（最小角 p1 / 翘曲 / 蝴蝶结）
+ `tether_conn_check.py`（tether∩belt>0、tether∩cav=0、tether∩seam=0）+ `render_anchor_side.py`（侧视对比）。

> **方案 A「显式节点序列」已实测并否掉**：`--mode polyline|band|hybrid` 三版全部跑过，
> 锚固排宽度 4.18~5.95mm、错位 σ 0.08~0.41、翘曲 max 78~82° —— 全面输给三刀切
> （5.00mm / σ 0.03 / 33°）。原因：显式节点只定"点在哪"，定不了"配对行跟谁平行"；
> 三刀切切出的是**矩形锚固带**，属拓扑性质。详见 references/18 §10。
>
> 全部踩坑与方法见 `references/18_tether_anchor_three_cut.md`。已知极限：锚固排两端仍有
> 15~33° 翘曲（1mm 面外偏置 + 过渡排纵深仅 2mm，属几何本征）、每块两端 0.3~0.9mm 短边。

### 5.3 交付前几何门禁（拓扑 QA 查不出的必须补）
拓扑 QA 只查 eid 唯一/无退化/无自由边，**查不出几何是否贴 CAD**（NEW_CAB 出现过凸台漏编→穹顶悬空而 QA 全 PASS，P41）。因此加逐环几何匹配 + 拉带连接检查（已并入 auto_gate，§6）。

---

## 6. auto_gate 自动校验套件 ★（零依赖 / 自出图 / 规则可迭代）

```bash
# 案例校验（一条命令：5 大检查 + 6 张 SVG 审查图 + JSON/文本报告）
python scripts/gate/auto_gate/run_gate.py --case cases/cab1_clean/gate_case.json
# 换机器/换项目：WORKDIR 指向项目目录即可（case 配置里用 ${WORKDIR} 占位）
# 清杂质（孤儿节点/重复单元，幂等）
python scripts/gate/auto_gate/clean_kfile.py --in out/mesh.k --out out/mesh_clean.k
```

**五大检查**：① 拓扑（重复节点/单元/引用/孤儿/最小边/长边）② Y 分层（豁免跨角色界面节点）
③ 环面积 + 节点路程（周长，凸包口径）④ 环几何匹配（逐 CAD 线拆解 + 跨 PID 覆盖三级判定）
⑤ 拉带连接（皮带腔界面识别，豁免良性共节点）。

> ⚠️ 上述五项**都看不见"整块丢"**：cab2 曾整块丢掉侧拉带（196 单元 / 2354mm²），
> 五项全 PASS。必须再跑 **`scripts/gate/partition_cover_check.py`**：按 PID 比对面积 /
> 连通组分逐个质心匹配 / 包围盒，少一块立刻 FAIL 并报出丢失块的面积与位置。
> ```bash
> python scripts/gate/partition_cover_check.py delivered.k --write ref_manifest.json  # 建基线
> python scripts/gate/partition_cover_check.py out.k --manifest ref_manifest.json    # 每次核对
> ```
> 已接进 `run_case.sh` ⑦d（`PARTITION_MANIFEST=`），退出码 2 = 不要交付。

**反假阳性口径（套件核心价值，全部踩坑换来）**：
1. 环几何**逐 CAD 线**拆解：自有 fabric 覆盖 = 局部特征 WARN；他 PID fabric 覆盖 = 跨 PID/错标 WARN；都无 = 真缺口 FAIL。（cab1 的 BELT75 充气口领圈被气腔 fabric 覆盖，即跨 PID WARN 而非 belt 缺口）
2. 拉带∩气腔共节点**同时属布带且 Y0** = 良性界面（参考模型允许），不计误连
3. 分层检查**豁免跨角色界面节点**（拉带接布带可取 Y0）
4. 几何结论必须基于**清洗后（被引用）节点**——孤儿节点会造成"最近节点 0.4mm"假良性

**产出**：`gate_report.json` + `.txt` + `gate_figs/*.svg`（浏览器直接开）。
**退出码**：0 = PASS/WARN，1 = FAIL。详细方法论/门限含义/迭代方法见
`references/12_auto_gate.md` 与 `scripts/gate/auto_gate/README.md`。

---

## 7. 案例无关与持续训练机制（本技能的沉淀方式）

技能价值不在 cab1 这一个网格，而在**可复用的流程 + 可迭代的门禁**。训练循环：

```
新案例 → 复制 cases/<案例>/gate_case.json 改字段 → 跑流水线 → auto_gate 出报告+图
      → 不过则定位：是网格问题（回 §4 修）还是门限/口径问题（改 gate_rules.json）
      → 改 gate_rules.json 的 _changelog 记一行（日期/案例/教训/改动）
      → 回归旧案例（cases/ 下全部跑一遍，确认不回退）→ 完成一次迭代
```

- **案例差异**只进 `cases/<案例>/case.json`（PID 方案/Y 分层/`parts`/组装参数/门禁基线路径），脚本零案例硬编码；
- **门限与口径**只进 `scripts/gate/auto_gate/gate_rules.json`（带 `_changelog` 的活文档）；
- **方法论与坑位**只进 `references/`（每加一条坑位 = 一次 P 编号追加）；
- **没解决的**进 `references/19_open_issues.md`（交付报告里的"已知残留"必须有对应条目）；
- **数字**进 `references/20_baselines.md` + `assets/baselines.json`（只写实测，不写预期）；
- **HM 版本/路径/PID 语义**等环境事实进 `config.json`；
- 每次交付在 `CHANGELOG.md` 记一条（案例 + 结果 + 新增/修正的规则）。

**换项目 Checklist**（完整版见 `references/00_RUNBOOK_接新气帘.md`）：
0. 全英文 WORKDIR；1. 重跑 ② 以面积定 PID（别继承上一案例语义，P28）；
2. ③ 聚类参数按新图样调并目视复核；3. 补桥点/EDGE_BAND/END_BAND 按新模型标定；
4. ⑦ 全部门禁重跑 + **建 partition_cover 基线**（QA PASS ≠ 空间合理）；
5. 新案例登记进 `cases/`，并把数字加进 `assets/baselines.json`。

---

## 8. 两条硬规矩（用户点名，违反即返工）

1. **网格修整不准乱删**（P18）。小面积/小角度/短边一律**保留**，用"微调节点位置"修。
   只准删**真退化**（独立节点 <3）和**完全重复**单元。（auto_gate 的 clean_kfile
   只删**无任何单元引用**的孤儿节点，不碰被引用节点。）
2. **网格边界必须严格贴合各环几何曲线**。实现手段是**同源拓扑**（裁切），不是投影缝合。

---

## 9. 排查索引（症状 → 坑位）

| 症状 | 看 |
|---|---|
| HyperMesh 打开 K 卡死 | **P1（eid 漏写）** |
| `No user profile` / `data-name "pid" not valid` | P2 |
| 界面共节点 0 | P12（缝面用了 spline 面而非洞内面） |
| 边界偏离 CAD 曲线 | P17（投影缝合而非同源拓扑） |
| 网格破洞/自由边一大堆 | P18（清洗时乱删） |
| 拉带并到气腔/缝线 | P21；"以为靠 CNRB" → P22 |
| 装配后 HM 里全模型飞丝（QA 却 PASS） | **P29（目标 id 必须读 K 本身）** |
| 拓扑 QA 全 PASS 但某环几何没对上 CAD | P41 → 用 auto_gate 环几何检查 |
| 自检把 IGES 线串成蝴蝶结自交 | P42（点云凸包，不用链多边形） |
| 自检面积翻倍/边界错乱 | P43（按 PID 分层选单元） |
| 自检边界误 FAIL / 环面开口处 | P45（主判据 CAD→mesh） |
| 自检/连接脚本坐标对不上 | P47（统一 `--map xy`） |
| **整块拉带/某个分区莫名没有，但门禁全 PASS** | **P48 + 跑 `partition_cover_check.py`**（★代价最大的坑） |
| **`out/` 清空后链还能跑但结果是残的** | P49（不许用 SKIP_LINES/GATE_ONLY 拼凑） |
| 锚固排翘曲 60~80°、单元成梯形 | **P50（用了显式节点方案，必须改回三刀切）** |
| `Selected lines do not form a combined curve` | P51（切线没贯穿面） |
| 锚固间距 4.7~5.3 漂 / 两端出薄条 | P52（链端点没 trim / 外推超 0.6mm） |
| 某块拉带完全没锚点、节点被推开 3mm | P53（`WEAK_ANCHOR_MIN` 要设 1） |
| `缺主拉带网格 .../out/out/xxx.txt` | P54（STEP2 只给文件名） |
| `partition_cover_check` 报 `unrecognized arguments` | P55（要 `--k`） |
| `run_gate.py --case` 跑到一半被 SIGTERM | P55（改相对路径 + 后台） |
| Tcl 报 `can't use empty string as operand of "-"` | P56（`hm_nodevalue` 花括号） |
| 网格尺寸不受控 / 密度乱 | P57（`*elementorder` 顺序） |
| PID5 有一批 0° 单元修不掉 | P58（拉带扁平共线，属退化几何，接受） |
| 内联 Python 解析 K 崩在 `'$#'` | P59（跳过注释行） |
| **改完脚本看着没问题，交付后才发现退化** | **P60（必须 MD5 回归）** |

完整 P1–**P60** 见 `references/04_pitfalls.md`，**动手前扫一遍**。

---

## 10. 文件索引（按需加载）

| 文件 | 内容 |
|---|---|
| **`references/00_RUNBOOK_接新气帘.md`** | ★★★**主入口**：接新案例端到端 runbook，7 阶段每步「命令 → 该看到的数字 → 看不到查哪条坑」+ 交付物清单 + 该停下来问人的 5 件事 |
| **`references/19_open_issues.md`** | ★★**未闭环登记册**：几何本征（WONTFIX + 原因）/ 该做没做（A1 侧条根锚固链）/ 案例配置层 / 已判定不做（X1–X6，防重试）/ 环境层 |
| **`references/20_baselines.md`** | ★★**数字台账**：cab2 v3/v4/v8 逐项对比、cab1/cab3 基线、门限表、**口径警告**（两套锚固统计差 4 倍） |
| `assets/baselines.json` | 机器可读回归基线（单元/面积/组分/门禁/门限） |
| `references/08_full_pipeline.md` | 全链路 7 阶段：命令/输出/预期数字/失败分支/换项目 Checklist |
| `references/09_partition_classify.md` | 四分区归类（判据顺序/实测数字/Checklist）+ component 落地 |
| `references/03_trim_topology.md` | 裁切拓扑方案 ★核心 |
| `references/07_tab_tether_meshing.md` | 拉带网格 + 与布带节点捏合 ★ |
| `references/12_auto_gate.md` | auto_gate 校验套件：检查项/门限/反假阳性口径/迭代方法 |
| `references/11_cab3_auto_pipeline.md` | cab3 无人值守一键链 + 弦误差自适应判据 |
| `references/10_geom_match_and_tether_check.md` | 逐环几何匹配 + 拉带连接检查方法论 |
| `references/13_washer_and_tether_union.md` | 后置 washer 插排 + 拉带凸台栅格并集 + 侧面拉带 |
| `references/14_blmesh2d_washer_preroll.md` | ★★**首选 washer 做法**：`*blmesh_2d2` 原生 2D 边界层前置（cab2 实测带宽 4.00mm/三角 0.59%/短边降 10 倍，界面 1615 不丢），含"邻居先划、blmesh 最后"的顺序铁律；模板 `scripts/stage3_mesh/blmesh2d/cab2_step1_bl.tcl` |
| `references/15_mesh_quality_and_tether_connection.md` | ★★**通用质量口径**：要方正四边不要求全四边/`element_type: mixed`（不合格降 16 倍）+ 拉带连接三性质 + 侧面拉带重叠段 → `scripts/gate/mesh_quality_gate.py` |
| `references/16_generic_pipeline.md` | ★★**换案例不改脚本**：`case.json` 驱动全链 + `chain_loops.py` 自动成环替代手抄 line id（cab2 验证 MD5 等价）+ 泛化边界诚实清单 → `scripts/drivers/run_case.sh` |
| `references/17_tether_anchor_defect_and_fix.md` | ★**拉带锚固排畸形根因**：拉带第一排骑跨布带边界线 + 布带 3 节点挂 1 拉带节点 → 翘曲 max 165.7°；修法=用布带边界线切拉带面并设 edge density（同 SCAV/SBELT 手法），含验收判据 |
| `references/18_tether_anchor_three_cut.md`（含 §10 方案A实测否掉、§11 侧拉带与整块丢事故） | ★★**锚固边受布带约束（cab2 v4 定版）**：`plan_anchors.py` 反求锚固链 → `gen_tabs_anchored.py` 三刀切 → 5.000mm/0.000mm 等距共节点（v3 165.7°→33.0°、p1 0°→8.3°）；含端点外推阈值 0.6mm 的取舍、TAB_TOL=0.35、侧视/俯视验收图、三刀切+automesh 框架的硬极限 |
| `references/04_pitfalls.md` | 坑位 **P1–P60** ★动手前扫一遍（P48–P60 是 cab2 第二批，全部"静默失败"类） |
| `references/01/02/05/06_*.md` | MCP 接入 / 2026 批处理速查 / K 文件写法 / cab1 实战数据 |
| `scripts/gate/auto_gate/README.md` | 校验套件快速上手 |
| `cases/README.md` | 案例配置写法 + 新案例接入三步 |
