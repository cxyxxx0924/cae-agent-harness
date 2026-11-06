# CHANGELOG · hypermesh2026-curve-to-mesh

## 2026-11-01 (8) — 工作流化沉淀：RUNBOOK + 坑位 P48–P60 + 未闭环登记册 + 数字台账 + 组装硬化

> 用户要求：不要只服务 cab2 这一单，要能"持续走不通的气帘"。所以这一版不是加功能，是**把流程变成可复用的东西**。

### 新增文档（工作流主入口）
- **`references/00_RUNBOOK_接新气帘.md`（★主入口）**：接新案例端到端——0 开工前 5 项检查表 →
  7 阶段每步「命令 → 该看到的数字 → 看不到查哪条坑」→ 一次完整通过长什么样（cab2 v8 数字）
  → 换案例"哪些必须重算/哪些能继承"表 → 出问题的三分法（几何/网格/口径）→ 交付物清单 → 该停下来问人的 5 件事
- **`references/19_open_issues.md`**：未闭环登记册。分五类：几何本征（G1–G4，含 3 条 WONTFIX 及原因）/
  该做没做（A1 侧条根锚固链=A1、A2 门禁 WARN、A3 充气口口径 BLOCKED）/
  案例配置层（C1–C4）/ **已判定不做 X1–X6（防后人重试）** / 环境层（E1–E6）
- **`references/20_baselines.md` + `assets/baselines.json`**：数字台账。cab2 v3/v4/v8 逐项对比、
  cab1/cab3 基线、门限表、**口径警告**（`tab_anchor_stat` 双节点 99 vs `anchor_metric` 宽口径 135，差 4 倍；
  `mesh_quality_gate` 的 amin_p1 排除退化单元，与 `anchor_metric` 的 8.3° 不是同一总体）

### 坑位 P1–P47 → **P1–P60**（`references/04_pitfalls.md` 追加第二批）
P48 组装缺件只打 WARN → 整块拉带静默丢（五项门禁全 PASS）· P49 `out/` 清空后静默降级 ·
**P50 显式节点控制不了配对行平行（方案 A 三代实测全输，翘曲 78~82° vs 33°）** ·
P51 三刀切线必须贯穿面 · P52 锚固链 `trim_chain` / 外推阈值 0.6mm · P53 `WEAK_ANCHOR_MIN=1` ·
P54 STEP2 只给文件名 · P55 两个脚本参数形式（`--k` / 相对路径）· P56 `hm_nodevalue` 花括号 ·
P57 `*elementorder` 顺序 · P58 拉带扁平共线 66 个 0° 单元是退化几何 · P59 K 里 `$#` 注释行 ·
**P60 改技能脚本必须 MD5 回归**

### 组装/驱动硬化（行为不变，MD5 已验证）
- `assemble_cab2.py`：STEP2/STEP2B 缺省名改由 `CASE` 派生（去掉写死的 `cab2_*`）；
  新增 **`REQUIRE_PARTS`** —— 声明必需部件，缺 `side` 直接 `SystemExit`，不再只打 WARN（P48 的根治）；
  打印实际读入的 `主拉带:` / `侧面拉带:` 全路径（P49 的定位手段）
- `case_env.py`：新增 `REQUIRE_PARTS / TAB_TOL / SNAP_INSIDE_TOL / WEAK_ANCHOR_MIN / ANCHORED_TETHERS /
  EDGE_BAND / TABS_POLYS / STEP2 / STEP2B / PARTITION_MANIFEST / GATE_CASE` 输出 → **案例知识全部进 case.json**
- `run_case.sh`：⑥ / ⑥b-4 透传上述全部参数；修 ⑦d `partition_cover_check` 缺 `--k` 的 bug；
  `TABS_POLYS` / `GATE_CASE` 支持相对 WORKDIR 或相对技能根目录
- `cases/cab2/case.json`：补 `parts` / `assemble` / `gates` 三段，cab2 现在只靠 case.json 就能复现 v8
- **回归证据**：用新参数重跑组装 → `md5sum = d8e50902f4a41e8029ba87eb502f18d5`，与交付件 cab2 v8 **完全相同**

