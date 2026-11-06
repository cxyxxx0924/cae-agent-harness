# 00 · RUNBOOK：接一个新气帘（工作流主入口）

> **这份文件是唯一入口。** 新来一个气帘项目，从这里第 0 步往下走，不要凭记忆拼流程。
> 每一步都写了：**命令 → 应该看到什么数字 → 看不到就是哪里坏了（查哪条坑）**。
>
> 配套：`04_pitfalls.md`（坑全集 P1–P60）、`19_open_issues.md`（还没解决的）、
> `20_baselines.md`（历史数字，用来判断"这版对不对"）。
>
> **时间预算参考**（cab2 实测，5mm 主尺寸、90 条 CAD 曲线）：全新案例从原始 .hm 到可交付 K
> 约 2.5~4 小时，其中 60% 时间在第 3 步（分区）和第 5 步（拉带锚固）。第 7 步门禁只要 3 分钟。

---

## 0. 开工前 5 分钟检查（不看这 5 条，后面一定返工）

| 检查 | 怎么查 | 不对的症状 |
|---|---|---|
| **工作目录全英文** | `echo $WORKDIR` 不能有中文 | hmbatch `-tcl` 静默挂掉（P6） |
| **HM 版本锁 2026** | `D:/Program Files/Altair/2026/.../hmbatch.exe` | 用 2020 跑同一份 Tcl，节点数差 3%、气腔单元少 6.2%（P4） |
| **模板必须先加载** | Tcl 第一句 `hm_framework loaduserprofile LsDyna Keyword971_R16.0` | `No user profile or template file loaded`、`data-name "pid" is not valid`（P2） |
| **CAD 是 2D 曲线分组** | 打开 .hm 看 component 数（应 4~6 个） | 全挤在 1 个 component → 先回 CAD 端分组，或走排序自动分组 |
| **图纸坐标系** | 图纸 X→模型 X，图纸 Y→模型 Z（`plane: "xy"`）；写进 case.json | 自检/连接脚本对不上，边界偏差全是几十毫米（P47） |

新建案例目录：
```bash
cd E:/work/skill/气帘自动网格划分
cp -r cases/cab2 cases/<新案例>
vim cases/<新案例>/case.json      # 只改 case / model / layers.cid / parts / assemble
mkdir -p /path/to/<新案例>/input /path/to/<新案例>/out
cp <模型>.hm /path/to/<新案例>/input/
```

---

## 1. 一键主链（先跑通，再讲究质量）

```bash
bash scripts/drivers/run_case.sh --case cases/<案例>/case.json --work /path/to/<案例>
```

七个阶段各自都能单独重跑，别整链反复跑：

| 阶段 | 命令/脚本 | 跳过方式 |
|---|---|---|
| ① 线采样 | `stage1_survey/export_lines_pts.tcl` | `SKIP_LINES=1`（复用 out/lines_pts.txt） |
| ② 自动成环 | `stage2_partition/chain_loops.py` | 不能跳，这一步是分区正确性的体检 |
| ③ 生成 Tcl | `drivers/gen_step1_tcl.py` | 不能跳 |
| ④ 三面网格 | `hmbatch out/step1_gen.tcl` | 没有单独跳过开关；要跳过前面所有阶段用 `GATE_ONLY=1` |
| ⑤ 拉带 | `TETHER_SCRIPT` / `TETHER_TCL` | 无拉带的产品整段跳过 |
| ⑥ 组装 | `stage4_assemble/assemble_cab2.py` | 不能跳 |
| ⑥b 锚固 | `plan_anchors.py` → `gen_tabs_anchored.py` → 再组装 | `ANCHORED_TETHERS=0` |
| ⑦ 门禁 | qa_strict / auto_gate / mesh_quality / partition_cover | `GATE_ONLY=1` 只跑这段 |

**只跑门禁**（改参数后最常用）：
```bash
GATE_ONLY=1 DECK=out/curtain_airbag.k \
  bash scripts/drivers/run_case.sh --case cases/<案例>/case.json --work /path/to/<案例>
```

---

## 2. 分阶段验收标准（每步都有硬数字，对不上就停）

### ① 线采样
```bash
# 产出 out/lines_pts.txt，每行一条线的点云
grep -c '' out/lines_pts.txt
```
**该看到**：线数 ≈ 4 个分区的曲线总数（cab2 = 35+87+43+531 里的**真实**线数，实测 338~700）。
**看不到**：
- 0 条 → `COMPS` 串和 .hm 里的 collector id 对不上（先跑 `stage1_survey/survey_comps.tcl` 看真实 id）
- 只有一个分区有线 → 某个 collector 是空的/线在别的 collector（P28：**别信 comp 名字，按面积判**）

