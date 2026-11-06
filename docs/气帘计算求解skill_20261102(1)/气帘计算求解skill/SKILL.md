---
name: qilan-solve
description: 气帘（充气帘/airbag curtain）**计算求解**技能——承接网格交付的 LS-DYNA `.k`，做"K 文件衔接门禁 → 整车整合/换装（清算验证工装、重编号防撞、参考 host 接线）→ 或**从零组合 deck**（车身+气帘两干净模型、全参考某参考模型、平移量按顶部距离差确定、拉绳 Z 向上投影）→ 约束/拉带固定/锚点 → LS-DYNA 求解（MCP / 本机 R10.1 / MPP n=2）→ 后处理（d3plot 二进制逆向 / glstat·matsum·abstat 健康门禁 / 漂移诊断）→ 渲染交付"。当用户说"气帘跑一下 / 算一下 / 套用参考模型约束材料厚度 / 整合进参考模型 / 换装 / 从零组合 / 平移对齐 / 拉绳投影 / 拉带没固定要加 / 质量增加终止 / forrtl 64 / 漂移太大 / 后处理看变形 / 充气体积对不对 / d3plot 怎么读 / 健康门禁过没过 / **设置一模一样还是抖 / 全参考对齐 / 阻尼失稳 / 上拉段抖 / 锚点质量 / 200ms 正式算例 / 换个气帘重走一遍**"时使用。沉淀自 2026-10-22 NEW_CAB 拉带固定实战、2026-10-25~28 cab1 整车整合攻坚（0.081ms 即爆 → 清算工装后参考 host 换装 2ms 正常终止）、2026-10-26~29 onekey 从零组合攻坚（BIW_clean.k + cab1_60ms.k 全参考 Model_update_Move_Iter04，2ms 探针正常终止）、**2026-10-31 全参考对齐 + 阻尼失稳定位 + 200ms 正式算例跑通（13h01m）**。
---

# 气帘计算求解（K 交付 → LS-DYNA 求解 → 后处理交付）

> **本目录是"气帘计算求解"阶段的唯一维护点。**
> 上游网格生成在 `E:\work\skill\hypermesh2026_CURVEtoMESH_skill`（曲线→面→网格→Y 分层→K），
> 上游四分区在 `E:\work\skill\气帘iges分区skill`（原始 IGES→四分区）。
> **本项目只调用这两个技能的脚本，不在具体项目里另写一份网格脚本。**

**版本基线**：
- 求解器：本机 LS-DYNA **R10.1.0 (rev123264)**，`D:\Program Files\ANSYS Inc\v193\ansys\bin\winx64\`
  （四个 exe 全是 R10.1，不是 v193 的 R13！R11 后关键字会被拒）
- MCP：`lspp-mcp`（`E:\work\lspp-mcp-server\`，56 工具：deck 检查/网格/本地求解/后处理/DOE/报告）；
  solver profile `ansys_smp_sp`（SMP, lsdyna_sp.exe, ncpu=4）
- Python：`C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe`（numpy / matplotlib / 已注册 msyh.ttc 中文字体）
- 后处理也可走 `D:\Program Files\LSTC\LS-PrePost 4.6\lsprepost4.6_x64.exe`，但**本技能用 numpy 直读 d3plot 二进制，不依赖 GUI**。

---

## 0. 一句话链路

```
网格交付 newcab_step1.k / 工作气帘 cab1_60ms.k
  └─⓪ 整车整合/换装：清算验证工装(SPC/CNRB) + 重编号防撞 + 参考host接线
       (03_Control_MOD + MAT.K + Vehicle.k + Spring改接)            [references/08, scripts/build_swap_clean.py]
  └─① K 衔接门禁(qa_kfile_strict + fix_kfile_format2 + geom_match/tether_conn 来自上游技能)
       └─ 从参考模型套用：约束(SPC/CNRB) + 材料 + 厚度 + 充气机(AIRBAG) [references/02,03]
  └─② 加约束：14 个扇形拉带自由端固定 + 主锚 [references/03]
  └─③ 求解：两段式——2ms 探针(死亡点×24) → 60-120ms 长跑        [references/02,08]
       lspp-mcp run_lsdyna_solver profile=ansys_smp_sp / 本机 lsdyna_sp.exe / MPP mpiexec -n 2
  └─③b 【跑之前两道门禁，2026-10-31 新增】
       ① 对齐审计 parity_audit.py（全卡逐字段 = 参考，偏离逐条 ack）      [references/10 §6]
       ② 阻尼门禁 damper_mass_gate.py（C < 2m/dt，否则补 *ELEMENT_MASS）  [references/10 §2,3]
  └─④ 健康门禁：k_health_gate.py 读 glstat/matsum/abstat  [references/04, scripts/k_health_gate.py]
  └─⑤ 后处理：d3plot_reader.py 逆向读坐标/速度/加速度/位移 + 固定节点校验 + 体积 [scripts/d3plot_reader.py]
   └─⑥ 漂移诊断：matsum 各 part 动量 + abstat 充气自洽 + 锚点分布  [references/04]
   └─⑥b 抖动诊断：内能分解(spring/damper 占比) → C_crit=2m/dt → 补质量 [references/10 §2,3]
  └─⑦ 渲染交付：render_deploy.py → 部署过程图 + 终态细节图  [scripts/render_deploy.py]
