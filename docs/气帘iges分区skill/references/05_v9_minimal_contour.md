# 05 · v9 极简轮廓原则（用户 2026-10-21 下午反馈）

> 适用场景：NEW_CAB（Drawing0904ZHEDIETU.iges）初版四分区（v8 = 119/78/59/572）跑出来后，
> 用户复核几何，要求**重新界定分组边界**。本文件是这次反馈沉淀下来的修正规则 + 落地清单。
> 该修正**针对这张图**，不是通用规则；其他项目照 `01~04` 走。

## 0. 一句话原则（最重要）

分区里的曲线**只为最终形成计算模型服务**——它们是后续裁切建面 / 作 Surface Edge 的**闭环边界轮廓**。
所以：

- **不是几何特征的"全集"，而是边界轮廓的子集**。没有必要的细小 Curve、特征装饰线、内部折叠线**不要放进来**。
- **参考 `E:\work\AI_CAB\气帘CAD数据\cab1.hm` 的分组风格**：cab1 用最少量外轮廓环（BELT 仅 7 线、CAVITY 仅 2 个 composite），
  在充气口处布带环与气腔环**基本对应、靠内平行**，两环在口部汇合，没有多余的闭合线。
- **语义归人，几何归机器**：哪些线该进哪个环由人眼在底图上圈定；脚本只负责按名单搬线 + 做连通性 QA。

## 1. 四个分区的具体修正（对照 cab1.hm）

### BELT 布带环 (PID2)
- **上部几个独立小竖线不要**：它们干扰 Surface Edge 网格，移出（归入 TETHER 或 DROP）。
- **右上不连续 → 从 TETHER 拿回**：凸台顶边盖线 `L822 / L525 / L767` 原本错放进 TETHER，
  应回归 BELT（它们就是布带顶边在凸台处的水平盖线，端点与 BELT 线 2~5mm 相接）。
- **肩部小竖线归还 TETHER**：`L262/L263/L316/L317/L370/L371`（3~6mm 短竖线，在凸台肩部）是 v8 误归 BELT，回归 TETHER 接回肩部线。
- **充气口只留最外轮廓反过来**：内部 70+ 条折叠线（领圈内部皱褶）**全部 DROP**；
  仅保留最外一圈反向轮廓（`L470→L189→L249→L196→L188→L187→谷底→L135` 闭合成领圈环）。
- 充气口内部一条孤立折叠线 `L254`（仅与已 DROP 的 `L212` 等相连）→ **DROP**。

### CAVITY 气腔环 (PID3)
- 中下部良好；主要问题在**上部开口**：它从口部环线**靠内一点**上行闭合（仿 cab1：口部两环对应、靠内平行）。
- 闭合路径：气腔顶边 → `L134`（气腔顶边 y≈357 延续）→ `L471` → `L166`（布带外墙、与 L470 平行）→ 领圈顶 →
  `L161`（气道左壁）→ `L162/163/164` → `L233/234`（重复）→ `L159/158` → `L157/167/253` → 回到气腔右上顶边 `L12`。
  **这条"气道回路"就是气腔的口部闭合，等价于 cab1 的 2 个 composite。**

### SEAM 缝线环 (PID4)
- 封闭双圆头（哑铃型）抓得很好，**保留 4 个哑铃**。
- 引入的垃圾：充气口上方非封闭凹曲线 + 与 BELT 平行重复的气道线 → **移走**：
  气道环 `L158/159/162/163/164/233/234` 归 CAVITY；平行重复 `L160/165/205/237/238/241/242/245/246` **DROP**。

### TETHER 拉带环 (PID5)
- 整体识别不错（7 个顶部凸台 + 左上/右上角拉带 + 右侧梯带）。
- 从 BELT 错拿来的曲线已归还 BELT（见上）。
- **左下方两个小圆圈是排气口，不是拉带** → 移出（`L5/L37/L820/L821/L825/L826/L827/L828` = 2 圆+2 十字+2 弧）→ **DROP**（暂不加，需要时再补）。

## 2. 落地清单（v9_apply_fix.py 里的硬编码）

```
TO_BELT   = [822, 525, 767]                       # 凸台顶边盖线回归 BELT
TO_CAVITY = [134,157,161,166,167,253,471,          # 布带口部内/外墙
             158,159,162,163,164,233,234]          # 缝线气道环
TO_TETHER = [262,263,316,317,370,371]              # 凸台肩部小竖线回归 TETHER
DROP      = 口部内部折叠 136-156,168-186,190-228子集
           + 缝线气道平行重复 160,165,205,237,238,241,242,245,246
           + 排气口 5,37,820,821,825,826,827,828
           + 充气口内折叠 254
```
> 脚本读 `newcab_classify8.json`（规范 v8 = 119/78/59/572）作稳定源，输出 `classify_v9.json` 并覆盖 `classify_final.json`。
> **幂等/可重复**：重跑不产生 KeyError（DROP/TO 列表都做了 `if lid in C` 保护）。

## 3. 最终计数（v9 = 738 参与分区，90 条不参与）

