# CHANGELOG — 气帘计算求解skill

## 2026.11.02.1 (2026-11-02)
**主题：CAB2 现场实战复盘 —— 修好"只有充气口和右边在拉伸"，并把"边算边判"变成可交付能力。**
**本轮最大的收获不是修好了模型，而是发现：有 4 次是"判据错了、模型对了"。**

- **新文档 `references/11_cab2_onsite_log.md`**（实战复盘，7 个坑逐条给 症状→误判→根因→修法→验证）：
  - **P-S68 锚点取凸台顶面**：9 个拉带是凸台（Z 868.8→1015.5，高 147mm），旧代码取**根部**，
    绳从布带上沿斜飞跨过整个凸台 → 凸台自由翻卷 → 气帘扭成螺旋，肉眼即用户所报
    "只有充气口和右边在拉伸、锚点在拉带上方"。改取顶面后绳长 227~450 → 81~184mm，2ms 形态图平整。
  - **P-S73 绳长硬下限 95mm**：cable beam 自然 dt≈L/c，L=81mm 低于 `|DT2MS|` → 节点质量被缩放到 **1E+05 kg**，
    t=0.05ms 就 Error。二分实证：dZ=81.1 崩（dt 2.7E-05）/ dZ=96.7 干净（dt 6.45E-04）。
  - **P-S74 锚点补质量正解 = 每点 1 g（不是 120 g）**：用 **part 总质量 ÷ 节点数** 反算真实节点质量
    `0.7001 kg / 93342 = 0.0075 g` → `C_crit = 2m/dt = 0.0303`，`C=0.2` **超临界 6.6 倍**。
    ⚠️ **推翻 2026.10.31.1 的 P-S51（120 g）与旧记录（24.4~42.4 g）**——那是按单元面积手算的，比真值大 3000 倍。
    补 1 g 后 `C_crit=4.07`（裕度 20 倍），10 点共 10 g 占气帘 1.4%；实测 SPR 从 1.98E+05 降到 2.25E-05（小 12 个数量级）。
  - **P-S78/P-S79 认知修正**：`MAT_CABLE_DISCRETE_BEAM` 卡片 `2400001 7.8E-6 0. 0 0.4 1.E10 10. 0` 里
    **E=0、`1.E10` 是预张力终止时间不是刚度** → 这是**恒力绞盘**，不会"拉直就停"。改 E 为 2.1E5 能量曲线一模一样。
  - **P-S78 车身"钉死"是参考意图**：`*MAT_RIGID 2010` 的 `CMO CON1 CON2 = 1.0 7.7` = 全自由度约束；
    `Vehicle.k` 的 part 用的也是 MID 2010 → 车身是固定台架，气帘被 10 根 0.4N 恒力索以 ≈20 g 上拽，
    34ms 顶到车顶梁（行程 115mm）后点爆。**不要改 CON1/CON2。**
  - **§6 三次假故障**：SPR 按 t³ 涨到 1.95 J 看着要炸，实际把参考模型自己跑 5ms 同刻对照，
    t=0.8ms 时 **差 2.4%** → `SPR≈0.025·t³` 是构造固有特征，不是失稳。
    ⚠️ 附带陷阱：`ref-Output/Model_update` 的 main.key **不含 Vehicle/Spring**，其 SPR 恒为 6.4E-19
    不能当"参考阻尼器是死的"的证据 —— **用别人 glstat 前先 `grep INCLUDE`**（P-S90）。
  - **§7 七个静默失效**：`n=2`→生成 "2" 目录+Signal 11（必须 `ncpu=`）；`*ELEMENT_SHELL` 自由格式节点在 `s[2:6]`
    （取 `s[1:5]` 会静默丢光全部单元且不报错）；参考 10 根绳里 7 根连**不存在的 node 1~7**；
    BEAM+DISCRETE 双定义需按节点对去重（否则 10 根数成 20 根）；`*NODE` 定宽是 **I8+3E16** 而 `*ELEMENT_*` 是 I8；
    lasso 的 `node_displacement` 是"当前坐标"要减 state0；`rm -f d3plot*` 被 safe-delete 拦改 Python。
  - **§8 最终通过证据**：10 个锚点末态 **`dZ/L` 9/10 精确 = 1.000**（升到自己的绳长即锁死），
    最大超伸 6.59mm(<5%L)，dt 恒定 4.95E-04，added mass 0.005%，全时程 200ms。