### SKILL.md
新增 §0「先读这三份（工作流入口）」+ 三条设计原则（案例知识只进 case.json / 缺件必须硬失败 / 改脚本必须 MD5 回归）；
§3 目录树补 `assets/baselines.json`、`references/00|19|20`、`gate/partition_cover_check.py`；
§7 沉淀机制补"未解决进 19、数字进 20"；§9 排查索引从 12 条扩到 24 条（含全部新坑）；§10 索引重排。

## 2026-11-01 (7) — 方案A实测否掉 + 侧拉带恢复 + 分区覆盖门禁（cab2 v8）
- **方案 A「锚固边显式节点序列」实测三版全部否掉**：`gen_tabs_anchored.py --mode {polyline|band|hybrid|triple}`
  - `triple`（三刀切）：宽度 **5.00**（7/8 块精确）/ 错位 σ **0.03** / 翘曲 max **32.97°**
  - `polyline`（沿锚固点折线一刀切）：4.36~5.95 / σ 0.41 / 翘曲 max **81.88°**
  - `band`（折线+双侧 5mm 偏置折线）：4.18~5.32 / σ 0.08 / 翘曲 max **81.59°**
  - `hybrid`（折线+两竖切）：3.76~5.84 / σ 0.37 / 翘曲 max **78.10°**
  - **根因定论**：显式节点只控制"点在哪"，控制不了"配对行跟谁平行"。三刀切切出的是**矩形锚固带**（拓扑性质），
    故保留为默认。A 唯一收益=无竖切弦线→顶角 0.3mm 窄条消失（<3mm 短边 235→188），需要时局部用
- **修 cab2 v4 整块丢侧拉带的回归**：`out/` 清空后 `cab2_step2b_side2.txt` 不存在，组装只打一行 WARN 就继续 →
  侧条 196 单元/2354mm² 消失，而 `qa_kfile_strict`/质量门禁/`tether_conn_check`/`auto_gate` **五项全 PASS**。
  恢复：`tether_side_outline.py` → `gen_side_tab_full_outline.py` → `cab2_step2b_side2.txt`（99 单元/5mm，与主体统一）
- **★新增 `scripts/gate/partition_cover_check.py`**（专防整块丢）：按 PID 比对面积 + 连通组分逐个质心匹配 + 包围盒；
  `--write` 建基线 manifest，`--manifest` 每次核对；被抓证据 `[FAIL] PID5: 组分 9->8 丢失1块(2354mm²@(1683,172)) -3.82%`；
  退出码 2=不要交付。已接进 `run_case.sh` ⑦d（`PARTITION_MANIFEST=`）
- **组装参数新增 `WEAK_ANCHOR_MIN=1`**：默认 8 会把 6~7 个外边界锚点的凸台也判成弱锚做内部二次焊接（节点推开 3mm、p1 掉）；
  设 1 后只有"0 个外边界锚点"的侧条走内部锚固排。定版 `TAB_TOL=0.35 SNAP_INSIDE_TOL=3.0 WEAK_ANCHOR_MIN=1`
- **cab2 v8 交付**：`cab2_curtain_airbag_v8.k` 83,808 单元 / 82,102 节点 / 9 个拉带组分 / 面积 64,550mm²；
  不合格 82(0.10%)、`tether∩belt=77`、严格 K PASS、auto_gate PASS3/WARN2/FAIL0、分区覆盖 PASS
- 新增 `scripts/render/render_pid5_map.py`（拉带逐组分着色图）+ `scripts/gate/cmp_pid5.py`
- references/18 增 §10（A 实测对比）§11（侧拉带与整块丢事故）；SKILL.md §5.2.1 + §6 加门禁说明

