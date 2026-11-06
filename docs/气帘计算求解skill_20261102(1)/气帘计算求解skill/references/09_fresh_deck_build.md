# 09 · 从零组合 deck（车身 + 气帘两独立模型，全参考某参考模型）

> 沉淀自 2026-10-26~29 `onekey` 攻坚：组合 `BIW_clean.k`（车身）+ `cab1_60ms.k`（气帘）两个**干净网格**，
> 清除两模型全部非网格设置，完全照抄 `Model_update_Move_Iter04` 的约束/材料/厚度/接触/上拉/点爆；
> 气帘按 roof rail 相对参考位置做 Y/Z 平移；9 拉带 + 1 充气口拉绳，车身侧 Z 向上投影；
> 向上拉起后点爆，车身刚体。
>
> 坑位编号 **P-S28~P-S46**（§11/§12 补 P-S41~P-S46：拉绳 SPC 锁横向、投影强制取上方、参考几何抑制 flutter、RefGeom 4 字段坑、SMP 渲染跑配方），总索引见 `07_pitfalls_index.md`。参考实现 `E:\work\AI_CAB\onekey\gen_deck.py`。

---

## 1. 本流程 vs 换装法（P-S26）—— 何时用哪个

| 维度 | 换装法（P-S26 / `build_swap_clean.py`） | 本流程（09 / `gen_deck.py`） |
|---|---|---|
| 输入 | 工作气帘网格 + **参考 host 全套**（03_Control+MAT.K+Vehicle.k+Spring 改接） | 两个**干净**模型：`BIW_clean.k`（车身）+ `cab1_60ms.k`（气帘） |
| 车身来源 | 直接 `*INCLUDE` 参考 Vehicle.k（自带 S2S 接触、刚体） | 自己从 BIW 网格**重建**刚体 + 接触 + 拉绳 |
| 设置来源 | 几乎全由参考 host 提供，气帘只负责"换进去" | 全部卡片**逐张照抄**参考模型（用户要求"完全参考参考模型"） |
| 适用 | 已有一套能跑的参考整车，只换气囊 | 参考模型不含现成整车、或需把气帘按相对位置拼进独立车身 |

**一句话**：参考 host 完整 → 换装法；只有两堆干净网格 + 一个参考 deck 当"模板" → 本流程。

---

## 2. 平移量确定（用户铁律 → P-S35）

气帘相对 roof rail 的 Y/Z 偏移 **不靠目测，靠"顶部距离差一致"**：

- **用户原话**："安全DZ可以参考参考模型的顶部距离差，一致即可"。
- **量法**：在工作模型与参考模型各取"气帘顶 → 车身顶"的节点对距离分布，令两者的 **p50（中位数）相等** → 解出 DZ；DY 同理（或按 roof rail 对齐取定）。
- **本例实测**：
  - 参考模型 p50 = **+522.0 mm**（气帘顶相对车身顶）。
  - 工作模型在 `DZ=-270` 时 p50 = **+522.9 mm**，与参考一致 → 锁定 `DZ=-270`。
  - `DY=-615`（roof rail 横向对齐）。
- **代码锚点**：`DY, DZ = -615.0, -270.0`，注释必须写明"由 solve_dz_gap.py 按顶部距离差求得"。
- **铁律**：平移量必须经"距离差一致"回算确认，不能凭视觉对齐——肉眼差几毫米，拉绳投影全偏。

---

## 3. 拉绳锚点投影（P-S28 ★★★ 本流程最核心坑）

车身侧锚点 = 气帘侧节点 **沿 Z 向上在车身上的投影点**。错误做法是全局最近邻，会引发 mass increase。

### P-S28 全局最近点 → 锚点被甩出 200~600mm
- 若用"全车身节点里离气帘侧点最近"的全局最近邻，锚点会落到**几百毫米外**的另一块板上
  （X 方向漂移 200~600mm），拉绳被强行斜拉 → 巨大接触力 → `mass increase` 终止。
