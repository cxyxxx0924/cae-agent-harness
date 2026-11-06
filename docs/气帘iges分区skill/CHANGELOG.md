# CHANGELOG · qilan-iges-partition (气帘 IGS 四分区)

## 2026-10-21 (1) — 首版沉淀，NEW_CAB 全链路回归通过

- 来源：NEW_CAB（`Drawing0904ZHEDIETU.iges`，828 线）四分区实战 v1→v8。
- 交付：BELT 119 / CAVITY 78 / SEAM 59 / TETHER 572 → `newcab_partitioned.hm`。
- 脚本 11 个（t01/t02/p03/p03b/p04/p05/p06/t07/t08/q09/q10），全部认 `WORKDIR` 环境变量，
  输入输出 hm 名可用 `HM_IN`/`HM_OUT` 覆盖，零项目硬编码。
- 坑位 P35–P42 入库；**P40 作废旧结论**（hmbatch `-tcl` 中文路径实测可 source，
  2026.0.0.27；当年 readfile 失败的锅被错记到中文路径上）。
- 新坑 P39：`*readfile` 目标不存在 → hmbatch 整体中止且**报告文件不生成**，
  看旧报告会误判成功；对策=跑前确认输入存在 + 跑后查报告 mtime/exit code。
- 回归证据：p05/p06/q09 重跑 counts 逐位重现；t07 重搬 id 集合逐一比对一致；
  t08 独立回读 VERIFY_FAIL=0，抽样线长与分区前导出逐位一致。
- 遗留（图纸固有，非缺陷）：气腔顶边充气口根部 410mm 缺口（x 478→888）；
  凸台区/布带/气腔既有短边 <3mm（与连接修复无关）。

## 2026-10-21 (2) — v9 极简轮廓修正全量沉淀

- 来源：用户 2026-10-21 下午复核 v8 产物，要求**分区曲线只为计算模型服务 = 裁切建面 /
  Surface Edge 的闭环边界轮廓子集**，不必要的细小 Curve / 特征装饰 / 内部折叠线不放进来，
  风格参考 `E:\work\AI_CAB\气帘CAD数据\cab1.hm`（最少量外轮廓环，口部布带环与气腔环靠内平行）。
- 修正：BELT 凸台顶边盖线 L822/L525/L767 从 TETHER 回归、肩部小竖线 L262/L263/L316/L317/L370/L371
  归还 TETHER、充气口只留最外轮廓（70+ 内部折叠线 + 口内 L254 全 DROP）；
  CAVITY 经口部内壁 L134/L471/L166 + 气道回路闭合；SEAM 只留 4 哑铃（气道线归 CAVITY、平行重复 DROP）；
  TETHER 左下方排气口 L5/L37/L820–828 移出。
- 最终计数：BELT 36 / CAVITY 92 / SEAM 43 / TETHER 567（合计 738，90 条不参与分区留 `lines0`）。
- **新增脚本（全部认 `WORKDIR`）**：
  - `v9_apply_fix.py` — 应用修正清单 + 端点搭接连通性 QA，读 `newcab_classify8.json`（规范 v8）
    → 写 `classify_v9.json`/`classify_final.json`，源可用 `V9_SRC` 覆盖；幂等（`if lid in C` 保护）。
  - `v9_recon.py` / `v9_recon2.py` — 四问题区域线清单侦察（P1a~P4 / A~E），复现"为什么这么改"。
  - `v9_render.py` — 问题区域特写渲染（带 id 标注），出 `v_v9_port/righttop/seamgas/exhaust.png`。
  - `run_v9.sh` — v9 修正一键链（7 步 + 人眼确认暂停），调用上面脚本 + p06/t07/t08。
- **文档**：`references/05_v9_minimal_contour.md`（原则 + 四分区修正清单 + 落地清单 + 最终计数 + 坑位 P43/P44/P45 + 复现命令 + 配套脚本清单）。
- **PATCH**：`t08_verify_partitioned.tcl` 加 `UNASSIGNED={lines0,DROPPED}` 跳过未参与分区的线，
  分区总数只算 4 个命名 comp，v8/v9 都 `VERIFY_FAIL=0`（修掉 v9 刻意留 90 条的误报）。
- **坑位 P43–P45 入库**：P43 基文件变体（`classify_prev.json` 9 线差异）审计对不上；
  P44 脚本自身副作用导致重跑 KeyError；P45 验证误报（已修）。
- 验证：`run_v9.sh` 跑通，`partitioned.hm` 独立回读 VERIFY_FAIL=0，4 comp id 集合与 json 逐位一致。
- 本技能现含 17 个脚本（run_all.sh 1 + v8 链 11 + v9 修正/诊断/编排 5） + 6 篇 references + SKILL.md + run_all.sh + run_v9.sh。

## 2026-10-21 (3) — v10 气腔口部开环修正