## 2026-11-01 (6) — 拉带锚固边受布带约束：三刀切（cab2 v4 定版）
- **根因定论**：拉带在 Z=−1 独立 automesh，第一排节点落在**自己的**网格相位上；组装最近邻吸附横向位移最大一整格 5mm → 两个拉带节点争同一布带节点，输的留在 Z=−1 拉出 60~78° 扭转片；端点距轮廓 0.2~0.5mm 时留薄条，最小角归 0°。**换更聪明的吸附无用，必须让拉带的网格线穿过布带锚固点。**
- **新增 `scripts/stage3_mesh/plan_anchors.py`**：布带自由边（**必须减去气腔界面 1615 个**）∩ 拉带**真实轮廓环**（不是凸包）→ 按边界邻接排序成链；cab2 得 8 链 / 64 点
- **新增 `scripts/stage3_mesh/gen_tabs_anchored.py`**：逐块「建面 → **三刀切** → automesh」。三刀 = 过链两端沿法向各一刀 + 沿链方向过锚固线一刀，**三条线都必须贯穿面**（面内短线报 `Selected lines do not form a combined curve`）。中间块宽度 = 锚固段长度（被 5mm 整除）→ cab2 实测 8 块全部 **5.000mm / 偏差 0.000mm**
- **对照实测**：只横切一刀 → 5.137mm、累积偏差 1.7mm；锚固链拆 5mm 分段短线 → 公共端点两套节点（min 间距 0.00）网格不连续。**三刀是必须的**
- **端点取舍（两个反向坑）**：① 链端点落在面外 → 中间块被轮廓截短，间距 5.00→4.73；② 端点距轮廓仅 0.2~0.5mm → 薄条 + 78° 扭转。修法=`trim_chain()` 裁到面内 + **只对 `dmin≤0.6mm` 的端点外推**（阈值放大到 2.5mm 反而让块0 只剩 3/6 点能配）
- **cab2 v4 交付**：`cab2_curtain_airbag_v4.k` 83,709 单元 / 81,980 节点；锚固排宽度 0.33~10.00 → **4.26~5.07mm**、错位 σ 1.72 → **0.00~0.10**、最小角 p1 **0.0°→8.3°**、翘曲 max **165.70°→32.97°**、>15° 单元 53→23、`tether∩belt` 94→**58**、整体不合格 85→**74（0.09%）**、尺寸梯度超限 5→**0 对**
- **组装参数定版**：`TAB_TOL=0.35 SNAP_INSIDE_TOL=0`（吸附位移 3.00mm → **0.26mm**）
- **新增三个测量脚本**：`scripts/gate/anchor_metric.py`（过渡排最小角/雅可比/翘曲/蝴蝶结，翘曲用两三角面片法向夹角——用单三角法向会恒出 180°）、`scripts/gate/tab_anchor_stat.py`（逐凸台宽度/错位 σ）、`scripts/render/render_anchor_side.py`（侧视对比，Z 落差纵向放大）
- **已知极限（写进 reference，不含糊）**：锚固排两端仍 15~33° 翘曲（1mm 面外偏置 + 过渡排纵深仅 2mm → 26.5° 坡度，属几何本征）；每块两端 0.3~0.9mm 短边（**精确等距与无窄条在「三刀切+automesh 均分」框架内不可兼得**，同时满足需改用「锚固边显式节点序列」）
- 新增 `references/18_tether_anchor_three_cut.md`；SKILL.md §5.2.1 + §4 流程 ⑤ + §10 索引

## 2026-10-24 (1) — cab3 五环全自动一键链（门禁驱动网格尺寸自动调优）
- **新增 `scripts/cab3_auto/`**：`run_cab3.sh` 单驱动 + 8 个参数化脚本（`WORKDIR`/`REFDIR`/`MESH_START`/`MESH_MIN`/`CMAX_LIMIT` 环境变量，零硬编码），S0-S8 一键跑完，退出码即交付许可
- **新增 `shape_gate_v3.py`**：在逐环几何匹配基础上加**弦误差自适应判据** `cratio = dist/(DP_EPS + L²/8R) ≤ 1.0`，R 由「网格边两端点 + 边上最远原始曲线点」三点外接圆估计（自洽、不跨分支）。修掉 5mm 网格在 R≈5.8mm 圆弧上 0.496mm 固有矢高被固定 0.5mm 门限误判的问题
- **修三个测量伪差**（否则门禁永远假 FAIL）：① 洞贴合改用原始线采样点（桥接弦横切急弯 0.696→0.194）；② `drop_needles()` 剔除零面积针状突出（链式追逐伪迹，共线判定允许同向/反向）；③ D 检查用点→线段距离
- **网格命令选型实测**：`*interactiveremeshsurf 1 $sz 2 2 2 1 1` + `*setedgedensitylinkwithaspectratio -1` 保共形；`*surface_chordalmesh` 共形崩 + 碎单元 0.07mm 不可用；`*defaultmeshsurf_growth` 弦误差参数无效
- **cab3 交付**：`cab3_full_v3.k` 13193 节点 / 13770 单元，充气口 6 个捏合四边形（port_edges=6 len=17.2mm），shape_gate_v3 ALL PASS，结构门禁 + 拉带检查全 PASS
- 新增 `references/11_cab3_auto_pipeline.md`；SKILL.md 增 §4.1；config.json 增 `cab3_auto` 段

