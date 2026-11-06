# 08 · 整车整合/换装阶段坑位详解（cab1 → 参考 host）

> 沉淀自 2026-10-25~10-28 气帘 cab1 整车整合攻坚：从"0.081ms 即爆"到"参考 host 换装 2ms 正常终止"。
> 坑位编号 P-S14~P-S27，总索引见 `07_pitfalls_index.md`。参考实现 `scripts/build_swap_clean.py`。

---

## 1. 阶段全景与最终结论

- **目标形态**：参考模型 host（`03_Control_card.k` + `MAT.K` + `Vehicle.k` + `Spring_move.k` 改接拉带）
  + 工作气帘网格（`cab1_60ms.k` 清算重编号版）。
- **结果**：2ms 探针 `*** termination time reached ***` 正常终止，0 错误，质量缩放 0.19%
  （对比爆炸时的 percent increase = 1.13E+8）。
- **根因结论**：爆炸根因 = cab1 自带的 **10 组"验证网格用"工装固定点**（用户点破：
  "原来他们为了验证网格问题都是自己起爆+固定点的，整合的时候要把这些都清算掉，删掉"）。
  跟拉带长度、单位制、BIW 参数都无关。

---

## 2. 工装清算（P-S14 ★★★）

**实录**：cab1_60ms.k 内查到：
- 10 张 `*BOUNDARY_SPC_SET`：900010~900018（9 个 boss cap 节点集，DOF1-6 全 1 = 全固定）
  + 900001（一撮散点 2070/2083/36558...，也是全固定）；
- 10 张 `*CONSTRAINED_NODAL_RIGID_BODY`：同一批集合做成节点刚体。

参考模型对照（grep 计数）：`5P-BAG_005.key` / `Vehicle.k` / `Spring_move.k` 里 **SPC=0、CNRB=0**。

**症状指纹**（诊断价值极高，以后遇到直接对表）：
| 试验 | 结果 |
|---|---|
| 带拉带（任意缆长） | 0.081ms 爆，同一 cycle 163、同一簇节点 |
| 无拉带自由充气 | 活（2ms added mass 0.03%） |
| 爆炸节点位置 | 20/20 落在 boss cap 节点集内（900010 含 112068） |

→ 两次不同缆长在同一瞬间爆同一簇 = 排除拉带几何，锁定固定点。

**正确锚定配方**（照参考 Spring_move.k）：
- boss 自由（不 SPC、不 CNRB）；
- cable 拉带 `*ELEMENT_BEAM`(ELFORM=6) + `*ELEMENT_DISCRETE`(damper) 连车身刚体节点；
- 锚点用 `*CONSTRAINED_EXTRA_NODES_SET` 焊进车身刚体（参考：PID 1000061 + 节点集 10200010）；
- 参考缆长全部纯垂直（dx=dy=0），L=85~210mm——工作拉带照这个量级设计。

---

## 3. deck 结构红线（P-S15/P-S16/P-S17/P-S18/P-S20）

### P-S15（★★★）删关键字必须整块删
- 只删关键字行不删数据行 → 孤儿数据行（TITLE 行、SPC 数据、CONTROL/DATABASE 数据全留下）
  → `forrtl: severe (64): input conversion error`（栈：BIGRDSECT dynkac.F ← GETCNT ← KEYWRD），
  keyword reader 段错误级崩溃，且 d3hsp 里一行错误回显都没有。
- **规矩**：任何丢弃 = 关键字 + 数据行直到下一个 `*`；改完必查"特征行清零"
  （如 grep SPC 数据行模式、ENDTIM 字面量、材料 MID 等）。

### P-S16 PART 数据行 10 字符定宽，SECID 溢出
- SECID 10005→1000037 超 10 列界 → 求解器读成 10000 → Error 10125/10133。
- 重映射必须按定宽字段重排：`'%10d%10d%10d' % (pid, new_sec, mid)`，不能字符串替换。

### P-S17 接触卡必须写满 4 行（含空白 A3 卡）
- `*CONTACT_..._ID` 少写第 4 行 → 解析器吞掉下一张卡 → Error 10246/10450。

### P-S18 `*DATABASE_BINARY_D3PLOT` 重复定义先到先得
- include 控制卡里已有 D3PLOT，主 deck 再定义无效。要改输出间隔就改控制卡副本
  （复制 `03_Control_card.k` → MOD 副本，改 ENDTIM/D3PLOT）。

### P-S20 定宽卡字段替换必须按列原位映射
- AIRBAG_HYBRID 等空格定宽卡：曲线引用 ±10/12/13/14/15 → ±30M 段，必须按 10 字符字段
  取出→判断→`'%10d'` 写回；拆成 token 用空格重连会毁列对齐（severe 64 同族）。

---

## 4. ID 空间与重编号（P-S19/P-S21）

### P-S19 跨文件 ID 冲突 → 段位偏移 + 七类审计
- 工作气帘与参考车身共用节点号段（如 114221 两边都有）→ 直接 `*INCLUDE` 合并必撞（重复节点 fatal）。
- 对策：工作文件节点/单元整体 **+30,000,000**（I8 装得下），并做七类审计零交叉：
  nodes / parts / sections / mats / curves / node-sets / part-sets。
- 审计注意：定宽文件取前 10 列当第一字段，逗号文件取逗号前字段。