- 来源：用户截图复核 v9——其他三环无问题，唯一气腔环在充气口**不是往回折形成封闭区域**
  （气道回路整体红叉叉不要）；气腔环应**跟布带环相约在最上面那个斜的线段上**
  （L471/L166 沿领圈内侧平行爬到楔顶封闭端 (834.89,497.37)=布带 L249/L196 交点停止，
  右支开口停止）；网格意义=充气口处全是气腔面区域，与布带层自然过渡（参考 cab1）。
- 修正：气道回路 9 线从 CAVITY 移出（L161/L162/L163 左下降壁、L164 底壁、L233/L234 右端、
  L159 右竖降、L157/L158 平行重复）。
- 最终计数：BELT 36 / CAVITY **83** / SEAM 43 / TETHER 567（合计 729，99 条不参与分区）。
- QA：CAVITY=1 组分+恰好 2 自由端；L166.sp 与布带 L249.sp 重合 d=0.00（楔顶精确相约）。
- 新增：`scripts/v10_cavity_open_port.py`（从规范 v8 一次应用 v9+v10 清单，幂等，`V10_SRC` 可覆盖）
  + `references/06_v10_cavity_open_port.md` + SKILL.md §7.6 + 坑位 **P46**（气腔口部开环规则）。
- 验证：p06/t07/t08 重跑，`partitioned.hm` id 集合与 json 逐位一致，VERIFY_FAIL=0。
- 本技能现 18 个脚本 + 7 篇 references。

## 2026-10-21 (4) — v11 气腔口部白链回归（当前交付态）

- 来源：用户 HyperMesh 截图复核 v10——口部白色未归档线里有一条**连续连接的链**，
  天然一路延伸到最斜上方蓝色（布带）封口斜线段处（充气口封口线段处），
  "加上这一下段就完美了"。v10 把整条气道回路 9 线全 DROP 属于**过度删除**：
  红叉叉指的只是平行重复线，主链是气腔在口部的真实内壁轮廓。
- 几何实证：链 = L157→L158→L159→L234→L233→L164→L163→L162→L161（922.7mm，
  内部最大间隙 0.29mm）；链首距气腔右支自由端 L167.ep 1.0mm，
  链尾距楔顶 (834.89,497.37)=布带 L249/L196 交点=气腔 L166.sp 1.0mm。
- 修正：V11_CHAIN = [157,158,159,161,162,163,164,233,234] 归还 CAVITY。
- **最终计数（v11）**：BELT 36 / CAVITY **92** / SEAM 43 / TETHER 567 = 738
  （90 条不参与分区留 lines0）。
- QA：CAVITY 3 组分（主环 83 + 链上段 6 + 链下段 3），链与主环间 0.29~1.0mm
  图纸固有微缝（建面/共节点阶段桥接，分区阶段几何零改动）。
- 新增：`scripts/v11_cavity_port_chain.py`（v8 起点一次应用 v9+v10+v11 清单，幂等，
  `V11_SRC` 可覆盖）+ `references/07_v11_cavity_port_chain.md` + SKILL.md §7.7
  + 坑位 **P47**（白线≠垃圾：DROP 前先扫连通性，分清主链 vs 平行重复线）。
- 验证：p06/t07（ALL_OK=1，4 comp id 集合与 json 逐位一致）/t08（VERIFY_FAIL=0）重跑通过。
- 本技能现 19 个脚本 + 8 篇 references。

## 2026-10-21 (5) — v12 气腔口部只加 L161（当前交付态；v11 被推翻保留作教训）

- 来源：用户 HM 截图红虚线标注——"你又倒退了啊，刚才那一步只差一根线了……沿着
  红色的虚线方向往上走，一直到右上方最上面那个缝，充气口封口线段……只要加这条线，
  退回原来的改"。v11 把 9 线整链回归 = 过度修复。
- 那根线 = L161：(531.80,335.08)→(835.36,496.49)，343.8mm，与气腔 L166 全程平行
  （垂距 ~1.0mm），上端距封口线段 L249 右端 1.0mm。
- 修正：`scripts/v12_add_l161.py`（v8 起点一次应用 v9+v10+v12 清单，幂等，V12_SRC 可覆盖）
  + `references/08_v12_add_l161.md` + SKILL.md §7.8 + 坑位 **P48**（只加用户指的那一根，
  勿整链带回；先渲染同视角对比图逐位吻合再动手）。
- **最终计数（v12）**：BELT 36 / CAVITY **84** / SEAM 43 / TETHER 567 = 730（98 条不参与 lines0）。
- QA：CAVITY 2 组分 = 主环 83（L166.sp 与布带封口 d=0.00 / L167 开口）+ L161 单根。
- 验证：p06/t07（ALL_OK=1）/t08（VERIFY_FAIL=0）重跑通过。
- 本技能现 21 个脚本 + 9 篇 references。

## 2026-10-21 (5) — v13 气腔封口链闭合 + 顺滑追链方法论（chain_trace.py）