## 2026-10-22 (5) — NEW_CAB 四分区网格交付 + 两道几何门禁自检（逐环对拍 / 拉带连接）
- **NEW_CAB 端到端交付**：IGS 828 线 → 四分区（BELT/CAVITY/SEAM/TETHER）→ 网格 → K，全程过门禁。
  修复 x1483 凸台矩形环漏编（8 线 `[550..556,525]` 进足印层）、剔除内部重叠片、端口封口、拉带连接对齐。
- **新增两道几何门禁自检**（拓扑 QA 查不出"几何是否和 CAD 曲线一致"，P41）：
  - `geom_match_check.py` — 逐环把 IGES 线段几何（点云凸包）与网格几何（按 `mesh_pid` 分层选单元）对拍：位置（凸包质心）/ 面积（凸包比单侧）/ 边界（主判据 CAD→mesh）。
  - `tether_conn_check.py` — 拉带连通组分↔布带：必须接 PID2、误连气腔/缝线=0、共节点占周长<50%（防整面重叠）、无退化/伪单元、band 软校验（凸台=顶帽边、长条=末端竖边）。
  - `gen_ring_spec.py` + `assets/ringdef_newcab.json` — 由 classify + 足印清单生成 ring_spec.json。
- **坑位 P39–P47**：凸台矩形环漏编（P39）、拉带连接对齐规则（P40）、几何匹配需求（P41）、凸包而非链多边形（P42）、按 PID 分层选单元（P43）、凸包质心非面心（P44）、边界判据 CAD→mesh（P45）、boss 面积单侧判据（P46）、map=xy 坐标映射（P47）。
- **新增 `references/10_geom_match_and_tether_check.md`**（方法论/参数/NEW_CAB 实测）；SKILL.md 增 §3.7、§4 门禁加 7b、§7 索引补 P39–P47；`08_full_pipeline.md` 增 §7b 几何门禁；`run_pipeline.sh` 接 ⑦b（缺 ring_spec/lines_pts 自动跳过）。
- **NEW_CAB 自检实测**：geom_match 13 环全 PASS（belt/cav/seam 凸包比 1.000、boss CAD→mesh 覆盖 1.6–2.5mm；cavity 13mm 间隙在充气口图纸固有开口、boss 面积比 1.06–1.17 为垫料外延仅 WARN）；tether_conn 16 组分全 PASS（误连 0、退化 0）。

## 2026-10-21 (4) — NEW_CAB 四分区（布带/气腔/缝线/拉带）归类 + component 落地
- **新增 `references/09_partition_classify.md`**：用户口述四分区规则的完整落地方法（7 步流程 + 判据顺序 + NEW_CAB 实测数字 + 换项目 Checklist）
- **坑位 P35–P38**：`*movemark` 第三参是 comp **名称**不是 id（`*collectormarkmove` 不收 lines、`*renamecollectorbyid` 改名不可信、`*writefile` 覆盖已存在文件必先 `file delete -force` 否则 FatalError）；切线连续判据必须看端点类型配对（只查 dot<−0.985 有偏，漏一半搭接）；IGS 缝线"圆圈"是多段弧拼的（端点分析误判 V/方头）；Tcl 双引号内 `[` 是命令替换
- **新增脚本**：`bridge_scan.py`（跨类切线搭接扫描，v8 修正的全部依据）、`classify8_fix.py`、`export_class_lists.py`、`render_v8.py`、`seam_check.py`、`ladder_connect.py`、`make_comps.tcl`（建 4 comp + `*movemark` 搬线）、`verify_partitioned.tcl`（回读逐 comp id 集合校验 + 端点 bbox + 抽样线长回对）
- **NEW_CAB 结果**：BELT 119 / CAVITY 78 / SEAM 59 / TETHER 572（总 828），`newcab_partitioned.hm`；
  id 集合逐一比对一致、抽样线长与分区前导出逐位一致、bbox 与实测环范围吻合
- 方法要点：水滴/充气口与气腔共边界（410mm 顶边缺口图纸固有，不硬凑闭环）；充气口与水滴源头从 TETHER 回归原环（L762→BELT、L68/66/69/70/93/95/130/91→CAVITY）