### ② 自动成环（★最重要的体检）
```bash
python scripts/stage2_partition/chain_loops.py out/lines_pts.txt --out out/loops.json --tol 0.8
```
**该看到**：seam 闭环数 = 缝线条数（cab2 = 6），`opens` 为空或 gap < 2mm。
**看不到**：
- 闭环数多于缝线条数 → tol 太大把相邻环串了 → 降到 0.5 再看
- `opens` 里 gap 几十毫米 → CAD 本身有缺口，**别用大 tol 硬补**，回 CAD 端补线（P39）
- 完全串成一根面条 → 线号重复或区间重叠

> **这一步 30 秒，能省后面 2 小时。** 环不对，后面裁切拓扑必然错。

### ③ 生成 Tcl（干跑先看）
```bash
python scripts/drivers/gen_step1_tcl.py --case cases/<案例>/case.json \
  --loops out/loops.json --out out/step1_gen.tcl --dry-run
```
**该看到**：缝面数 = 闭环数、气腔面数 = 1（带洞）、布带面数 = 1，`*surfacemarksplitwithlines` 的线号都非空。
**看不到**：缝面 0 个 → loops.json 里 seam 没成环，回 ②。

### ④ 三面网格
```bash
D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe -tcl out/step1_gen.tcl -nolock
cat out/<case>_step1_bl_report.txt
```
**该看到**（cab2 基线）：`__HW_DONE__` + 布带/气腔/缝线三个 txt，`blmesh` 报告带边界层。
**关键校验**：缝面是**洞内面**不是 spline 面（P12），否则界面共节点 = 0。
界面共节点检查：组装后 `气腔剩 N 节点，其中距界面 <3mm 未合并` 应 < 1%。