- **新文档 `references/12_unattended_ops.md`**（无人值守作业规范，用户核心诉求"不能等算完才发现"）：
  - **三层监控**：L1 进程级 `watch_run.py`（每 60s）、L2 几何级 `check_tethers.py`（每 20 轮）、L3 视觉级形态图。
  - **L1 判据 T1~T9**，新增 **T9 绳能量跑带** `SPR > 20×0.025·t³`（参考标定带，避免绝对阈值天天误报）。
  - **L2 判据 J1~J6**：J1 超伸 >5%L、J2 上升窗口内速度偏差、J3 偏离趋势、J4 横向漂移、J5 回落、J6 锁死=正常。
  - **§4.1 核心认知修正（P-S86/P-S87）**：**不能用锚点彼此的 dZ 散差判不同步**。各绳长度不同，
    每根升到自己的绳长就锁死，末态散差 177mm 却完全正常（dZ/L 全 =1.000）。正解 = **绳长归一化 + 全未绷紧窗口内比拟合斜率**。
  - **§6 看门狗自身三个失效模式**：漏传 `--json` 导致连续 **40 分钟**报 `t=5.0ms 太早不判`（实际已 104ms）、
    阈值过严误杀、判据本身错。自查法：`monitor.log` 的 t 与 `main.log` 是否一致。
  - **§7 重启决策树**：只有 FATAL 才 kill，WARN 一律先出图确认，避免判据过敏杀掉好算例。
- **新脚本 8 个**：
  - `watch_run.py` 无人值守看门狗（T1~T9，触发即 `taskkill /F /T` 整棵进程树 + 写 `ALERT.txt`）。
  - `check_tethers.py` 拉带几何体检（**锚点与绳长自动从 deck 解析，不写死节点号**，BEAM+DISCRETE 去重，
    输出 `verdict: PASS/WARN/FAIL` 供看门狗消费）。
  - `plot_d3plot.py` 形态图；`plot_anchors.py` 锚点几何验证图（绳是否穿布/是否某根特别长）。
  - `plot_ref_ab.py` **本模型 vs 参考模型几何 A/B 对照**（判断锚点位置对不对的唯一硬标准，自动兼容两种 deck 格式）。
  - `cmp_energy.py` glstat 同刻对照（三联图 + 同刻偏差表，|dev|<10% 判同源）。
  - `run_deck.sh` 标准启动（ANSYS 许可双变量 + `ncpu=` + 启动自检）；`ref_bench.sh` 造 5ms 参考基准。
- **修正 `scripts/damper_mass_gate.py` 的说明**：其中"面积/4×T1×rho"只是粗估量级，
  精确值必须用 part 总质量 ÷ 节点数反算；补偿量按固定增量（每点 1 g），不要 fill-up 到大数。

## 2026.10.31.1 (2026-10-31)
**主题：从"把这次算对"升级为"以后每个气帘都能复用"——全参考对齐 + 阻尼失稳判据 + 两道跑前门禁 + 九阶段工作流。**