- 来源：用户 2026-10-21 18:04 反馈。v12 被推翻：L161 是**左边**错加的平行死线；
  正确形态 = **右边 X 大侧**从 L167 沿编号顺滑链（L168→169→170→172，实测端点
  0.00/0.00/0.00/0.06mm 衔接）通上去，封在封口段 L188/L196 上。
- v13 = v12 + delta：`CAVITY -= {161}`，`CAVITY += {168,169,170,172,188,196}`。
  封口线段并入气腔环（用户要求，方便下一步网格切割），气腔环于充气口闭合。
- 交付态：**BELT 34 / CAVITY 89 / SEAM 43 / TETHER 567 = 733**（95 条留 lines0）；
  t07 ALL_OK=1，t08 VERIFY_FAIL=0（lines0 跳过）。L172→L188 13mm 图纸缝留建面桥接。
- 新工具 `scripts/chain_trace.py`：沿顺滑方向追链（编号顺序 + 方向连续 + 偏好方向
  三因子打分；种子两端都接线时优先走「邻居线号=seed+1」方向）。用户明示此方法
  要作为技能沉淀："要会这么寻找啊，就沿着它顺滑的方向去寻找啊"。
- 新脚本 `scripts/v13_cavity_seal_chain.py`（幂等累积，V13_SRC 可覆盖）、
  `scripts/v13_render.py`（绿粗=新增链、橙虚=L161 已移出）。
- 坑位 P49-P52 入库：**P49 t08 漏设 WORKDIR=读旧报告假 PASS**（v13 首次校验实栽，
  读到 v12 旧计数 36/84）；P50 零长度退化线 L171；P51 端口近重合线团（容差追链
  拐进 L198→L161 旁支，权威判据=精确衔接+编号连续）；P52 QA 0.05mm 容差把
  0.06/0.23mm 真衔接判成开环（容差边界效应，非分类错误）。
- 参考：`references/09_v13_seal_chain_and_chain_trace.md`；SKILL.md §7.9（§7.8 v12 标记被推翻）。

## 2026-10-21 (6) — v14 剔除气腔内三个小圆圈（拉带组符号残留）

- 来源：用户 2026-10-21 19:01 标注截图（红字"移走"）。TETHER 组里三个小圆圈
  独立漂浮在气腔内部，面积很小 → 从拉带组移走。
- 几何实证：三者为 **~6.1mm 退化重复微段**（bbox 2.8×5.3mm，同一小段重复 2/8/2 次）：
  A=L229+L230 @(580.1,260.3)~(582.9,265.6)；B=L231/232/235/236/239/240/243/244
  @(894.1,263.6)~(896.9,268.9)；C=L247+L248 @(878.3,320.7)~(881.1,326.0)。
  互相独立、不连任何环 = 图纸符号残留。
- 识别方法：已归档类端点融合 union-find（TOL 0.3mm）→ 小 bbox 分量过滤 →
  「集合内互为重复线」= 符号残留强判据。
- v14 = v13 + delta：`TETHER -= 12 条`（→ lines0）。
- 交付态：**BELT 34 / CAVITY 89 / SEAM 43 / TETHER 555 = 721**（107 留 lines0）；
  t07 ALL_OK=1；t08 COUNT 全 OK、VERIFY_FAIL=0。
- 流程强化（用户明示）：**发图说明必须先渲染带坐标标注的确认图核对再动手**
  （本次 out/v14_confirm_coords.png 与用户标注逐位吻合后才改）。
- 参考：`references/10_v14_remove_tiny_circles.md`；SKILL.md §7.10（§7.9 标记被迭代）。

## 2026-10-21 (7) — 端到端升级：原始 IGES → 四分区 一键链（run_full.sh + t00 + p07）

用户要求：「从拿到原始 iges/igs 等 CAD 文件到分区得到布带环、气腔环、缝线环、拉带
这四组的**完整链路**沉淀升级到本技能」。

新增：
- `scripts/t00_import_iges.tcl`（**S0 原始 CAD 导入**）：`*geomimport "iges_altair"`
  （失败退回 `*import`）+ 2026 profile 加载 + 写盘前 `file delete` + 导入统计报告。
  实测 `newcab.iges` → 828 线 / 1 comp / curves.hm。
- `scripts/p07_report.py`（**S5 终检报告，通用无硬编码**）：四组计数、每组 bbox、
  连通组分、**小分量（<30mm 疑符号残留）单独列出**、组内重复线对、主环自由端
  最近邻提示、未归档组分统计 → `out/final_report.txt`。
- `scripts/run_full.sh`（**端到端一键链 S0–S8**）：断点续跑（产物存在则跳过，
  FORCE=1 强制）；`IGES/SEED/DELTA/HM_IN/HM_OUT/SKIP_CONFIRM` 全环境变量，零硬编码；
  DELTA 支持 none/v9/v10/v12/v13/v14；S8 前自动 rm 旧报告（P49）。