| 分区 | 线数 | 连通组分 | 说明 |
|---|---|---|---|
| BELT   | 36 | 5 | 主环(comp0,21线,0.24mm≈闭合) + 口部外领圈(comp1,10线) + 凸台盖线(L525/L767/L822, 2.7~5.2mm 短缺口) |
| CAVITY | 92 | 3 | 主体(83线) + 气道回路(6线) + 气道上部(3线)，口部 ~1mm 缺口闭合 |
| SEAM   | 43 | 4 | **4 个全部闭合**的哑铃 |
| TETHER | 567 | 114 | 7 凸台 + 角拉带 + 右梯带；排气口已移出 |
| **合计** | **738** | — | 原 828，移出 90 条 |

## 4. 坑位（本次踩过，编号接 SKILL.md 的 P42 之后）

- **P43 基文件坑**：v9 必须从**规范 v8 `newcab_classify8.json`（119/78/59/572）** 出发。
  `classify_prev.json`（119/71/58/580）是含 9 线差异的**变体**，若误用作源会得到
  BELT 36 / CAVITY 85 / TETHER 575（7 条本应属 CAVITY 的线被算作 TETHER、L762 错位），审计对不上。
  → 脚本默认源已钉死 `newcab_classify8.json`，可用 `V9_SRC` 环境变量覆盖。
- **P44 幂等坑**：脚本会把 `classify_v9.json` 复制到 `classify_final.json`（自身副作用）。
  若对已生成的结果重跑，DROP 列表里的 id 已不在 C 里 → 原代码 `del C[lid]` 抛 `KeyError`。
  → 已加 `if lid in C` 保护；且源读稳定 v8 而非会被改写的 final。
- **P45 验证误报**：`t08_verify_partitioned.tcl` 原按"全部线都进 4 comp"假设 `TOTAL=738`。
  v9 刻意留 90 条不参与分区的线在 `lines0`（用户要求"不要放这组里"），导致 `VERIFY_FAIL=1` 误报。
  → 已补 `UNASSIGNED={lines0,DROPPED}` 跳过，分区总数只算 4 个命名 comp，v8/v9 都 PASS。

## 5. 怎么复现

### 5.1 一键链（推荐）

```bash
export WORKDIR="E:/work/AI_CAB/onekey/work/<proj>"   # 指向含 out/ 的工作区
export V9_SRC="newcab_classify8.json"                # 规范 v8 种子分类 (默认即此名)
export HMBATCH="D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe"
bash "E:/work/skill/气帘iges分区skill/scripts/run_v9.sh"
# 期望: out/verify_partitioned.txt 含 VERIFY_FAIL=0, 计数 36/92/43/567
# 注意: 第 3 步会停在人眼确认 — 看图 out/v_partition*.png / out/v_v9_*.png 后回车
```

### 5.2 分步（等价）

```bash
export WORKDIR="E:/work/AI_CAB/onekey/work/newcab"
cd "$WORKDIR"
V9_SRC=newcab_classify8.json python scripts/v9_apply_fix.py   # -> classify_v9.json + classify_final.json + 连通性 QA
python scripts/p06_export_class_lists.py                     # -> out/class_lists.tcl
hmbatch -tcl scripts/t07_make_comps.tcl                      # -> partitioned.hm (ALL_OK=1)
hmbatch -tcl scripts/t08_verify_partitioned.tcl              # 期望 VERIFY_FAIL=0
```

## 6. 配套脚本清单（本 skill `scripts/` 下）

| 脚本 | 作用 | 输入 | 输出 |
|---|---|---|---|
| `v9_apply_fix.py` | 应用本文 §1~§2 的修正清单 + 端点搭接连通性 QA | `out/$V9_SRC`、`out/geom_features.txt` | `out/classify_v9.json`、`out/classify_final.json`、`out/v9_apply.txt` |
| `v9_recon.py` | 四个问题区域侦察：BELT 顶部小竖线/右上方断链/口部全部线/SEAM 气道缝/左下方排气口 | `out/geom_features.txt`、`out/classify_final.json` |  stdout 清单（P1a~P4） |
| `v9_recon2.py` | 补齐侦察：拐角线、凸台顶边盖线候选、BELT 连通组分、排气口区 | 同上 | stdout 清单（A~E） |
| `v9_render.py` | 四个问题区域特写渲染（带 id 标注） | `out/lines_pts.txt`、`out/classify_final.json` | `out/v_v9_port.png`、`v_v9_righttop.png`、`v_v9_seamgas.png`、`v_v9_exhaust.png` |
| `p05_render_partition.py` | 全图分色渲染 | 同上 | `out/v_partition.png`、`v_partition_all.png` |

> `v9_recon*.py` / `v9_render.py` 是**诊断辅助**，用于复现"为什么这么改"和"改完还有无残留"。
> 它们均只读当前 `out/classify_final.json`，可重复跑；改完想复查某区域直接调用即可。
> 所有脚本认 `WORKDIR` 环境变量（与 `run_all.sh` 一致），换项目不用改硬编码路径。