## 2026-10-21 (3) — 2026 hmbatch 通道实证修正（P33/P34）+ 冒烟测试重写
- **冒烟测试重写**（`smoke_2026.tcl`）：改测流水线**真实操作**——模板加载 / `*readfile`+mark 计数 / spline 建面 / automesh / 写通道。2026 实测 **SMOKE_OK=1**（comp2 Belt 面 18,153 元素）
- **P33**：2026 hmbatch 里 `*createentity elems` 建不出元素（`Invalid element config`；`collector=`/`propertyid=`/`mark=` 报 data-name not valid；`*createentity nodes` 建的节点 mark 查不回）→ 记忆里那条是 **MCP live bridge（GUI Python API）** 的用法，hmbatch 建元素只有 spline+automesh 一条路。`02_hw2026_batch.md` §3 与 SKILL.md §2.2 已更正
- **P34**：2026 hmbatch automesh 静默出 0 元素（报 `Internal mesh error, try modifying element densities`，catch 得住不崩）→ 必须在 `*readfile` **之后**先 `*elementorder 1` + `*setedgedensitylinkwithaspectratio -1`；放 readfile 之前会触发不可 catch 的 FatalError。build_step1/build_tabs 两个 Tcl 本就带这两行
- 脚本全部支持 `WORKDIR` 环境变量覆盖项目路径（Python `os.environ` / Tcl `::env(WORKDIR)`，缺省仍 cab1），run_pipeline.sh 导出之 → 换项目不用逐个改硬编码

## 2026-10-21 (2) — 全链路部署：IGS → 几何清理 → 分区 → 网格完成
- **新增 `references/08_full_pipeline.md`**：完整链路文档，7 个阶段（导入/调查清理/分区/裁切拓扑三面网格/拉带捏合/充气口/门禁），每阶段命令+输入输出+cab1 预期数字+失败分支 + 换项目 Checklist
- **新增一键编排 `scripts/run_pipeline.sh`**（`SKIP_IMPORT=1` 跳过已有 .hm 的导入；门禁失败即整体失败）
- **补齐链路头部两个脚本**（2026-10-20 实测）：`import_igs_2026.tcl`（`*geomimport "iges_altair"` + `*writefile`，批处理导入只有 1 个 comp，组件结构靠 Python 聚类恢复或 GUI 预整理）、`survey_comps.tcl`（逐 comp spline 面积实证，PID=component id 的判定依据）
- **补齐后续阶段脚本**：`assemble_port.py`（充气口捏合）、`diag_cavity_port.py`、`diag_strap_ends.py`、`render_left_conn.py`、`render_before_after.py`、`fix_kfile_format2.py`、`qa_full2.py`、`render_lines.py`
- **基线数字全部按最终 deck 校正**：final K = 115,367 节点 / 83,743 单元（PID2 8,169 + PID3 71,208 + PID4 1,087 + PID5 3,279）；pre_tabs = 111,927 / 80,464；PID2∩PID5 共节点 **148**（左拉带单边连接后）；门禁全过（QA PASS / 长边 0 / 端口自由边 0）
- 坑位 P30–P32 已入排查索引；SKILL.md §4 快速开始重写为从 IGS 起的全链

## 2026-10-21 — 左拉带末端竖边连接（用户否决"整个重叠区啮合"后重做）
- **连接规则重定**（用户："啮合点在拉带顶端，粘合线垂直布带长度方向"）：凸台=顶帽边水平一条线（EDGE_BAND 8mm）；左区长拉带（`tabc*`/`tabh*`）=**末端竖边**一条线（END_BAND 3mm）
- **HORIZ 构造重做**：主轮廓线（最长线闭合成环 = 干净拉带体，右端斜切补直成竖直边）∪ 装饰线开运算包络（扇形接口）；锯齿/缝线不再上轮廓
- 修两个坑：开运算必须 ±2 净零（旧 +2/-2.5/+2.5 净 +2 使带宽 9.5→13.5mm）；HORIZ simplify 容差单独 2.0（扇形微锯齿 5mm 网格下必出 <3mm 短边）
- 结果：tabc7 末端竖边 6 共节点（x≈1114.5, z1191.7~1216.6）、tabh8 末端竖边 3 共节点（x1104.4, z946.5~956.8），与参考模型 R8 拓扑一致；R8 短边 97→0；QA PASS、长边 0、充气口 0
- `07_tab_tether_meshing.md` 增补 §5.1 左拉带连接拓扑实证；新增 `diag_strap_ends.py` / `render_left_conn.py`