- **新文档 `references/10_full_parity_damping.md`**：解决"设置跟参考一模一样，上拉段还是抖"这条最容易被误判的故障线。
  - **P-S49（方法论铁律）**："完全参考参考模型"= 卡片参数一个数不动。用户当面否决了"C 降到 0.010 让抖动消失"——
    症状消失但 deck 与参考不再可比，所有结论失去基准。正确推理链：逐卡 diff 证明抄对 → 查模型条件差异 →
    找被破坏的物理约束 → 用**不动参考参数**的方式恢复它。
  - **P-S50 判据**：`MAT_DAMPER_VISCOUS` 显式失稳 `C < 2m/dt`。锚点 `24.4~42.4 g`、`dt=4.95E-4 ms`
    → `C_crit=0.098~0.171`，参考 `C=0.2` 刚跨临界 **1.2~2 倍** → 上拉段抖动而 glstat 全局"健康"。
    阈值实证：同 deck 只改 C，KE 峰值 `0.2→572（爆）` / `0.10→1.1E-04（健康）`，跨 5 个数量级（断层式 = 失稳指纹）。
    定位捷径：内能分解 `spring+damper 占 99.3%` → 嫌疑人从整模型缩到 10 个阻尼器。
  - **P-S51 正解**：不改参考卡，`*ELEMENT_MASS` 把 10 个气帘侧锚点补到 `1.2E-4` tonne（**120 g**，不是 mg），
    `C_crit=0.48`、裕度 2.4 倍；总加质量 ≈1.1 kg（added mass 0.023%）。效果：3ms KE `572→5.70E-03`（参考的 0.49 倍），
    首帧抖动 `46.6→1.3 mm`。方案对比表（补质量 / 降 C / 换非线性阻尼）一并入档。
  - **P-S52~P-S55**：`*ELEMENT_MASS` 必须逗号格式（8+8 定宽在 nid 顶满 8 位时粘连）；气囊卡整块照抄不重映射曲线 ID；
    全卡 diff 的已知等价差异清单（接触 SSID / SPR=MPR=1 / 全零补白行 / 唯一物理偏离 D3DUMP 间隔）；
    `2.29E-02` = 0.023% 不是 2.3%。
  - **P-S56（OPEN，如实标注）**：点爆 `100→110ms` external work `-1.5→+370 kJ`（反算 ≈9.7 MPa）与 abstat `1E-5 MPa`
    差 6 个数量级；已排除 6 项，待验路径 = `d3dump08` 重启 4ms 三组对照（原样 / 删 AIRBAG / 曲线置 0）。
    **纪律：报告必须标注该疑点，不能因"曲线与参考一致"就默认无问题。**
  - **§9 200ms 正式算例基线**：`404041` 步 / `13h01m` / added mass `0.023%` / energy ratio `0.9999` / hourglass `0`；
    上拉段 KE `0→2.58 @15ms→1.23 kJ` 平滑无尖峰；点爆段体积 `8→45→50 L`、KE 峰 `270 kJ @101.9ms`。
    **P-S40 估时由 11h 修正为 13h**（`404041/8.4 cyc/s ≈ 48100 s`）。
  - **§10 九阶段工作流（本次核心交付）**：S0 参数化 → S1 网格进厂 → S2 清工装 → S3 平移重编号 → S4 锚点投影 →
    S5 卡片照抄 → **S6 阻尼门禁** → S7 3ms 探针 → S8 200ms 主跑 → S9 后处理；每阶段写明 STOP/GO 门禁与对应工具。
    附**换气帘只改的 9 个参数表**（CAB_K/BIW_K/REF_DECK/DY,DZ/NOFF/拉带数/ANCHOR_MASS_TARGET/ENDTIM/WITH_AIRBAG_SPC）
    与**回归基线**（3ms KE 5.70E-03、首帧 1.3mm、200ms 13h01m 正常终止）。
- **新脚本 `scripts/parity_audit.py`**：全卡逐字段对齐审计。展开 `*INCLUDE`；`*XXX_TITLE` 规范化并丢标题行；
  ID 类卡按 ID 配对（`--id-map DEFINE_CURVE:30000000` 处理 30M 段，且只对"确实加过偏移"的 ID 生效）；
  **曲线数据行按 20 字符定宽**解析（按 10 切会错位一批值——实测踩过）；`&` 续行标记剥离；
  文本字段/0-空/全零补白行自动降级为 INFO；`--ack "KW:field=N|key=id:N|*"` 三级登记；退出码 0/1 直接当门禁。
  实测把 200ms 正式 deck 的 48 个关键字审到 `MATCH=41 ACK=7 DIFF=0`。
- **新脚本 `scripts/damper_mass_gate.py`**：跑之前判 `C < 2m/dt`。按 `面积/4 × SECTION_SHELL.T1 × rho` 估锚点质量
  （支持 `--mass-csv` 覆盖）；输出每个锚点的 `m(g) / C_crit / C/C_crit / 判定 / 需补量`，`--emit` 直接吐 `*ELEMENT_MASS`。
  本例实测输出 10/10 FAIL、需补 `7.8E-05~9.6E-05` tonne/点，与修复方案一致。