修复（真 bug，端到端测试暴露）：
- **P53**：delta 脚本 `*_SRC` 传裸文件名会 `FileNotFoundError`（原本按绝对路径打开）
  → v9/v10/v12/v13/v14 全部改为非绝对路径自动拼 `BASE`（out/）。
- **P54**：`set -euo pipefail` 下 `p07_report.py | head` 触发 SIGPIPE 使整链 exit 120
  → 报告落文件后用 grep 回显摘要。

文档：SKILL.md 重写为端到端入口（§0 一句话链路 / §3 S0–S8 表 + 单步命令 /
§5 终检三项 / §6 坑位 P35–P55 / §7 版本链 v8→v14 / §8 换项目 Playbook /
§9 2026 批处理铁律 / §10 目录）；config.json 升 2026.10.21.2；
assets 加 v14 确认图、结果图、final_report.txt。
P55 入库：TETHER 天然多组分（v14 111 个组分），拉带按片验收不看"主环"。

**端到端回归（2026-10-21 19:15，全新工作区 `work/newcab_test`）**：
IGES → t00(828/1comp) → t01 → t02 → SEED v8 → DELTA=v14 → p05/p07 → p06 →
t07(ALL_OK=1) → t08(COUNT 全 OK / TOTAL 721 / VERIFY_FAIL=0)，
与既有 `work/newcab` 交付态逐位一致。

## 2026-10-23 (3) — 全自动模式 + 学到的气帘研判先验（通用技能模块）

- **动机**：用户要求"自动学会研判曲线分组"，把视觉/功能/组别/连贯性综合起来，
  识别过程全自动（不靠人工逐步确认），并沉淀为通用技能模块。
- **方法（视觉+功能+连贯性 先验）**：
  1. 自动判定坐标平面 X-Y / X-Z（P42 填坑：5P-BAG 是 X-Z）。
  2. 端点焊接 8mm → 连通分量；切线连续度（P36 端点类型配对判据）→ 连贯性特征。
  3. 逐线几何+视觉+功能特征：长度/径向壳层(shell_rank)/凸包距离/长宽比/位置/
     分量大小/角度…，**全部几何量，不依赖线号 → 跨图通用**。
  4. 以金标准 `newcab/partitioned.hm`(v14, BELT34/CAVITY89/SEAM43/TETHER555/lines0 107) 为
     **监督训练样本**，拟合决策树（depth=10, 100% 拟合）作为"学到的研判先验"，
     序列化进 `tree_model.json`（89 节点，零 sklearn 运行时依赖，纯 Python 遍历应用）。
  5. `auto_partition.py`：特征提取+树推理 → `classify_final.json`（仅 4 类，lines0 不写入）。
- **交付验证（目标图 = `Drawing0904ZHEDIETU.iges`，即 NEW_CAB 源图）**：
  `run_auto.sh` 一键 S0→S2→AUTO→p06→t07→t08，**VERIFY_FAIL=0，TOTAL 721**，
  与金标准 **逐线 721/721 精确一致**。
- **跨图泛化（同一棵树，零重训，跑 5P-BAG 338 线 X-Z）**：CAVITY/SEAM/内部
  结构泛化良好；**BELT（最外闭环）与最外硬件（充气口/凸台）在半径上同层**，
  该语义边界属"语义归人"范畴，新图仍可借既有 S3–S4 delta 精炼（与技能原铁律一致）。
- **新增脚本（全部认 `WORKDIR`）**：
  - `featurize.py` — 通用特征提取（导出 `compute_features(workdir)`，可被 import）。
  - `auto_partition.py` — 自动四分类（加载 `tree_model.json`，输出 `classify_final.json`）。
  - `tree_model.json` — 学到的研判先验（决策树，可经 `train.py` 用新金标准重训）。
  - `render_auto_partition.py` — 按 classify JSON 渲染分区图（自动判平面）。
  - `train.py` / `featurize.py` 配套训练脚本（特征→树，导出规则文本+模型）。
  - `run_auto.sh` — **端到端全自动一键链**（无需人工确认）。
- 修复（真 bug）：`train.py` 导出 `tree_model.json` 时 `leaf` 字段为 numpy.bool 不可
  序列化 → 转原生 bool；`| head` 触发 SIGPIPE 截断模型文件（P54 再中）→ 输出落盘规避。
- 文档：SKILL.md 新增"全自动模式 S0→AUTO→S8"与"学到的研判先验"两节；本条目入库。

## 2026-10-23 (4) — 跨图泛化实测：5P-BAG 基线 + "语义归人"边界结论