- **正确算法（同 X 邻域 + Z 向上）**，层级兜底：
  1. `XTOL=45mm` 内、`bz > z`（车身节点高于气帘点）→ 按 `(dX, |dY|, -Z)` 选（dX 最小优先）；
  2. 放宽到 `3*XTOL` 同上；
  3. `XTOL` 内**最高**节点（不论是否高于气帘）；
  4. 全局兜底（仅兜底，正常不应触发）。
- 关键：**先锁 X 邻域**，再在邻域内按 Y 距离/高度挑，绝不让 X 自由漂。

### P-S38 投影质量验收：看 dXY≈0（锚点没横向甩偏），dZ 不必等于参考 tether dZ
- 拉绳应近似竖直，记 `dXY = hypot(bx-x, by-y)`、`dZ = bz - z`。
- **本例最终（run_probe7）10 根**：全部 `dXY < 64 mm`（近似竖直、锚点未横向甩到错板），`dZ ∈ [+135, +378] mm`（均值 ≈ +225mm）。
- **关键澄清**：dZ 量级由 cap/锚点的具体布置决定，**不必等于参考模型的 tether dZ**（参考锚点位置不同）；真正的"相对位置一致"由 P-S35 的**顶部距离差 +522mm** 保证。
- **判据（验收投影成败）**：看 **dXY≈0** 且锚点落到预期零件；若某根 dXY 突然 >200mm、或 dZ 为负、或锚点落到明显非预期零件 → 投影失败，回查 P-S28 层级。

### P-S30 重编号与坐标提取的 ID 基准必须一致
- `cap_sets` 里存的节点 ID 是**重编号后**（`+30M`）；取原始坐标要先 `-NOFF` 还原，再查 `cab_nodes`。
- 已重编号又减 NOFF 会算出**错位坐标**（实测锚点坐标错乱）。统一用：
  ```python
  def cab_coord_orig(nid):  # nid = 原始 ID
      return (cab_nodes[nid][0], cab_nodes[nid][1]+DY, cab_nodes[nid][2]+DZ)
  ```
  气帘侧点的元祖里**重编号 ID** 与 **原始 ID** 要分清，打印时同时输出两者便于核对。

---

## 4. 车身（BIW）处理专门坑

### P-S29 BIW 文件混入他模型孤立节点（约 33790 个）
- `BIW_clean.k` 的 `*NODE` 卡混入了约 **33790 个气帘节点**（ID/坐标与 `cab1_60ms.k` 完全一致，
  且**不被任何车身壳单元引用**）。它们不是车身几何。
- 危害：(a) 若车身做全节点 SPC，会把它们固定并干扰气帘；(b) 拉绳 Z 向上投影会落到"气帘自己"身上。
- **正确**：先收集被车身 `*ELEMENT_SHELL` 真实引用的节点集 `body_shell`，只保留 `body_shell` 中的
  节点，其余（混入的气帘节点）整行删除。

### P-S31 平移只改 Y/Z，DY 不要错加到 X
- 节点字段顺序 `nid, x, y, z`，Y 是索引 2。写节点时 `p[2] = y + DY`（Y 加 DY）、`p[3] = z + DZ`。
- 误写成 `p[1] = x + DY` 会把气帘整体沿 **X** 平移，整个相对位置崩掉。

### P-S32 节点行索引错位（node_rows ↔ body_lines）
- 剔除混入节点时，行号要在 `body_lines.append` **之后**记录：`node_rows.append((len(body_lines), nid))`。
- 若先记录再 append，或混用两个列表的下标，`_node_line_ids` 会命中错行 → 删错/留错节点。

### P-S33 SET ID 冲突
- 车身集合改用 **900101 / 900102 / 900103**，避开气帘原有集合（900010~900018、10200009 等），
  防止 `*INCLUDE` 后集合被覆盖或重复定义。