### P-S21 材料共享与 include 语义
- 工作文件 MAT_FABRIC 84450005 与参考 MAT.K 逐字一致 → **丢自己的**，用参考 MAT.K
  （织物曲线 16-20 同理）；PART 卡里的 MID 84450005 自动落到参考材料。
- 参考 include 文件内嵌 `*KEYWORD`/`*END` 对 `*INCLUDE` 无害（R10.1 实测）；
  但**手工拼接**（去 *END 连接）会制造各种伪影——优先用 `*INCLUDE` 原样组装。

---

## 5. 时间读数与速度基线（P-S23/P-S24）

### P-S23 时间读数陷阱
- "termination at problem time 8.0681E-02" 是 **0.081ms**（163 循环 × dt=4.95E-4ms），
  不要读成"80.7ms"。判时间用 cycle × dt 交叉验证。
- "termination due to mass increase" 且 percent increase ~1E+8 = **单元翻转**（负雅可比）；
  `*** termination time reached ***` 才是正常跑完。

### P-S24 dt2ms 钉步与两段式跑法
- 本气帘 dt 被 DT2MS=-5.5E-4/TSSFAC=0.9 钉在 ~0.5µs（织物载荷曲线刚度高，参考模型同样钉 ~1µs）。
- 实测速度基线（n=2）：2ms 探针 7m51s（~8.5 cyc/s）；60ms ≈ 4h；100ms 级 8h+。
- **两段式**：先 2ms 探针（= 死亡点 ×24，验证"还爆不爆"）→ 通过后再 60-120ms 长跑看部署过程。
- 质量缩放偏高先看落点：cable 拉带元素质量极小刚度高，吃质量缩放属正常；
  判据看终止方式与趋势，不要看到 added mass 非零就慌。

---

## 6. 块级二分定位法（P-S25）

forrtl 类崩溃 / 段错误（无错误回显）的定位套路，实测两轮定位到行：

1. **单 include 探针**：每个 include 单独成 deck（`*KEYWORD + *INCLUDE file + *END`）跑 n=1，
   谁段错误谁肇事（其余文件会优雅报"引用不存在"后退出，exit 0）。
2. **块级前缀二分**：把肇事文件按关键字切块（keyword + 数据直到下一个 `*`），
   生成 25/50/75/100% 前缀探针 → 第一次崩的前缀 = 肇事块范围。
3. 崩溃原因前三名：孤儿数据行（P-S15）、列宽破坏（P-S20）、全局去逗号（references/01）。

---

## 7. host 接线要点（P-S26）

换装组装 = 参考 5 文件原样（`03_Control_MOD` + `MAT.K` + `Vehicle.k` + `Spring_move.k` 改接）+ 工作气帘清洗版：

- **Vehicle.k 自带袋-身接触**：`*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE_ID` ID=2，
  slave = SET_PART **2**，master = 节点集 10200009 → 工作文件的 SET_PART 2 必须包含**全部气帘件**
  （cab1 是 2,3,4,5），SID 恰好对上即自动生效。
- **充气**：工作文件自带 `*AIRBAG_HYBRID_ID`（SID=1 → SET_PART 1 = CAVITY 件）原样保留。
- **排除参考 6P_CAB**：它含 `*AIRBAG_LOAD_CURVE`（SID=1），混进来会对 set 1 二次加压（双重充气）。
- **拉带改接**：参考 beam/discrete 的袋侧端点（1-7、10092372、10008759、10065865）
  → 工作气帘 9 个 boss cap 按**最近贪心**匹配（禁止重复占用）；落选点 10065865 = 充气口，
  其 beam/discrete 删除（与"PORT 拉绳不要"决策一致）。改接按 I8 定宽列原位写回。
- **锚点已在刚体上时**不要再加 `*CONSTRAINED_EXTRA_NODES_SET`（报 20367
  "already contains extra node"）——该卡只用于把**独立**锚点节点焊进刚体。

---

## 8. 提交模板（P-S27）

```bash
export LSTC_LICENSE=ansys
export ANSYSLMD_LICENSE_FILE=1055@server
mpiexec -n 2 "D:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_mpp_sp_msmpi.exe" i=main_swap.key
```

- 许可只放 **2 个 rank**（`-n 4` 直接 abort）；MPP 输出 mes0000/mes0001。
- 崩溃判读：`ended prematurely, exit code 64` = 求解器段错误（查 P-S15/P-S20）；
  exit 0 + d3hsp 有 Error 列表 = 优雅报错（查引用缺失/重复定义）。

---

## 9. 换装管线参考实现

`scripts/build_swap_clean.py` 一条龙（本目录镜像，源在 `E:\work\AI_CAB\onekey\`）：
1. 清算工装（整块删 SPC×10 + CNRB×10 + CONTROL/DATABASE×31 + 自带 MAT_FABRIC/曲线16-20）；
2. 节点/单元 +30M 重编号（NODE/ELEMENT_SHELL/SET_NODE_LIST 三类行）；
3. 保留曲线 10-15 → 30M 段重命名（`&TTF` 参数还原为字面量），AIRBAG 定宽卡内 ±LCID 同步映射；
4. 解析 Spring_move.k beam/discrete，袋侧端点最近贪心改接到 9 个 boss cap（定宽列原位写回）；
5. 生成 03_Control MOD（ENDTIM/D3PLOT 参数化）与 main_swap.key；
6. 七类 ID 审计输出零交叉结论。

产出目录约定：`run_swap/`（2ms 探针）→ `run_swap_long/`（60ms 长跑，D3PLOT=0.5ms）。