- **任务**：用同一棵先验树零重训跑 `E:/work/AI_CAB/5P-BAG.igs`（338 线，X-Z），看泛化实况，决定是否补"外包络 BELT"增量规则。
- **基线结果**：`run_auto.sh` 在全新 `5pbag_auto_test` 工作区 →
  `BELT=45 / CAVITY=50 / SEAM=54 / TETHER=147 / lines0=42`；四类 COUNT 全 OK。
  （`VERIFY_FAIL=1` 仅为未分配组件命名边角：5P-BAG 导入后 42 条未分配线落在 IGES 原始层
  `lvl10000` 而非 `lines0`，被计入总数；非分类错误。）
- **泛化实况**：CAVITY/SEAM 与内部结构合理；**最外层大包络整圈被误判成 TETHER**——
  5P-BAG 外包络是多短段+间隙，决策树把"短+外圈→TETHER"规律套上（newcab 训练时 TETHER 多为短硬件线）。
- **补规则尝试（全失败）**：①半径/凸包距离阈值——气帘细长 82% 线贴凸包，分不出外包络；
  ②切向闭合环追踪——短段有间隙，识别出 0 个闭环；③焊接+角度跨度最大分量——碎片化成多块，挑错成内部分量。
  **且该规则把 newcab 的 10 条外接硬件 TETHER 误并进 BELT，使 721/721 掉到 695/721。**
- **决定：不给自动流水线打脆性增量规则**（否则回退认可结果）。外包络 vs 外接硬件属"语义归人"，
  按 §2 交互铁律 + 既有 S3–S4 幂等 delta 人工精炼；`scripts/delta_belt_envelope.py` 仅作诊断实验保留
  （默认 `--dry` 不改文件，未接入 `run_auto.sh`）。
- 文档：SKILL.md §0.5 泛化边界补 5P-BAG 实测 + 决定；`references/11_auto_learned_prior.md` §4 扩写为
  4.1 实测 / 4.2 失败证据 / 4.3 决定；本条目入库。

## 2026-10-23 (5) — cab1 金标准并入 + 双金标准联合先验（修正 5P-BAG 包络误判）

- **动机**：用户提供第二份人工金标准 `E:/work/AI_CAB/气帘CAD数据/cab1.hm`（5P-BAG 图的人工分组），
  要求据此"增加金标准规则、反复自训"，自动产出目标文件 `cap1.hm`，自建标准、自我完善、增强泛化。
- **cab1.hm 结构揭秘**：曲线分在 5 个 comp——`component1(7)/component2(2)/component3(56)/component4(249)`
  + `_5P-BAG_Wireframe(24, 参考层→lines0)`。用**几何+视觉综合研判**定映射（贴凸包=最外闭环、闭合环带、
  内层散弧、局部硬件簇）：`component1→BELT / component2→CAVITY / component3→SEAM / component4→TETHER`
  （工具 `dump_comp_lines.tcl` + `render_per_component.py` + `analyze_components.py` 佐证）。
- **方法**：从 cab1.hm 同源提取采样点与金标签（同一 line-id 序，保证与 t07 对齐）→ featurize
  → 与 newcab 金标准**联合拟合** `train_joint.py`（155 节点，双图 100%）。
- **验证**：
  - NEW_CAB 逐线 **721/721，VERIFY_FAIL=0**（认可结果零回退）。
  - cab1 逐线 **314/314 精确一致**，`cap1.hm` 与人工 `cab1.hm` 五组逐 id 相同，VERIFY_FAIL=0。
  - 5P-BAG（同图，自动导入 `5P-BAG.igs`）现在 **BELT=7/CAVITY=2/SEAM=56/TETHER=249**，与人工 cab1 吻合——
    早期"外包络整圈误判成 TETHER"被修正。
- **根因/结论**：BELT-vs-最外硬件这道"语义归人"缝，**根本解法是增加金标准联合拟合**（把正确切分教给先验），
  而非纯几何硬阈值（早期三条路线全失败、且回退 newcab 到 695/721）。
- **新增脚本**：`train_joint.py`（多金标准联合训练）、`feat_driver.py`（通用特征驱动）、
  `dump_comp_lines.tcl`/`render_per_component.py`/`analyze_components.py`（组件→类别研判工具）。
- **t07 加固**：搬完 4 类后把未分配线统一收入 `lines0`，t08 据此排除 → 修掉 5P-BAG/多 comp 图纸的
  VERIFY_FAIL 命名边角误报。
- **默认先验升级**：`tree_model.json` 更新为双金标准联合版（155 节点）；旧单金标准备份 `tree_model_v1_newcab.json`。
- 文档：SKILL.md §0.5 重写为"双金标准监督"叙事；references/11 §3/§4/§5 更新；本条目入库。

## 2026-10-23 (6) — cab3（6P）盲测暴露不一致 → 人工金标准并入 + 三金标准联合先验