### P-S34 车身刚体**不加全节点 SPC**
- 参考模型车身 = `MAT_RIGID` **可动刚体**，不做全节点 SPC。
- 锚点若**已属于刚体 part**（本例全部落在 part 96318 内），**不要再**额外加
  `*CONSTRAINED_EXTRA_NODES_SET` → 报 `20367 already contains extra node`。
  该卡只用于把**分属不同 part** 的独立锚点节点焊进刚体（见 P-S22）。

---

## 5. 复制参考模型的卡片配方

全部卡片**逐张照抄** `Model_update_Move_Iter04`（用户要求"完全参考"），本例取值：

| 卡片 | 做法 | 本例取值 |
|---|---|---|
| 材料 | 气帘织物/刚体用参考 MAT.K；车身全 `MAT_RIGID` | `MAT_FABRIC=84450005` / `MAT_RIGID=84450006` / `MAT_NULL=74000001` |
| 截面 | 车身壳 `SECTION_SHELL` 全 `MAT_RIGID`（刚体语义） | — |
| 接触（P-S37） | `*CONTACT_AUTOMATIC_SINGLE_SURFACE_ID`，**SSID=2**，气帘零件作 slave | 参考 main.key 结构；set 2 = 气帘件(2,3,4,5) |
| 上拉 | 复制参考 `*LOAD_BODY_Z` + 曲线 1 | 缩放系数 **0.0098** |
| 点爆 | 复制参考 `*SENSOR_DEFINE_MISC` / `*SENSOR_SWITCH` / `*SENSOR_CONTROL` | 取自 `6P_CAB_update2.k` |
| 充气 | 保留工作文件 `*AIRBAG_HYBRID_ID`（R10 兼容） | SID=1 → SET_PART 1 = CAVITY 件 |

> **P-S05 提醒**：R10.1 求解器下 `*AIRBAG_HYBRID_ID` 是兼容卡，技能要求保留，**不要**改用 R11+ 新卡。

---

## 6. 接触卡（P-S37）结构要点

参考 `main.key` 尾部，单面接触：

```
*CONTACT_AUTOMATIC_SINGLE_SURFACE_ID
         1
         2         0         2         0         0         0         1         1
       0.1       0.1       0.0       0.0       0.0         0       0.0       0.0
       ...   (写满 4 行，含空白 A3 卡，见 P-S17)
*SET_PART_LIST
    900103         0       0.0       0.0       0.0
  <车身 part 逐行>
```

- `SSID=2` → 气帘零件集（set 2）作为 slave，与全场（车身）接触 → 袋-身互相接触。
- 区别于 P-S26 的 `Vehicle.k` S2S（`slave=SET_PART 10200009 车身` vs `master=2 气帘`）。
- 接触卡**必须写满 4 行**（含空白 A3 卡），少一行解析器会吞下一张卡（P-S17）。

---

## 7. 弹簧/阻尼能量 4.8e4 异常（P-S36）—— 已定位为投影缺陷副产物，非物理差异

- **现象（中间态）**：早期某次 2ms 探针 `glstat` 中 `spring and damper energy ≈ 4.8e4`，参考模型仅 **~1e-4** 量级，差 8 个数量级。
- **最终态（run_probe7，全部修正后）**：同一指标 `= 2.0e-20 ≈ 0`，与参考（~1e-4，可忽略）一致；
  `added mass = 2.78e-5`（百分比 0.0004%）、`*** termination time reached ***` 正常、无 mass-increase 终止。
- **根因**：该异常是**拉绳被错误拉伸**的副产物——早期投影用全局最近点（P-S28 反面）、cap 节点 ID 基准错位（P-S30）、
  或重复声明 `*CONSTRAINED_EXTRA_NODES_SET`（P-S34），导致锚点落错板、拉绳斜拉数百 mm，弹簧/阻尼储能爆掉。
- **结论**：弹簧/阻尼能量异常不是"物理设置固有差异"，而是**锚点几何错误的报警**。看到它就回查
  P-S28 / P-S30 / P-S34，**不要去调拉绳间距或约束语义**（本例拉绳间距 147~380mm 与参考 130/50/140/180/210/175/145/155/85/190mm
  不同，但修正后能量仍≈0，证明间距差异不是主因）。