```

---

## 1. 何时用 / 何时不用

**用**：
- 已有气帘网格 `.k`，要套用参考模型补约束/材料/厚度后试算
- 用户说"拉带没固定 / 要加约束 / 参考模型拉带有固定"
- **要判定 deck 是否与参考"完全一样"**（`parity_audit.py`，逐卡逐字段，等价偏离显式登记）
- **上拉段（点爆前）抖动 / 气帘乱飞舞**（references/10：先算 `C_crit=2m/dt`，补锚点质量，不改参考参数）
- 求解跑完要判读健康门禁（质量增加、沙漏、能量比、触底、充气）
- 要看变形过程、位移云图、充气体积、漂移原因
- d3plot 不会读 / MATLAB/LSPP 不方便时的轻量逆向
- **换一个气帘重走全流程**（references/10 §10 九阶段 + 只改 9 个参数）

**不用**：
- 从原始 IGES 开始 → 用 `气帘iges分区skill`
- 曲线→网格→K → 用 `hypermesh2026_CURVEtoMESH_skill`
- 纯线性分析（模态/刚度）→ 用 OptiStruct 技能
- 跨文件 id 引用搞错导致的"飞丝" → 见 references/01 P29 铁律

---

## 2. 最关键的五条铁律（先读这个）

1. **K 文件绝不手改格式**：薄片/退化/重编号错一处，HM 读死机或求解器读错拓扑。
   只用**逗号自由格式**（首选）或严格 10 字符定宽；4 位数坐标+6 位小数必须自由格式。
   QA 验证器（`qa_kfile_strict.py`）必须比真实读取器更严，不共享字段假设。 → references/01
2. **跨文件 id 引用，坐标+id 必须从目标 K 本身解析**：中间导出 txt 只用于渲染/统计，
   拿 txt 的 nid 当 K 的 gid 用 = 飞丝（NEW_CAB 实测 1174 条 >20mm 长边）。 → references/01 P29
3. **固定节点必须用"当前坐标逐位==初始坐标"验证**：MCP 长跑后易掉线、spcforc 对
   CNRB+SPC 组合不报反力。**唯一硬判据** = d3plot 状态下固定节点 1800/1800 坐标 max|Δ|=0.0。 → references/03,04
4. **deck 删改必须整块操作，合并前必须过 ID 审计**：删 `*XXX` 连数据行删到下一个 `*`
   （孤儿数据行 → forrtl severe(64) 段错误）；跨文件合并先做七类 ID 审计
   （nodes/parts/sections/mats/curves/node-sets/part-sets），重编号用段位偏移(+30M)。 → references/08
5. **"完全参考参考模型" = 卡片参数一个数不动；抖动先算 C，别先改参数**（详见 references/10）：
   - 抄对了却不正常 → 先 `parity_audit.py` 证明抄对，再找**模型条件**差异（用户明确否决"降 C 遮症状"）。
   - 离散阻尼失稳判据 `C_crit = 2m/dt`。**m 必须用 part 总质量 ÷ 节点数反算**（实测 **0.0075 g**，
     按单元面积手算会大 3000 倍）。气帘锚点 `C_crit=0.0303` 而参考 `C=0.2` → **超临界 6.6 倍**。
     解法是 `*ELEMENT_MASS` **每点固定补 1 g**（`C_crit→4.07`，裕度 20 倍），不是改成 120 g、更不是改 C。
6. **交付前看一个数：所有锚点末态 `dZ/L` 是否 = 1.000**（L = 绳长）。这套"恒力索 + 固定车身"构造里，
   每个锚点被拉到自己的绳长即锁死；`dZ/L` 全 1.000 ⇒ 无超伸、无穿绳、锚点取点正确。
   末态 dZ 彼此差几十上百毫米是**正常**的（绳长不同），不要当不同步。 → references/11 §8, 12 §4

---

## 3. 文档索引（references/）

| 文件 | 内容 |
|---|---|
| `01_kfile_handoff.md` | K 交付→求解衔接：格式铁律、eid 漏写/退化/飞丝坑、QA 门禁脚本、长边检查 |
| `02_solve_setup.md` | 求解器配置（solver profile / MCP / 本机 exe）、DT2MS 负值、质量缩放、网格硬条款、时间步受控 |
| `03_constraints_tether.md` | 约束/拉带固定/锚点：SPC、CNRB、参考模型实况、固定 14 拉带端实战、固定双证、锚点布置陷阱 |
| `04_postprocess_d3plot.md` | **d3plot 二进制逆向布局**（主/状态文件）、健康门禁判读、漂移诊断、时刻标定、渲染 |
| `05_quick_setup.md` | 快速设置清单：一键环境、路径、venv、典型命令序列 |
| `06_specs.md` | 《DEP_2012001 碰撞模型建立流程规范 1.1》关键条款引用（强制先查） |
| `07_pitfalls_index.md` | 全链坑位总索引 **P-S01–P-S92**（网格→整合→求解→无人值守），含跨技能链接 |
| `08_deck_integration.md` | **整车整合/换装**：工装清算(P-S14)、整块删/定宽/接触卡红线、ID 段位偏移+七类审计、时间读数陷阱、dt2ms 钉步基线、块级二分定位、host 接线、MPP 提交模板 |
| `09_fresh_deck_build.md` | **从零组合 deck**（车身+气帘两干净模型全参考某模型）：平移量顶部距离差(P-S35)、拉绳Z向上投影(P-S28)、混入孤立节点(P-S29)、ID基准/平移/行索引(P-S30/31/32)、SET冲突(P-S33)、刚体不加全SPC(P-S34)、接触单面(P-S37)、投影dXY验收(P-S38)、弹簧能量异常=投影缺陷报警(P-S36)、ENDTIM参考一致vs用户选项(P-S39)、主跑估时(P-S40)、主跑启动配方、**减抖三处修复**（拉绳SPC锁X/Y·Z自由、投影强制取上方、*AIRBAG_REFERENCE_GEOMETRY 参考几何，§11，P-S41 4字段坑）、**SMP渲染跑配方与抖动验证管线**（§12，P-S42~P-S46） |
| `10_full_parity_damping.md` | **全参考对齐 + 离散阻尼失稳**（"设置一模一样却抖动"的判据与解法）：P-S49 完全参考=卡片不可动（禁降C遮症状）→ P-S50 `C_crit=2m/dt` 判据与 C 扫描证据 → P-S51 补 `*ELEMENT_MASS` 到 120g（不动参考卡的唯一正解）→ P-S52 质量卡格式 → P-S53 气囊卡整块照抄 → P-S54 全卡 diff 审计与等价差异清单 → P-S55 质量缩放读数 → P-S56 OPEN 点爆能量疑点 → P-S57 厚度取值坑；**§10 是九阶段工作流 + 换气帘只改 9 个参数 + 回归基线**；**§13 用参考模型当"能量标尺"**（P-S78~P-S84：跑 5ms 基准做同刻对照，`SPR≈0.025·t³` 是固有特征不是失稳；`MAT_RIGID CMO/CON1/CON2=1.0 7.7` 把车身钉死；`MAT_CABLE_DISCRETE_BEAM` E=0+F0 是恒力绞盘；`ncpu=` 不是 `n=`；两张卡的定宽字段序；参考 10 根绳里 7 根连不存在的 node 1~7） |
| `11_cab2_onsite_log.md` | **CAB2 现场实战复盘**（一次真实"从错到通过"的完整因果链）：7 个坑逐条给 症状→误判→根因→修法→验证。锚点取凸台根部致气帘扭转(P-S68) → 绳长 81mm 致质量放大 1E+05(P-S73) → `MAT_CABLE` 是恒力索不是弹簧 → 阻尼超临界 6.6 倍致能量注入(P-S50/P-S74，用户提示命中) → 车身"钉死"是参考意图 → 三次假故障（SPR t³）→ 7 个静默失效（`ncpu=`/shell 字段序/幽灵绳节点/BEAM+DISCRETE 重复计数/lasso 坐标/`rm` 被拦）。**含最终通过时的 dZ/L=1.000×9 强证据** |
| `12_unattended_ops.md` | **无人值守作业规范**（长时算例边算边判、错了立刻重开）：三层监控（进程级/几何级/视觉级）、L1 判据表 T1~T9、L2 判据表 J1~J6、**J2 窗口取法与绳长归一化**、阈值用参考基准标定（§5）、**看门狗自身三个失效模式**（漏传 `--json` 报了 40 分钟假 OK）、重启决策树、部署到新项目只改三处 |

## 4. 脚本索引（scripts/）

| 脚本 | 用途 |
|---|---|
| `d3plot_reader.py` | 逆向读主 d3plot + 状态文件：坐标/速度/加速度/位移、固定节点校验、腔体包络体积、各 part 平移（**numpy 直读，无需 GUI**） |
| `k_health_gate.py` | 读 glstat/matsum/abstat，自动判读 6 道门禁（质量<3%/沙漏<3%/能量比/触底/DT2MS/充气自洽），退出码 0/1 |
| `render_deploy.py` | 渲染部署过程（平铺→充中起→终态）+ 终态四视图 + 位移云图，自动标定时刻，中文字体 |
| `smp_d3plot.py` | **SMP 单文件 d3plot 逆向 reader**（2026-10-29）：不解析连接段（状态0==g0 定位 + stride 校验），`--shake` 输出 vrms/vmax/dmean/dmax 抖动指标（MPP d3plot 不适用，见 P-S44） |
| `render_fixed.py` | **减抖验证渲染**（2026-10-29）：前 27ms 逐帧侧视图（按|位移|着色）+ 总览 + 速度 RMS 历程，配合 `smp_d3plot.py --shake` 定量对比修复前后抖动 |
| `qa_kfile_strict.py` | *(镜像自 CURVEtoMESH 技能)* K 文件独立严格校验（eid 唯一/pid 合法/无退化/无重复） |
| `fix_kfile_format2.py` | *(镜像自 CURVEtoMESH 技能)* K 格式修复，回读比对 1e-12 |
| `geom_match_check.py` | *(镜像自 CURVEtoMESH 技能)* IGES vs 网格逐环对拍（按 mesh_pid 分层防面积翻倍） |
| `tether_conn_check.py` | *(镜像自 CURVEtoMESH 技能)* 拉带连通检查（须接 PID2、共节点占周长<50%） |
| `build_swap_clean.py` | **整车换装一条龙**（2026-10-28 实战）：清算工装→+30M 重编号→曲线 30M 段映射（AIRBAG 定宽原位替换）→参考拉带最近贪心改接→host 组装→七类 ID 审计 |
| `parity_audit.py` | **全卡对齐审计**（2026-10-31）：展开 `*INCLUDE`、`*XXX_TITLE` 规范化、ID 类卡按 ID 配对（`--id-map` 处理 30M 段）、20 字符定宽曲线行、文本/补白行降级、`--ack` 三级登记等价差异；退出码 0/1 作门禁 |
| `damper_mass_gate.py` | **离散阻尼显式稳定门禁**（2026-10-31）：估锚点质量 → 判 `C < 2m/dt` → `--emit` 直接吐出 `*ELEMENT_MASS` 补偿卡。**跑之前用它，别用 3ms 试算发现抖动**。⚠️ 其中"按 `面积/4 × T1 × rho`"只是**粗估量级**；精确值必须用 **part 总质量 ÷ 节点数** 反算（实测 0.0075 g，面积法差 3000 倍，P-S74）。补偿量按**固定增量**给（每点 1 g），不要 fill-up 到大数 |
| `watch_run.py` | **无人值守看门狗**（2026-11-02）：盯 glstat+main.log，T1 dt 崩塌 / T2 质量缩放 >3% / T3 报错 / T4 停滞 / T5 能量爆炸 / T6 沙漏 / **T9 绳能量跑出参考带 `SPR>20×0.025t³`** / T7 vz 反向 / T8 锚点不同步；触发即 `taskkill /F /T` 整棵进程树 + 写 `ALERT.txt`；每 20 轮自动调 `check_tethers.py`。用法见 `references/12` |
| `check_tethers.py` | **拉带几何体检**（2026-11-02）：直读 d3plot，锚点与绳长**自动从 deck 解析**（不写死节点号，BEAM+DISCRETE 按节点对去重）。判据全部**相对各自绳长**：J1 超伸 >5%L / J2 上升窗口内速度偏差 / J3 偏离趋势 >3mm / J4 横向漂移 / J5 回落 >2mm / J6 到顶锁死=正常。输出 `verdict: PASS/WARN/FAIL` 供看门狗消费。**不要用"锚点彼此 dZ 散差"判不同步**（P-S86/P-S87） |
| `plot_d3plot.py` | 不用 LS-PrePost 直出气帘形态图（XZ/XY，颜色=dZ），判"帘子有没有被拉歪/扭转" |
| `plot_anchors.py` | **锚点几何验证图**：初始网格上叠加 10 根绳的起止点，看绳是否从凸台顶面竖直向上、是否穿布、是否某根特别长。要求目录内有 `cab2_clean.k / BIW_clean.k / Spring_swap.k` |
| `plot_ref_ab.py` | **本模型 vs 参考模型几何 A/B 对照**（上下两栏同比例）：判断"锚点位置对不对"的唯一硬标准。自动兼容逗号自由格式与 8 字符定宽 deck（`*NODE` 是 I8+3E16，与 `*ELEMENT_*` 的 I8 不同，踩过） |
| `cmp_energy.py` | **glstat 同刻对照**：本模型 vs 参考基准的 KE/IE/SPR/dt 三联图 + 同刻插值偏差表。|dev|<10% ⇒ 同源，能量增长是构造固有特征，不是失稳 |
| `run_deck.sh` | **标准启动脚本**：ANSYS 许可双变量 + `ncpu=`（不是 `n=`）+ 启动后自检（MPP banner 计数、`2/` 目录告警） |
| `ref_bench.sh` | **造 5ms 参考基准算例**：只改 `ENDTIM 200→5` 和 `D3PLOT 2.5→0.25`，其余卡片一个数不动。产出 `glstat` / `d3plot` 供 `cmp_energy.py`、`check_tethers.py` 做阈值标定 |

> **从零组合（两干净模型，对应 `references/09`）的参考实现**见项目副本 `E:\work\AI_CAB\onekey\gen_deck.py`：清工装+平移+重编号 → BIW 刚体化+剔混入节点 → 拉绳 Z 向上投影 → 抄参考接触/载荷/传感 → 组装 main.key。项目专属，不放入本技能 `scripts/`。
> 镜像脚本来源：`E:\work\skill\hypermesh2026_CURVEtoMESH_skill\scripts\`。
> 上游更新时同步覆盖本目录副本即可；本技能不维护网格生成逻辑。

## 5. 资产（assets/）

- `case_config.example.json` —— **换气帘参数表模板**（2026-10-31）：复制成项目 `case_config.json`，
  只改 `inputs / placement / tether / damper / run` 里的值，其余卡片全部照抄参考；
  文件内已把"为什么这么定"和"回归基线"写在 `_` 注释键里（对应 references/10 §10.2）。
- `render_deploy_process.png` —— 部署过程示例（NEW_CAB 平铺→4.4ms→9.4ms→20ms）
- `render_t20_detail.png` —— 终态细节示例（X-Z 分区 / Y-Z 侧视 / X-Y / 位移云图）
- （健康门禁示例报告见 `references/04` 末尾）

## 6. 换项目 Playbook

1. 拿到网格 `.k` → 先跑 `qa_kfile_strict.py` + `geom_match_check.py` + `tether_conn_check.py`（上游技能）。
2. **要整合进参考模型/换装时**（references/08）：`build_swap_clean.py` 一条龙——
   清算验证工装（SPC/CNRB 整块删）→ +30M 重编号 → 材料用参考 MAT.K →
   参考拉带最近贪心改接 boss cap → host 组装 → 七类 ID 审计；
   然后 **2ms 探针**（`*** termination time reached ***` + added mass <1% 才算过）→ **60-120ms 长跑**。
2b. **只有两堆干净网格（车身 BIW + 气帘）+ 一个参考 deck 当模板时**（references/09，对应 `gen_deck.py`）：
   ① 平移量按"气帘顶→车身顶距离差一致"回算 DY/DZ（P-S35），别肉眼对齐；
   ② 清两模型非网格设置 → 气帘 +30M 重编号+平移，车身刚体化（P-S34 不加全 SPC）；
   ③ **剔车身混入的孤立节点**（P-S29），拉绳锚点用"同 X 邻域 Z 向上"投影（P-S28），用 ΔZ 一致性验收（P-S38）；
   ④ 逐张照抄参考的接触（单面 SSID=2，P-S37）/上拉（LOAD_BODY_Z 缩放 0.0098）/点爆 SENSOR/AIRBAG_HYBRID_ID（R10 保留）；
   ⑤ 同样先 **2ms 探针**再过 **60-120ms 长跑**；若弹簧/阻尼能量异常暴涨，先看 P-S36（=投影/锚点几何错误报警，回查 P-S28/P-S30/P-S34，别去调间距）；
   ⑥ **减抖三件套**（references/09 §11）：拉绳起点 `*BOUNDARY_SPC_NODE` TX=TY=1/TZ=0（Z 向垂直动）→ 投影所有层级强制 `bz>z` 取上方节点 → 拷 `*AIRBAG_REFERENCE_GEOMETRY` 进 deck（**R10.1 严格 4 字段/行**，P-S41，6 字段=Error 30099）；
   ⑦ **要看 d3plot 渲染**（references/09 §12）：另跑 SMP 验证版（`memory=50000000 ncpu=2`，P-S42/43；渲染控制卡关 EXTENT_BINARY 输出 flag，P-S45），用 `smp_d3plot.py --shake` + `render_fixed.py` 定量对比抖动。
   ⑧ **上拉段还抖 → 走 references/10**：先 `parity_audit.py` 证明全卡对齐（P-S49/P-S54），
      再 `damper_mass_gate.py` 算 `C_crit=2m/dt`（P-S50/P-S57），补 `*ELEMENT_MASS` 到 120 g（P-S51），
      **绝不用降 C 遮症状**；这套流程见 references/10 §10 的九阶段工作流（换气帘只改 9 个参数）。
3. 从参考模型（`E:\work\AI_CAB\ref-Output\Model_update` 或 `Model_from_AI_07`）提取：
   *SECTION_SHELL*（厚度/ELFORM）、*MAT_FABRIC* 或等效、*AIRBAG*（充气机）、
   *BOUNDARY_SPC* / *CONSTRAINED_NODAL_RIGID_BODY*（约束）、*CONTROL_*（DT2MS 负值）。
4. 加约束（拉带固定见 references/03）→ 写 deck `newcab_calc.k`。
5. **跑之前两道门禁（必须过，references/10 §10.1 的 S5/S6）**：
   - `parity_audit.py --ours main.key --ref <REF>/main.key --skip-bulk --diff-only --id-map "DEFINE_CURVE:30000000"`
     → 设置类卡全 MATCH；等价偏离逐条 `--ack` 登记理由（唯一允许的物理偏离只应有一条）；
   - `damper_mass_gate.py --grid 气帘K --grid MAT.K --nodes <锚点> --dt 4.95e-4 --c 0.2 --emit`
     → PASS；不过就把它吐出的 `*ELEMENT_MASS` 粘进 `Spring_swap.k` 再复算。**不要改 C**（P-S49）。
6. `lspp-mcp` 的 `run_lsdyna_solver(profile="ansys_smp_sp")` 提交；长跑后若 MCP 掉线，
   直接用本机 `lsdyna_sp.exe` 或 numpy 直读 d3plot（references/04）。
7. 跑完 `k_health_gate.py --glstat --matsum --abstat`；再 `d3plot_reader.py` 校验固定节点；
   `render_deploy.py` 出图交付。上拉段抖动 → `smp_d3plot.py --shake` 定量 + references/10 §2 判据。

## 7. 目录结构

```
气帘计算求解skill/
├── SKILL.md
├── config.json
├── CHANGELOG.md
├── references/
│   ├── 01_kfile_handoff.md
│   ├── 02_solve_setup.md
│   ├── 03_constraints_tether.md
│   ├── 04_postprocess_d3plot.md
│   ├── 05_quick_setup.md
│   ├── 06_specs.md
│   ├── 07_pitfalls_index.md
│   ├── 08_deck_integration.md
│   ├── 09_fresh_deck_build.md       (从零组合两干净模型, 2026-10-29)
│   ├── 10_full_parity_damping.md    (全参考对齐 + 阻尼失稳 + 九阶段工作流, 2026-10-31)
│   ├── 11_cab2_onsite_log.md        (CAB2 实战复盘: 7 个坑的症状→根因→修法→验证, 2026-11-02)
│   └── 12_unattended_ops.md         (无人值守: 三层监控 + 判据表 + 重启决策树, 2026-11-02)
├── scripts/
│   ├── d3plot_reader.py
│   ├── smp_d3plot.py               (SMP 单文件 d3plot reader + 抖动指标, 2026-10-29)
│   ├── render_fixed.py             (减抖验证渲染: 前27ms逐帧+速度RMS, 2026-10-29)
│   ├── parity_audit.py             (全卡逐字段对齐审计 + --ack 登记, 2026-10-31)
│   ├── damper_mass_gate.py         (C<2m/dt 阻尼门禁 + 输出补偿质量卡, 2026-10-31)
│   ├── k_health_gate.py
│   ├── render_deploy.py
│   ├── build_swap_clean.py         (换装清洗一条龙, 2026-10-28)
│   ├── watch_run.py                (无人值守看门狗 T1~T9 + 自动 kill, 2026-11-02)
│   ├── check_tethers.py            (拉带体检 J1~J6, 绳长归一化, 2026-11-02)
│   ├── plot_d3plot.py              (形态图: 判帘子有没有被拉歪, 2026-10-31)
│   ├── plot_anchors.py             (锚点几何验证图: 绳是否穿布/特别长, 2026-11-02)
│   ├── plot_ref_ab.py              (本模型 vs 参考几何 A/B 对照, 2026-11-02)
│   ├── cmp_energy.py               (glstat 同刻对照: |dev|<10% 即同源, 2026-11-02)
│   ├── run_deck.sh                 (标准启动: 许可双变量 + ncpu= + 自检, 2026-11-02)
│   ├── ref_bench.sh                (造 5ms 参考基准算例做阈值标定, 2026-11-02)
│   ├── qa_kfile_strict.py          (镜像)
│   ├── fix_kfile_format2.py        (镜像)
│   ├── geom_match_check.py         (镜像)
│   └── tether_conn_check.py        (镜像)
└── assets/
    ├── case_config.example.json    (换气帘参数表模板, 2026-10-31)
    ├── render_deploy_process.png
    └── render_t20_detail.png
```