- **动机**：用双金标准先验盲测新图 `S31 CAB_AIR BAG ASSY_6P_20240827.iges`（911 线，X-Y）：
  基线 BELT=83/CAVITY=236/SEAM=20/TETHER=461/lines0=111，结构大体合理，但放大检查发现
  **同类件不同判**（顶排 9 个充气口"房子+方框"被拆成 TETHER/CAVITY/lines0 三种；
  右下"圆环+杆"有 CAVITY 与 lines0 两种分法；中部楔形区整体未分配）。用户据此手工精分出第三份金标准。
- **cab3.hm 结构**：911 线 = `component1(67)/component2(109)/component3(40)/component4(586)`
  + `_lines0_Wireframe(109→lines0，用户已按此命名)`。映射（几何聚合+逐组件渲染研判）：
  `component1→BELT`（最外整圈闭合包络）/ `component2→CAVITY`（大气腔环+右下圆环+杆腔室）/
  `component3→SEAM`（3 个内层孤立闭合环）/ `component4→TETHER`（顶排充气口+右簇+密集短线网，
  586 条 88% 闭合、len_med≈0.012、ntan≈17）。**教训复现**：勿只信视觉第一眼，用 dhull/闭合度/半径带/线长做几何判据。
- **方法**：从 cab3.hm 同源提取采样点+金标签 → `train_joint.py` 的 `DRAWS` 加入 cab3
  → **三金标准联合拟合**（POOLED 2077 条，depth=20，269 节点，三图 hold-in 均 100%）。
- **验证（全部逐线 MISMATCH=0）**：NEW_CAB **721/721**（零回退）；cab1 **314/314**；
  cab3 **802/802**（`cap3.hm` 与人工 `cab3.hm` 五组逐 id 相同，VERIFY_FAIL=0）。
  5P-BAG 回归仍 BELT=7/CAVITY=2/SEAM=56/TETHER=249。
- **默认先验升级**：`tree_model.json` 更新为三金标准联合版（269 节点）；
  旧版备份 `tree_model_v2_joint_cab1.json`（双金标准）/ `tree_model_v1_newcab.json`（单金标准）。
- 文档：SKILL.md §0.5/§10、description 更新为三金标准叙事；references/11 §3/§4 同步；本条目入库。

## 2026-10-23 (7) — 金标准全部沉淀进技能目录 golden/（技能自包含闭环）

- **动机**：用户要求"目前累积沉淀的金标准全部沉淀到技能文件夹下"——此前三份金标准的标签/特征散在
  项目工作区，`train_joint.py` 指外部绝对路径，技能文件夹复制后无法独立重训。
- **新增 `golden/` 目录**（每份金标准 = 金标签 + 同源 features.json + 源图纸 + 出处 source.txt）：
  - `golden/newcab/`：classify_v14.json（721 分类）+ features.json（828 线）+ source.iges
  - `golden/cab1/`：cab1.hm（用户手工分组）+ golden_line_comp.json（314 分类）+ features.json + source.iges
  - `golden/cab3/`：cab3.hm（用户手工精分）+ golden_line_comp.json（802 分类）+ features.json + source.iges
  - `golden/README.md`：训练集总览（POOLED 2077 条）、重训流程、新增第四份金标准五步法
- **train_joint.py 改为技能内相对路径**（`HERE/../golden`，`os.path` 计算，可移植）→ 重训验证：
  与外部路径版**完全一致**（269 节点，三图 hold-in 100%）。
- **自包含端到端证明**：全新工作区 + `golden/cab3/source.iges` + `run_auto.sh`（默认树）→
  VERIFY_FAIL=0；与人工金标准逐线 798/800 一致（99.75%）——差异 4 条为导入会话差异：
  L774/L778（金标准 BELT→判 CAVITY，BELT/CAVITY 边界灰带）、L342/L781 落 lines0。
  同会话内复现仍 802/802。两个口径已写入 references/11 §5。
- **踩坑（方法论）**：跨 ID 空间比对分类结果时，端点几何匹配脚本混用 int/str 键会产出大量假 disagree
  （本次一度显示 687 个，实际 4 个）——**比对前先显式验证两侧键空间与键类型**。
- 文档：SKILL.md §10 加 golden/ 树；references/11 §5 改写在 golden/ 布局 + 双口径复现精度；本条目入库。

## 2026-10-31 (8) — 三图交叉验证驱动重做全自动先验（v1 → v2），LODO 0.763 → 0.957

- **触发**：用户给出统一训练集 `E:/work/AI_CAB/分区训练/{igs,hm}`（三套"原始 IGES + 人工分区 .hm"），
  要求"自动分区无需人工干预"，并明确"可以用这三组数据做交叉验证"。
- **同源核对（先做，避免泄漏）**：md5 比对发现
  `cab1.igs == 5P-BAG.igs`、`cab2.iges == golden/newcab/source.iges`（NEW_CAB/Drawing0904）、
  `cab3.iges == S31_..._6P_...iges`。即三套数据 = 已知三张图。
  → v2 训练集定为 cab1+cab2+cab3；`golden/newcab/`（v14）降级留档不进训练（同图重复会泄漏）。