---

## 8. 验证结果（本例最终状态 = run_probe7）

- `main.key` 生成；ID 审计无致命冲突（车身 900101/102/103，气帘 900010~018、10200009 等互不覆盖）。
- 10 根拉绳全部连通；10 根 `dZ ∈ [+135, +378] mm`、均值 ≈ +225mm，全部 `dXY < 64 mm`（近似竖直、锚点未横向甩偏）。
- **2ms 探针**：正常到达 `termination time = 2.0003`（cycle 4041，n=2，8m21s）；
  `added mass = 2.78e-5`（百分比 0.0004%）；`spring and damper energy = 2.0e-20 ≈ 0`；
  无 mass-increase 终止；仅有良性 Warning（曲线离散化、INI 提示），无 Error。
- **结论**：顶部距离差 +522mm 与参考一致（P-S35）、投影无甩偏（P-S28/P-S38）、弹簧能量≈0（P-S36）——
  该 deck 已通过 2ms 探针健康门禁，可进入 60-120ms 长跑看部署过程。
- **主跑实证（run_main1，200ms deck）**：后台启动后稳定运行至 **t=40.0ms / cycle 80809**，
  稳定步长 `dt=4.95e-7s`（=4.95E-04 ms，与探针一致），周期性 d3plot flush、无 Error / mass-increase；
  后因用户要求"先停掉计算"在 40ms 处干净中断（无残留进程）。**40ms 全程健康 = 该 deck 跨时间尺度稳定**的强证据。

---

## 9. 主跑启动配方与估时（P-S39 / P-S40）

### 9.1 ENDTIM 取舍
- `main.key` 指向 `03_Control_card_MOD200.k`，`ENDTIM=200.0`（"参考一致"，对应 `Model_update_Move_Iter04`）；
  `main_probe.key` 指向 `03_Control_card_MOD2.k`，`ENDTIM=2.0`（探针）。
- 用户早期选项曾选 **80ms**，与 deck 默认的 200ms 不同——属"完全参考参考模型"的设计取舍，非 bug（P-S39）。
- 要改 ENDTIM：**整串替换**控制卡定宽数（保留前导空格列宽）：
  `     200.0         0       0.0       0.0       0.0` → `      80.0         0       0.0       0.0       0.0`。

### 9.2 估时（P-S40）
- 稳定 `dt = 4.95e-7 s`；`步数 ≈ ENDTIM/dt` → 200ms ≈ **40 万步**。
- `n=2`（MPP，许可证限 2 进程）实测速率：40ms 用 ~2h13m → 200ms ≈ **11 小时**、80ms ≈ **4.5 小时**。
- 用户曾因"时间过长"中断主跑 → 推荐流程：① 2ms 探针过健康门禁；② 截断 ENDTIM（如 80ms）看部署中段；③ 确认无误再 200ms 全量。

### 9.3 启动命令（MPP n=2，自带 license env）
```bash
cd "E:/work/AI_CAB/onekey/_t_run" && mkdir -p run_mainX \
  && cp main.key 03_Control_card_MOD200.k MAT.K BIW_rigid.k cab1_clean.k Spring_swap.k sensor.k contact.k run_mainX/ \
  && cd run_mainX \
  && export LSTC_LICENSE=ansys \
  && export ANSYSLMD_LICENSE_FILE=1055@server \
  && "C:/Program Files/Microsoft MPI/Bin/mpiexec.exe" -n 2 \
     "D:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_mpp_sp_msmpi.exe" i=main.key > main.log 2>&1
```
- 探针同理，把 `main.key`→`main_probe.key`、`03_Control_card_MOD200.k`→`03_Control_card_MOD2.k`。
- 健康门禁（完成后看）：`glstat` 的 `added mass`、spring/damper energy、`*** termination time reached ***`；
  `main.log` 周期性 `write d3plot file` / `flush i/o buffers` 即正常推进。

---

## 10. 参考实现（项目副本）

`E:\work\AI_CAB\onekey\gen_deck.py`（约 600 行，本项目副本，非技能通用脚本）：