- **P-S57（★ 新增）厚度取值坑**：项目早期用裸布 `0.3mm` 估节点质量 → `6.7~12.7 g`，比真值小 3 倍，
  把 `C_crit` 误算成 `0.027~0.051`（看起来"超 4~7 倍"，像别的问题）；按 section `T1=1.0mm` 得 `0.098~0.171`，
  与实测"C=0.1 健康 / 0.2 爆"严丝合缝。**动力学质量一律用 section 厚度。**
- **同步更新**：`SKILL.md`（铁律 4 条→5 条、链路图加 ③b 两道门禁与 ⑥b 抖动诊断、文档/脚本索引、Playbook 加 S5/S6 步骤
  与 ⑧ 抖动分支、description 关键词）；`07_pitfalls_index.md`（P-S49~P-S57 + 口诀 18~22）；
  `config.json`（版本 2026.10.31.1、hard_rules 41 条、gates 加阻尼稳定性/锚点目标质量/质量厚度口径/对齐审计要求）。

## 2026.10.30.1 (2026-10-30)
- **抖动根因定位与修复（P-S48）**：忠实重建 deck（全抄参考 Model_update_Move_Iter04）后 200ms 主跑
  （run_full）仍在上拉段可见抖动。诊断链：glstat 全局健康（KE 单调衰减、added mass 0.88% 恒定、
  车身刚体 rbdout 全程不动、接触/控制卡逐字段=参考、阻尼器未漏抄）→ **matsum 末块按 part 分解
  kinen：腔体 part 3（CAB1_CAVITY）KE=8.64 占总 KE 83%** = 腔体在织物层间无接触自由拍打。
  - 根因：gen_deck.py 曾以"腔体与织物同位初始穿透→质量暴增"为由把 part 3 剔出接触集（900106 只含
    2,4,5）；参考模型单面接触集**包含**腔体；且 `*CONTROL_CONTACT IGNORE=1`（参考同值）已使初始
    穿透安全，当初剔除理由不成立。
  - 修复：接触集恢复全部气帘零件（2,3,4,5）。验证：2ms 探针干净到时、added mass 0.04%、同 t=2ms
    全局动能 35.3→18.5（近乎减半）；200ms 全 run（run_full_fix）重启。
- **P-S47（LOAD_BODY_Z LCID 误用 + 时间单位 ms）**：第 1 字段是曲线 ID 不是零件集号，照抄参考
  `1 0.0098 0`；glstat/d3plot 的 t 单位是 ms（dt=4.95e-4 ms，ENDTIM=200ms，之前误当秒导致估时混乱）。
- config.json → 2026.10.30.1（hard_rules +2）；07 索引 P-S47/P-S48 + 口诀 16/17。