- **先证伪 v1**：留一图交叉验证（LODO）v1 仅 0.761/0.706/0.823，**两张图低于"全猜 TETHER"朴素基线
  (0.793/0.769/0.731)**；特征消融（去绝对位置、换 RandomForest）仍在 0.65~0.83。
  病根：绝对位置特征 + 凸包距离（气帘细长，82% 线贴凸包）+ 按最大线长归一。
- **v2 重做**（新文件，不动 v1）：
  - `featurize2.py`：轮廓内向深度（栅格化→闭运算→填洞→距离变换）、切向连续链（ch_len/ch_dep/ch_ext…）、
    局部密集度（dens_cnt/cl_size）、图内百分位（rk_*）+ dep_rel。32 维，全部尺度无关。
  - `train_v2.py`：两阶段随机森林（symbol vs structure → BELT/CAVITY/SEAM）+ 物理规则
    `ch_dep>0.055 & ch_len<0.90 → SEAM`（三图零有害误判）；导出 `tree_model_v2.json`（4.9MB，纯 Python 推理）。
  - `auto_partition2.py` + `run_auto2.sh`：端到端一键链，零 sklearn 运行期依赖。
- **LODO 结果**：cab1 0.971/0.919、cab2 0.951/0.926、cab3 0.949/0.964，
  **平均条数 0.957、结构长度加权 0.936**（v1 平均 0.763）。
- **端到端（全新工作区从原始 IGES 导入）**：三图全部 VERIFY_FAIL=0；
  与人工金标准逐线：cab1 **314/314 全对**、cab2 708/714、cab3 797/802；
  差异全部是"金标准 lines0 → 判成某类"（把本不分类的散碎线也归了类），视觉无害。v2 不产 lines0 残线。
- **新增通用工具**：`t09_dump_comps.tcl`（comp→线 id JSON）、`ga_analyze_comps.py`（聚合表+逐组件渲染，
  修正 X-Z 投影 bug）、`ga_build_golden.py`（映射表→金标签）、`cv_lodo.py`（LODO，v1 留档对照）。
- **金标准库**：新增 `golden/cab2/`（cab2.hm + golden_line_comp.json + features2.json + source.iges + source.txt）；
  cab1/cab3 补 `features2.json`；重写 `golden/README.md`（v2 布局 + LODO 基线 + 五步法 + 铁律）。
- **文档**：SKILL.md §0.5 重写为 v2（含 LODO 表与已知边界），原 v1 降为 §0.5b 留档；description/§10 同步；
  新增 `references/13_vision_prior_v2.md`（数据同源核对 / 映射判定 / 特征推导 / 模型 / 结果 / 坑位）。
- **踩坑**：① `cab2.iges` 与 newcab 源图 md5 相同（不做核对就会交叉验证泄漏）；
  ② compute_features 返回 int 键、features.json 是 str 键，混用出假差异；
  ③ cab1 是 X-Z，渲染器若固定取 (x,y) 会画成一条线；④ 聚合表 `midr` 对长折线不可靠，定案靠渲染图。

## 2026-10-31 (9) — 纠错：cab2 的 L5（18 条）实属 lines0，金标准重解构后重训（LODO 0.957 → 0.961）

- **触发**：用户指出 `cab2.hm` 里被我判成"斜向拉带"并入 TETHER 的 `L5`（18 条）**弄错了，实际属于 lines0**，
  并亲自更新了 `E:/work/AI_CAB/分区训练/hm/cab2.hm`（125521 B，`_lines0_Wireframe` 114→132，`L5` 消失）。
- **重新解构**（新工作区 `work/train4/cab2`）：`t02` + `t09` 重导 → 6 comp 变 5 comp，总数仍 828 线、
  line id 空间逐一对应（仅 old/new 差集为空）→ 几何未变，**只需改标签**。
- **根因核对（用户判断成立）**：这 18 条 `len_diag` 仅 0.009~0.014（≈20~30 mm）、`dens_cnt` 15~18、
  `cl_size` 6~8，`ch_len` 0.217 —— 是拉带旁一簇首尾相接的碎线，不是连续板带。
  此前它们以 TETHER 身份参与监督，等于在教模型"碎线簇可以是结构件"。
- **重训**：`ga_build_golden.py --map "L1=BELT,L2=CAVITY,L3=SEAM,L4=TETHER,_lines0_Wireframe=lines0"`
  → cab2 = BELT35/CAVITY87/SEAM43/TETHER531/lines0 132（分类 696）；`features2.json` md5 与修订前**完全一致**
  （6e5d0abf…，零重算）→ `train_v2.py` 重导出 `tree_model_v2.json`。
- **LODO（重训后）**：cab1 0.971/0.919、cab2 **0.964/0.944**、cab3 0.949/0.964，
  **平均 0.961 / 结构长度加权 0.943**（修订前 0.957/0.936）；cab2 的 TETHER 长度召回 0.92→0.97。