- `DY,DZ` 平移（§2）、`NOFF=30M` 重编号、`CRV_MAP` 曲线 10-15→30M+、`MAT` 映射；
- `cab1_60ms.k` 清算（整块删 SPC/CNRL/CONTROL/DATABASE/BOUNDARY/CONSTRAINED/CONTACT/自带 MAT）+ 平移 + 重编号；
- `BIW_clean.k` 刚体化 + 剔除混入孤立节点（§4 P-S29）+ 节点行改写为逗号格式；
- 拉绳投影 `proj_body()`（§3 P-S28 层级兜底）+ `cab_coord_orig()`（§3 P-S30）；
- 提取参考 `Spring_move.k` 缆/阻尼 PART/SECTION/MAT/LOAD_BODY_Z/曲线1，写 `Spring_swap.k`
  （10 beam + 10 discrete，8 字符定长，离散元尾部补 `" 0. 0 0."` 防字段不足错位）；
- 提取 `6P_CAB_update2.k` SENSOR 三卡；照抄参考单面接触（§6）；
- 组装 `main.key`（ENDTIM=200）+ `main_probe.key`（ENDTIM=2）。
- 所有输出经 `ascii_write()` 强制纯 ASCII（中文注释预翻译表），避免 HM/LS-DYNA 读入乱码。

> 技能不维护网格/项目专属脚本；本文件只沉淀**可复用的坑位与配方**，换项目时按 §1 选流程、按坑位对表。

---

## 11. 减抖三处修复（P-S41 + 用户三项要求，2026-10-29 实战）

用户看了主跑 d3plot（前 27ms 气帘乱飞舞/抖动严重）后提出三项修复，全部落到 `gen_deck.py`：

### 11.1 拉绳起点（气帘侧）加 SPC：Z 自由、X/Y 锁死
- 拉绳是沿 **Z 向垂直**动的，气帘侧起点节点不应被拉绳带着横跑：
  `Spring_swap.k` 末尾追加：
  ```
  *BOUNDARY_SPC_NODE
  $#   nid       cid       dofx      dofy      dofz     dofrx     dofry     dofrz
  30112068,0,1,1,0,0,0,0     ← 10 行（dofx=dofy=1 固定, dofz=0 自由）
  *END
  ```
- 即 **TX=TY=1（锁）、TZ=0（自由）**；生成前校验 10 个 cap 节点都真实存在于 `cab1_clean.k`（防 SPC 空挂报错）。

### 11.2 `proj_body()` 重写：所有层级强制 `bz > z`（绝不取下方节点）
- 用户反馈"车尾数第二个"拉绳被连到斜 Y 方向去了——旧 fallback 层级允许 `bz<=z`（取到下方/同高节点）。
- **新层级（全部先筛 `bz > z`）**：
  1. `XTOL=45mm` 内，按 `(水平距离 hypot(bx-x,by-y), -Z)` 排序取最优（Z 越高越好）；
  2. 放宽 `3*XTOL`；3. 放宽 `6*XTOL`；4. 全部车身节点里 `bz>z` 者；5. 兜底取全局最高节点（正常不应触发）。
- **实现坑**：候选元组 `(dist, bx, by, bz, bid)` 共 5 元，取节点号必须 `cand[0][4]`；
  写成 `[3]` 取到的是 bz 浮点坐标 → KeyError。重写投影后**回归校验**：10 根拉绳 `dXY≤6mm`（近似竖直）、`dZ` 全正。

### 11.3 引入 `*AIRBAG_REFERENCE_GEOMETRY`（参考几何，抑制上拉抖动）
- 参考模型 `6P_CAB_update2.k` 中该卡把气帘**全部节点号+零位坐标 copy 一份**，作为膜片静止形状的软约束，
  抑制充气上拉时的 flutter/乱飞舞（无显式 ID，靠节点号归属气囊隐式关联）。