## 2026.10.29.3 (2026-10-29)
- **减抖三处修复 + SMP 渲染管线沉淀**（用户看主跑 d3plot 前 27ms "气帘乱飞舞/抖得不行"后提出三项修复）：
  - **修复 1（拉绳 SPC）**：拉绳沿 Z 向垂直动 → `Spring_swap.k` 末尾加 `*BOUNDARY_SPC_NODE` 10 行，
    气帘侧起点节点 `TX=TY=1（锁 X/Y）、TZ=0（Z 自由）`；生成前校验 cap 节点真实存在防空挂。
  - **修复 2（投影强制取上方）**：`proj_body()` 重写——所有 fallback 层级强制 `bz > z`（绝不取下方/同高节点），
    排序改为 `(水平距离 hypot(dx,dy), -Z)`（先近后高）；修 `pick` 取元组 `[4]`（bid）而非 `[3]`（bz 坐标）的 KeyError。
    回归校验：10 根拉绳 `dXY≤6mm`（近似竖直，原斜 Y 的 #9 变为 `dZ=+443.6mm` 垂直向上）。
  - **修复 3（参考几何）**：定位参考模型 `6P_CAB_update2.k` 的 `*AIRBAG_REFERENCE_GEOMETRY`（气帘全部节点号+零位坐标 copy，
    膜片静止形状软约束抑制 flutter）→ `gen_deck.py` 生成 `RefGeom.k`（115446 节点）进 deck（include 在 Spring 之前）。
  - **新坑位 P-S41~P-S46**（07 索引 + 09 §11/§12）：
    - P-S41（★★★）`*AIRBAG_REFERENCE_GEOMETRY` R10.1 按 **4 字段/记录连续流**读；6 字段（照抄参考旧版）→ 解析流错位 →
      Initialization `Error 30099 (INI+99) zero normal vector` 终止；指纹 = `KEY+457 only 4 expected` 满屏。
    - P-S42 SMP 启动必加 `memory=50000000 ncpu=2`（默认 20M words 报 Error 70021，本 deck 差 2.3M words）。
    - P-S43 后台任务里 solver 必须前台进程，`nohup ... &` 被静默杀（日志停在 license OK 似正常）。
    - P-S44 MPP d3plot 主文件仅单 domain 几何、状态文件用全局节点号 → SMP reader 越界；要渲染另跑 SMP 版。
    - P-S45 渲染专用控制卡关 `*DATABASE_EXTENT_BINARY` 输出 flag（STRFLG 等 5 个置 0，帧定长可读，物理零差异）。
    - P-S46 git-bash heredoc 里 Windows python 不认 `/e/...`，python 内用 `E:/` 风格路径。
  - **新增技能脚本**：`scripts/smp_d3plot.py`（SMP 单文件 d3plot reader，不解析连接段：状态0==g0 定位 + stride 校验；
    `--shake` 输出 vrms/vmax/dmean/dmax 抖动指标）、`scripts/render_fixed.py`（前 27ms 逐帧侧视图按|位移|着色 + 总览 + 速度 RMS 历程）。
  - **实证（run_fix_smp）**：三修复 + 4 字段 RefGeom 的 deck SMP 跑初始化零 Error，稳定求解至 t=7.5ms（d3plot01~04 写出，
    d3hsp 确认 RefGeom 被正常解析）后按用户要求停算；6 字段版对照初始化即 Error 30099——字段数是唯一变量。
    40ms 渲染验证未完成（用户停算），后续用 `smp_d3plot.py --shake` 对比 run_main1 前段定量确认抖动缓解。
  - `09_fresh_deck_build.md` 新增 §11（减抖三处修复）、§12（SMP 渲染跑配方与抖动验证管线）；`SKILL.md` 脚本/文档索引同步；
    `config.json` 升版本 `2026.10.29.3`、hard_rules 补 P-S41~P-S46。

## 2026.10.29.2 (2026-10-29)
- **补 09 文档主跑章节 + 坑位 P-S39/P-S40**（用户要求"先停计算、把技能和坑都沉淀"）：
  - `09_fresh_deck_build.md`：新增 §9「主跑启动配方与估时（P-S39/P-S40）」含 MPP n=2 完整启动命令、`dt≈4.95e-7s` 估时（200ms≈11h / 80ms≈4.5h）；
    §8 验证补充**主跑实证 run_main1**：200ms deck 后台稳定运行至 **t=40.0ms / cycle 80809**，稳定 dt、周期 d3plot flush、无 Error，后按用户要求干净中断（无残留进程）——证明 deck 跨时间尺度稳定。
  - `07_pitfalls_index.md`：追加 **P-S39**（主 deck ENDTIM=200ms 参考一致，与用户选项 80ms 不同；改 ENDTIM 整串替换定宽数）、**P-S40**（主跑估时陷阱 200ms≈11h 易超预期，先用探针+截断 ENDTIM 验证）；口诀补第 14 条。
  - `SKILL.md`：09 文档行坑位范围扩至 P-S40。
  - `config.json`：升版本 `2026.10.29.2`，hard_rules 补 P-S39/P-S40。
- **关键澄清（覆盖 2026.10.29.1 的中间态数据）**：弹簧/阻尼能量 4.8e4 是坏投影副产物，最终实测 `≈2.0e-20`；ΔZ 最终 `∈[+135,+378]mm` 均值 +225mm（非早先 +149.6mm 中间态）。均以 run_probe7 / run_main1 实测为准。