### ⑤ 拉带（含侧面拉带）
```bash
# 轮廓先出来
python scripts/stage2_partition/tether_side_outline.py   # 侧条 → out/side_tether.json
python scripts/stage3_mesh/gen_tabs_tcl.py               # 主拉带 → out/tabs.tcl
```
**该看到**：主拉带 txt + 侧条 txt **两份都在 out/**。
**看不到**：只有主拉带 → 侧条静默丢了（P48）。侧条是"缝在布带内部"的，`plan_anchors.py` 拿不到，
必须单独走 `tether_side_outline.py` → `gen_side_tab_full_outline.py`。

### ⑥ 组装
```bash
STEP1=<step1.txt> STEP2=<tabs.txt> STEP2B=<side.txt> \
REQUIRE_PARTS="belt cavity seam tether side" \
TAB_TOL=0.35 SNAP_INSIDE_TOL=3.0 WEAK_ANCHOR_MIN=1 \
python scripts/stage4_assemble/assemble_cab2.py
```
**该看到**：
```
读入: step1 nodes=... step2 nodes=... step2b nodes=...
   [belt] ...   [cav] ...   [seam ...] ...   [tether] ...
   主拉带: .../tabs_triple_export.txt
   侧面拉带: .../cab2_step2b_side2.txt     ←★ 这两行必须都出现
```
**看不到 `侧面拉带:` 这行 → 直接停**，不要往下跑门禁（P48）。

### ⑥b 锚固边（拉带整齐的唯一解）
```bash
python scripts/stage3_mesh/plan_anchors.py --k <deck> --belt 2 --cav 3 --tether 5 \
       --out out/anchors.json --png out/anchors.png
python scripts/stage3_mesh/gen_tabs_anchored.py --polys out/tether_full.json \
       --anchors out/anchors.json --model <model>.hm \
       --out out/tabs_anchored.tcl --export out/tabs_anchored_export.txt
hmbatch.exe -tcl out/tabs_anchored.tcl -nolock
# 再组装一遍（TAB_TOL=0.35）
```
**该看到**（`anchor_metric.py` + `tab_anchor_stat.py`）：
- 锚固排宽度 **5.000mm**（±0.05），σ ≤ 0.05
- 翘曲 max ≤ 35°，最小角 p1 ≥ 8°
- `tether∩belt > 0`、`tether∩cav = 0`、`tether∩seam = 0`

**看不到**：
| 现象 | 根因 | 查 |
|---|---|---|
| 宽度 4.7~5.3 漂 | 锚固链端点落在面外/贴轮廓，中间块被截短 | P52 |
| 翘曲 60~80° | 用了显式节点方案（polyline/band/hybrid） | P50 |
| 某块拉带完全没锚点 | 该块没有布带自由边锚点 → 内部锚固 | P53 |
| 报 `Selected lines do not form a combined curve` | 三刀里的线没贯穿面 | P51 |

### ⑦ 四道门禁（全过了才允许交付）

```bash
python scripts/gate/qa_kfile_strict.py <deck>                       # ① 严格 K 校验
python scripts/gate/auto_gate/run_gate.py --case cases/X/gate_case.json  # ② 业务门禁
python scripts/gate/mesh_quality_gate.py <deck> --pids 2,3,4,5      # ③ 质量门禁
python scripts/gate/partition_cover_check.py --k <deck> \
       --pids 2,3,4,5 --manifest out/ref_manifest.json              # ④ 分区覆盖（防丢块）
```

| 门禁 | PASS 判据 | 退出码 | 查不出什么 |
|---|---|---|---|
| qa_kfile_strict | 致命 0 / 警告 0 | 0 | 几何对不对 |
| auto_gate | FAIL 0 | 0/1 | 整块丢 |
| mesh_quality_gate | 不合格率 ≤ 5% | 0/2 | 整块丢（丢了反而更"合格"） |
| **partition_cover_check** | 组分个数 + 面积 ±3% | 0/2 | — 专治整块丢 |

**第一次跑没有基线**，先建一次：
```bash
python scripts/gate/partition_cover_check.py --k <第一个认可的 deck> --pids 2,3,4,5 \
       --write out/ref_manifest.json
```
之后每次交付都对拍。**没有 baseline 就等于没这道门禁。**

---

## 3. 一次完整通过长什么样（cab2 v8 实测，照这个对数字）

```
单元 83808 / 节点 82102
PID{2:5315, 3:74822, 4:879, 5:2792}      ← 四个 PID 都有量
单元类型 4节点 81175 / 3节点 2633        ← 三角占比 3.14% < 8%
拉带组分 9 个                             ← 关键：块数对，不是"有量"就行
PID5 面积 64550 mm² (基线 64683.5, -0.21%)
不合格 82 = 0.10%   (PID2 8 / PID3 8 / PID4 0 / PID5 66)
tether∩belt 77 / ∩cav 0 / ∩seam 0
qa_kfile_strict 致命 0 警告 0
auto_gate PASS 3 / WARN 2 / FAIL 0
partition_cover_check PASS 四个 PID 组分与基线一致
```

---

## 4. 换案例时"哪些必须重算、哪些能继承"

| 项 | 新案例 | 说明 |
|---|---|---|
| PID 语义 | **必须重算** | 用 `survey_comps.tcl` 按 spline 面积定，别继承上一个案例（P28） |
| 缝线环 | **必须重算** | `chain_loops.py` 自动，别手抄 line id（`references/16`） |
| `parts` 清单 | **必须重写** | 该案例到底有没有侧条/几块凸台，直接决定缺件是否硬失败 |
| 网格尺寸 | 按最小特征定 | 5mm 起步；最小边 < 3mm 的部位要么 BL 要么局部加密 |
| `bl_thick/bl_layer` | 可继承 4.0 / 1 | washer 首选 `*blmesh_2d2` 前置，顺序不能变（`references/14`） |
| `tab_tol/snap_inside_tol` | 可继承 0.35 / 3.0 | 只有"内部锚固"（缝在布带里）的块才需要 3.0 |
| `weak_anchor_min` | 可继承 1 | **别用默认 8**，会误伤凸台（P53） |
| 拉带轮廓 `tether_full.json` | **必须重做** | 不同案例块数/形状差异大，这是泛化边界（见 `references/16` §10） |
| 门禁基线 manifest | **必须重建** | `--write` 一次，之后对拍 |
| gate_rules.json | 一般不动 | 新案例首次跑出的 WARN 先看是不是口径问题再改 |

---

## 5. 出问题怎么定位（三分法）

**先问：是几何问题、网格问题、还是口径问题？**

```
形状不对 / 某块没了        → 几何（分区）问题 → 回 ② 看环，回 ③ 看面数
有网格但畸形 / 翘曲大      → 网格问题     → anchor_metric / mesh_quality_gate 定位到单元
数字不合格但肉眼看没错     → 口径问题     → 看 gate_rules.json 的判据是否符合这个案例
```

**"某块没了"专项流程**（cab2 踩过，代价最大）：
1. `partition_cover_check.py` 报出丢失块的面积+质心 → 拿坐标在图上看是哪个部位
2. 回 ⑤ 看该部位的 txt 在不在
3. 不在 → 生成脚本没跑到它（`out/` 清空、`STEP2B` 没给、脚本只打 WARN）
4. 在 → 组装没读进去（`STEP2B` 名字不对、`REQUIRE_PARTS` 没声明）
5. **不要靠肉眼在 CAE 里翻** —— 整块丢最容易被"看起来元素很多"骗过。

---

## 6. 交付物清单（少一样都算没做完）

| 文件 | 必须有 |
|---|---|
| `<case>_curtain_airbag_vN.k` | 最终网格，纯 ASCII，`__HW_DONE__` 之后无残留 |
| `out/ref_manifest.json` | 分区覆盖基线（下次回归用） |
| `out/qgate.json` + `qgate.png` | 质量门禁明细 + 云图 |
| `out/gate_report.json` + `gate_figs/*.svg` | auto_gate 报告 |
| `out/anchors.png` | 锚固链位置（换人接手时唯一能对上几何的东西） |
| `<case>_网格交付报告_vN.md` | 结论表 + 门禁明细 + 已知残留 |
| CHANGELOG 一条 | 案例 + 结果 + 新增/修正规则 |

---

## 7. 什么时候该停下来问人

技能能自动跑，但这几件事**必须人定**，不要自己猜：

1. **充气口封不封口** —— 设计决定，不是网格问题（cab2 X 616–881 至今未定）
2. **缝线条数对不对** —— ② 出来的闭环数要跟图纸数对，多一个少一个都要人确认
3. **拉带块数对不对** —— `partition_cover_check` 只保证"跟上一次一样"，第一次的基线要人认
4. **质量口径** —— 要方正四边还是允许全三角，是项目要求（`references/15`）
5. **门槛放宽** —— `gate_rules.json` 的任何放宽都要留 `_changelog` 一行说明为什么

---

## 8. 接新项目时，先跟客户要这 5 样

缺任何一样，链一定卡在第 ② 或 ③ 步，而且**卡住的时候看不出是输入不全**。

| # | 要什么 | 为什么 | 缺了会怎样 |
|---|---|---|---|
| 1 | **按分区拆好的 CAD 曲线**（4~6 个 layer/collector：布带/气腔/缝线/拉带） | 分区的语义只有客户知道，不能靠几何猜（"几何归机器、语义归人"） | 全挤在 1 个 component → 只能靠面积/位置硬分类，错一次后面全错 |
| 2 | **缝线条数 + 每条缝线的走向意向**（图纸标注或截图） | ② 成环会给出 N 个闭环，必须跟真实缝线数对上 | 多环少环都发现不了，网格出来才发现缝合线位置不对 |
| 3 | **拉带块数 + 每块是"外边界锚固"还是"缝在布带内部"** | 决定走三刀切还是内部锚固二次焊接（P53） | 内部锚固的块拿不到锚点，过渡排松散 |
| 4 | **厚度方向约定**（哪根轴是厚度、各层偏移） | `case.json` 的 `thickness_axis` / `layers.z` | 分层全错，气腔双层做不出来 |
| 5 | **充气口位置 + 封不封口**（设计决定） | 影响气腔开孔与封口网格 | 自己猜 = 返工（A3 至今 BLOCKED） |

**加分项**：一张参考模型的网格截图（哪个 PID 是布带、拉带贴在哪）。有截图能省掉
一半的 PID 语义争论（参考模型 PID 界面是最快的仲裁手段）。

---

## 9. 连续跑多个气帘时的节奏（工作流模式）

不要"一个气帘从头调到完美再下一个"。按这个节奏走，吞吐和稳定性最好：

```
第 1 个案例：全链打通，建立 4 道门禁 + 基线 manifest        ← 慢，1~2 天
第 2 个案例：只改 case.json，跑链；卡在哪补哪               ← 半天
第 3 个案例起：90% 时间花在 ② 成环 + ⑤ 拉带轮廓，其余全自动  ← 2~4 小时
```

**每接一个新案例，只允许新增三类东西**：
1. `cases/<新案例>/case.json`（参数）
2. `cases/<新案例>/gate_case_vN.json`（校验口径，通常复制改路径）
3. `out/tether_full.json`（拉带轮廓，案例级产物）

**不允许**为新案例改 `scripts/` 里的流程脚本。一旦想改，先问：
这是"这个案例的特殊性"（→ 进 case.json）还是"流程少了一条规则"（→ 进脚本 + 补 P 坑位 + MD5 回归）？

**回归义务**：每次改 `scripts/`，把 `cases/` 下所有已登记案例重跑一遍，
数字对不上就回滚（`20_baselines.md` 是判据）。