- `gen_deck.py` 生成 `RefGeom.k`（115446 行 = 1 头 + 全部气帘节点），`main.key` 里 include 顺序 **RefGeom.k 在 Spring_swap.k 之前**：
  坐标用**平移后**值（`x, y+DY, z+DZ`，与 `cab1_clean.k` 初始坐标逐点一致）。
- **P-S41（★★★）格式坑**：本机 R10.1.0 把该卡当 **4 字段/记录连续流**读（`Warning KEY+457 only 4 expected`）。
  照抄参考模型旧版 6 字段（`nid,x,y,z,0,0`）→ 解析流错位 → 膜片坐标全乱 →
  **Initialization `Error 30099 (INI+99) zero normal vector`** 终止。**必须严格写 4 字段 `nid, x, y, z`**。
- **实证**：4 字段版 SMP 跑（run_fix_smp）初始化零 Error、正常求解至被人为停止的 t=7.5ms；
  6 字段版初始化即 Error 30099 终止——同一 deck 唯一差异就是 RefGeom 字段数。

---

## 12. SMP 渲染跑配方（P-S42~P-S46）与抖动验证管线

### 12.1 为什么渲染要另跑 SMP（P-S44）
MPP 的 d3plot 主文件只含单 domain 几何（126707 节点），状态文件用全局节点号（231681）→ SMP 版 reader 越界。
**对策**：同 deck 复制一份跑 SMP（单文件 d3plot，几何+状态一体，`d3plot_reader` 家族直接可读）。

### 12.2 渲染专用控制卡（P-S45）
- 复制 `03_Control_card_MOD40.k` → `*_rd.k`，把 `*DATABASE_EXTENT_BINARY` 的
  STRFLG/SIGFLG/EPSFLG/RLTFLG/ENGFLG 由 1 置 0（帧里不再追加单元数据块，定长 stride 可读；物理零差异）。
- 手写 `main_rd.key` include 链与主跑一致（含 `RefGeom.k`）。
- 输出间隔 `*DATABASE_BINARY_D3PLOT` DT=2.5ms → 前 27ms ≈ 11 帧。

### 12.3 启动命令（SMP，P-S42/P-S43）
```bash
cd run_dir && export LSTC_LICENSE=ansys ANSYSLMD_LICENSE_FILE=1055@server OMP_NUM_THREADS=2
"D:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_sp.exe" \
    i=main_rd.key memory=50000000 ncpu=2 > smp_run.log 2>&1
```
- `memory=50000000` 必加（默认 20M words 报 Error 70021，本 deck 差 ~2.3M words）。
- **后台任务里直接前台执行 solver**，勿 `nohup ... &`（P-S43：内层 & 会被静默杀掉，日志停在 license OK 似正常）。
- SMP 速率实测（ncpu=2）：2.5ms/状态 ≈ 9~10 分钟 → 40ms ≈ 2.5h；dt 与 MPP 一致（4.95e-7 s）。

### 12.4 渲染/验证管线（技能新脚本）
- `scripts/smp_d3plot.py`：SMP 单文件 d3plot 逆向 reader。不解析连接段——用"状态0 坐标==初始 g0 逐位相等"
  定位状态0、标准 stride `(140+9N)` 对齐 4 词边界 + 状态1 合理性校验兜底；
  `--shake` 输出每帧 `vrms/vmax/dmean/dmax`（无需质量的抖动指标），`--shake-csv` 导出。
- `scripts/render_fixed.py`：前 27ms 每帧侧视图（X–Z 按 |位移| 着色）+ 多格总览 + 速度 RMS 时间历程，
  量化对比"旧 deck vs 修复 deck"抖动水平。
- **验证跑实证（run_fix_smp，2026-10-29）**：三处修复 + 4 字段 RefGeom 的 deck 初始化零 Error，
  稳定求解至 t=7.5ms（d3plot01~04 已写出）后按用户要求停算；d3hsp 确认 RefGeom 卡被正常解析（echo `>300xxxxx` 节点行）。
  后续 40ms 跑完用 `--shake` 对比 run_main1 前段即可定量确认抖动缓解。