## 2026.10.29.1 (2026-10-29)
- **新增"从零组合 deck"阶段**（2026-10-26~29 onekey 攻坚沉淀，区别于 2026-10-28 的"换装法"）：
  - `references/09_fresh_deck_build.md`（新）：两干净模型（车身 `BIW_clean.k` + 气帘 `cab1_60ms.k`）
    组合、全参考 `Model_update_Move_Iter04` 的约束/材料/厚度/接触/上拉/点爆的完整配方。
  - `07_pitfalls_index.md`：追加 **P-S28~P-S38**，口诀补 3 条（顶部距离差定平移/同X邻域投影/混入孤立节点）。
  - `SKILL.md`：文档索引加 09、脚本索引补 `gen_deck.py` 项目实现说明、Playbook 加"从零组合"分支(2b)。
  - `config.json`：升版本 `2026.10.29.1`、参考模型加 `Model_update_Move_Iter04`、hard_rules 补 P-S28/29/30/31/33/34/35/36/37/38。
- **新增坑位（本阶段独家）**：
  - P-S28（★★★）拉绳锚点投影必须用"同 X 邻域 + Z 向上"，**禁全局最近点**（甩偏 200~600mm→mass increase）。
  - P-S29 BIW 文件混入约 33790 个气帘孤立节点 → 只留被车身壳单元引用的节点。
  - P-S30 重编号与坐标提取的 ID 基准必须一致（已重编号勿再减 NOFF）。
  - P-S31 平移只改 Y/Z，DY 莫错加到 X。
  - P-S32 节点行索引在 append 之后记录，防删错/留错节点。
  - P-S33 SET ID 冲突 → 车身集用 900101/900102/900103 避开气帘原有集。
  - P-S34 车身刚体不加全节点 SPC；锚点已在刚体内勿加 EXTRA_NODES_SET（防 20367）。
  - P-S35（用户铁律）平移量 DY/DZ 由"参考模型顶部距离差"回算一致，别肉眼对齐（本例参考 +522.0mm、工作 DZ=-270 时 +522.9mm）。
  - P-S36 弹簧/阻尼能量 4.8e4 异常已定位为投影缺陷副产物（全局最近投影 P-S28 反面 / cap ID 基准 P-S30 / 重复 EXTRA_NODES_SET P-S34 致拉绳斜拉数百 mm）；最终修正版 run_probe7 该能量回落至 2.0e-20≈0，与参考(~1e-4)一致。
  - P-S37 接触用 SINGLE_SURFACE_ID SSID=2 气帘作 slave（区别于 P-S26 S2S）。
  - P-S38 投影质量验收看 dXY≈0 锚点未横向甩偏（本例 10 根均 <64mm、dZ∈[+135,+378]mm），dZ 不必等于参考 tether dZ（顶部距离差 +522mm 由 P-S35 保证）。
- **实测背书**：`gen_deck.py`(项目副本) 生成 `main.key`+`main_probe.key`，2ms 探针(run_probe7)正常到达 `termination time=2.0003`(cycle 4041)、
  added mass≈2.78e-5(0.0004%)、`spring and damper energy=2.0e-20≈0`、无 mass-increase 终止、无 Error(仅良性 Warning)；
  10 根拉绳全部连通、dXY<64mm 近似竖直、dZ∈[+135,+378]mm；顶部距离差 +522mm 与参考一致。

## 2026.10.28.1 (2026-10-28)
- **新增整车整合/换装阶段**（cab1 → 参考 host 攻坚沉淀）：
  - `references/08_deck_integration.md`（新）：工装清算（P-S14 ★★★：cab1 自带 10×BOUNDARY_SPC_SET +
    10×CNRB"验证网格用"固定点，参考模型 SPC=0/CNRB=0；症状指纹=带拉带 0.081ms 爆/无拉带活/改缆长同 cycle 同簇节点）、
    整块删铁律（P-S15：孤儿数据行→forrtl severe(64) BIGRDSECT）、PART 定宽溢出（P-S16）、
    接触卡 4 行（P-S17）、D3PLOT 先到先得（P-S18）、+30M 段位偏移+七类 ID 审计（P-S19）、
    定宽字段原位映射（P-S20）、材料用参考 MAT.K（P-S21）、20367 重复锚定（P-S22）、
    时间读数陷阱（P-S23：0.081ms≠80.7ms，cycle×dt 交叉验证）、dt2ms 钉步基线+两段式跑法（P-S24）、
    块级二分定位（P-S25）、换装法+host 接线（P-S26：Vehicle.k 自带袋-身 S2S slave=SET_PART 2、
    排除 6P_CAB 防双重充气）、MPP n=2 提交模板（P-S27）。
  - `07_pitfalls_index.md`：追加 P-S14~P-S27，口诀补 3 条（整合清算/ID 审计/块级二分）。
  - `scripts/build_swap_clean.py`（新）：换装清洗一条龙——清算→+30M 重编号→曲线 30M 段映射
    （AIRBAG 定宽原位替换）→参考拉带最近贪心改接 9 boss cap（落选=充气口自动删）→host 组装→七类审计。
  - `SKILL.md`：链路加 ⓪ 整合换装段、铁律三条→四条（整块删+ID 审计）、索引/Playbook 同步。