- **端到端复跑**：`v2_cab1/2/3` 全部 `VERIFY_FAIL=0`；逐线对金标准 cab1 **314/314**、
  cab2 **692/696**、cab3 797/802。cab2 剩余 4 条为结构互换（`TETHER→BELT`×2、`CAVITY→BELT`×1、`TETHER→CAVITY`×1）。
  渲染对照 `out/render_v2.png` vs `out/render_golden.png` 结构一致（灰=金标准 lines0）。
- **新增脚本** `eval_vs_golden.py`：逐线比对可复现（先校验两侧 id 空间相等；分开报"结构互换 / lines0 覆盖"，
  并打印物理兜底规则命中分布）。
- **文档**：SKILL.md §0.5（LODO 表 + 修订说明）、§10 目录、description 数值；`references/13_vision_prior_v2.md`
  §1/§2/新增 §2.1（案例：看起来是一条带 ≠ 一条带）/§6.1/§6.2/§9；`golden/README.md` 总览与基线；
  `golden/cab2/source.txt` 重写（含纠错记录与映射命令）。
- **教训**：金标准的错比特征的错更贵，但**改起来更便宜**——把"标签层 / 特征层"分开，
  改标签只改一行 `--map`，几何特征零重算。判 TETHER 前先看 `len_diag`/`cl_size`。

## 2026-10-31 (10) — 自动识别分区的全部技能自包含进一个文件夹（解构证据 + 交付快照 + 离线校验）

- **目标**：`E:/work/skill/气帘iges分区skill` 单独拷走即等于带走「图纸 + 人工标注 + 特征 + 模型 + 判据 + 交付证据」，
  **不再依赖 `E:/work/AI_CAB/...` 任何工作区**。
- **golden/ 每个金标准目录补齐为统一 7 件**（此前只有源图/`.hm`/标签/特征）：
  - `comp_lines.json`（组件→线 id = 标签怎么来的原始证据）、`comp_agg.json`（组件几何聚合表 = 定映射的判据）、
    `golden_panels.png`（逐组件面板 = 视觉定案依据）、`lines_pts.txt`（采样点 → 可离线重算特征）；
  - cab2 另存 `zoom_L5_18fragments.png`（那次 L5 纠错的现场图）。
- **新增 `cases/`（冻结的端到端验收快照，勿改）**：`v2_cab1/ v2_cab2/ v2_cab3/`，每个含
  `partitioned.hm` + `classify_final.json` + `class_lists.tcl` + `render_v2.png` + `render_golden.png` +
  `verify_partitioned.txt`（`VERIFY_FAIL=0`）+ `make_comps_report.txt` + `t00_import_report.txt`；
  `cases/README.md` 记三图验收表（314/314、692/696、797/802）、文件说明、复跑命令、可复现性证据。
- **新增 `scripts/rebuild_from_golden.py`（自包含校验）**：只用 `golden/<name>/lines_pts.txt` 离线重算 32 维特征，
  与存档 `features2.json` 比对 → **三图 max|Δ|=0.0（完全一致）**，并校验标签与特征同一线号空间。
  这证明"特征链路不需要 HyperMesh、不需要外部工作区"。
- **`scripts/eval_vs_golden.py` 升级**：不传参时优先读技能自带 `cases/`；`--pred-root` 优先匹配 `v2_<name>`
  （旧目录 `<name>/` 命中时显式告警"可能是 v1 结果"，此前曾误读到 v1 的 0.825）；输出里标注**预测来源路径**。
- **文档**：SKILL.md §0.5 加「自包含」四条命令、§10 目录树按新布局重写；`golden/README.md` 改为 7 件表格 +
  自包含校验 + 五步法补"7 件一起落盘"；`references/13_vision_prior_v2.md` §6.2/§8 指向 `cases/` 与离线复算。
- **实测（本机）**：`rebuild_from_golden.py` 三图全 OK（338/828/911 线 × 32 特征）；`eval_vs_golden.py`
  默认读 cases 得 314/314、692/696、797/802；`python scripts/train_v2.py` 仅凭 golden/ 即可复现 LODO 0.961/0.943。
- **可移植性实测**：整包 `cp -r` 到临时目录（`/tmp/skillport`）后，`rebuild_from_golden.py` 与
  `eval_vs_golden.py` 均直接通过（三图 max|Δ|=0、平均一致率 0.996）→ **无任何绝对路径依赖**。
- **新增 `scripts/sync_to_install.sh`**：把本目录（唯一权威源）同步到
  `~/.workbuddy/skills/qilan-iges-partition`（技能实际加载的副本），自动建带时间戳备份并校验
  `SKILL.md` / `tree_model_v2.json` 的 md5；`--dry` 只列差异。本次已同步（旧副本 1.8MB/2026-10-21
  → 17MB，备份于 `qilan-iges-partition.bak-20261031-2240`）。