## 2026-10-20 (2) — 拉带网格 + 连接
- 新增拉带（tabs/tethers）全流程脚本：`tabs_extract.py` / `gen_tabs_tcl.py` / `build_tabs_2026.tcl` / `assemble_tabs.py` / `ref_conn_map.py` / `export_tabs.tcl`
- 新增参考文档：`05_kfile_output.md`（K 写法 + 交付门禁）、`06_case_cab1_2026.md`（cab1 实战）、`07_tab_tether_meshing.md`（拉带方法）
- `04_pitfalls.md` 新增 P21–P28（拉带连接、参考模型拓扑、1-to-1 贪心、去重等）
- 拉带结果（cab1）：PID5 = 3233 单元，657 唯一 / 2367 关联节点共节点到布带，9 区域全连，QA PASS
- 关键修正：拉带只并到单层布带(PID2)，不能并到气腔/缝线（参考模型 PID8∩PID4=0）；连接靠节点捏合非 CNRB

## 2026-10-20 (1) — 裁切拓扑主链路
- 初版技能：MCP 连接 / 2026 批处理铁律 / 裁切拓扑方法 / 19 条坑位 P1–P20
- step1 deck：80464 单元，seam↔cavity 共节点 100%
- 修复 P1（eid 漏写导致 HM 读死机）+ P20 交付门禁 `qa_kfile_strict.py`

## 2026-10-25 (6) — 重组为通用技能「气帘自动网格划分」+ auto_gate 统一校验套件

- **目录重组**：从 `hypermesh2026_CURVEtoMESH_skill` 独立为 `E:/work/skill/气帘自动网格划分`，
  scripts/ 按流水线阶段分层（stage0_import / stage1_survey / stage2_partition / stage3_mesh /
  stage4_assemble / gate / render / drivers），全链路 7 阶段一目录贯通。
- **去项目硬编码**：全部脚本的 WORKDIR 默认值由 cab1 绝对路径改为 `.`；REFDIR 默认改 `./ref`；
  assemble_v3.py 的 MAT.K/03_Control_card.k 改 REFDIR 相对；组装链输出名统一
  `airbag_step1_2026.k`（DECK 环境变量可覆盖）；**技能内零 AI_CAB/cab1 路径残留**。
- **run_pipeline.sh 重写**：自定位 SKILL_DIR + 新目录结构 + GATE_ONLY（只跑门禁）+ GATE_CASE
  （接 auto_gate），换项目只改环境变量。
- **新增 auto_gate 套件**（`scripts/gate/auto_gate/`，9 文件，零第三方依赖）：
  run_gate 编排 + checks 五大检查 + kio（free/fixed 双格式 K 解析）+ svgfig（纯 Python SVG 出图）
  + clean_kfile（孤儿节点清洗）+ gate_rules.json（可迭代门限+changelog）+ case 配置外置 cases/。
- **反假阳性口径固化（三轮修正，全部来自 cab1 实战）**：
  ① 环几何逐 CAD 线拆解 + 跨 PID 覆盖三级判定（BELT74/75 充气口领圈 = 气腔 fabric 覆盖 → 跨 PID WARN，非 belt 缺口）；
  ② 拉带皮带腔界面识别（50 个 Y0 界面节点 = 参考模型允许的"拉带∩气腔侧单层"，非误连）；
  ③ 分层豁免跨角色界面节点（146 个拉带-布带共节点）。
- **重大发现**：clean_kfile 在 cab1 交付 K 中清出 **33,790 个孤儿节点**（定义但无单元引用，占 29%）——
  旧门禁完全没发现；并据此修正先前"belt 最近节点 0.4mm 良性"的误判（依据的是孤儿节点）。
- **cab1 回归**（rules v2026-10-25.2，清洗版 K）：WARN（PASS 3 / WARN 2 / FAIL 0），
  WARN = <3mm 尖边 + BELT74/75 跨 PID，均非网格破损。
- 新增 `references/12_auto_gate.md`、`cases/README.md`；SKILL.md 全文重写（通用化定位+训练迭代机制）。