- 实测背书：参考 host（03_Control_MOD+MAT.K+Vehicle.k+Spring 改接）+ cab1 清算版，
  2ms 探针 `*** termination time reached ***` 正常终止、0 错误、质量缩放 0.19%
  （修复前同配置 0.081ms mass increase 1.13E+8）；60ms 长跑已启动（run_swap_long）。

## 2026.10.22.1 (2026-10-22)
- **新建技能**，沉淀 NEW_CAB 气帘"从 K 交付 → 计算求解 → 后处理"全链路坑点。
- 主入口 `SKILL.md`：一句链路、何时用、三条铁律、文档/脚本/资产索引、换项目 Playbook。
- `config.json`：求解器/版本/MCP profile/d3plot 二进制布局/门禁阈值/硬规则。
- `references/`（7 篇）：
  - 01_kfile_handoff.md —— K 交付衔接铁律（eid 漏写 P-S01 / 飞丝 P-S02 / 格式 P-S03 / 自由边 P-S04）
  - 02_solve_setup.md —— 求解器配置（R10.1 非 R13 P-S05 / profile 必填 P-S06 / DT2MS 负值 P-S07 / 质量缩放 / 网格硬条款 / 输出文件速查）
  - 03_constraints_tether.md —— 约束/拉带固定/锚点（固定双证 / CNRB+SPC spcforc 不报反力 / 参考模型其实无 SPC P-S11 / 锚点漂移 P-S12）
  - 04_postprocess_d3plot.md —— **d3plot 二进制逆向布局**（主/状态文件 int32 连接区 P-S09 / 固定逐位校验 P-S10 / 时刻 RMS↔KE 标定 P-S13）+ 健康门禁 + 漂移诊断
  - 05_quick_setup.md —— 快速设置清单（路径/venv/典型命令序列/易错核对）
  - 06_specs.md —— 《DEP_2012001 规范 1.1》关键条款引用（DT2MS、质量缩放<3%、网格硬条款、单位制）
  - 07_pitfalls_index.md —— 全链坑位总索引（求解阶段 P-S01~P-S13 + 跨技能坑位速查表 + 避坑口诀）
- `scripts/`（原创 3 + 镜像 4）：
  - d3plot_reader.py —— 逆向读主/状态 d3plot（坐标/速度/加速度/位移、固定节点校验、腔体包络体积、各 part 平移），numpy 直读无需 GUI
  - k_health_gate.py —— glstat/matsum/abstat 自动判 6 道门禁，退出码 0/1
  - render_deploy.py —— 部署过程 + 终态四视图 + 位移云图，自动标定时刻，中文字体
  - qa_kfile_strict.py / fix_kfile_format2.py / geom_match_check.py / tether_conn_check.py —— 镜像自 CURVEtoMESH 技能（K 衔接门禁）
- `assets/`：render_deploy_process.png + render_t20_detail.png（NEW_CAB 实测示例）
- 实测背书：NEW_CAB 加 14 拉带固定端重算，20ms 正常终止、质量增加 0.0002%、沙漏 0、能量比 1.00001、
  0 触底、拉带固定双证（rbdout 零位移 + 1800 固定节点逐位不动）、abstat 35.2L/1.028bar/16.07g@760K 自洽。
