# 11 · cab3 类项目全自动流水线（曲线 → 三环共形网格 → Y 分层 K → 全门禁）

> 沉淀自 2026-10-24 cab3 实战。**目标：全自动、非人工干预。**
> 入口：`scripts/cab3_auto/run_cab3.sh`（换项目只改环境变量，脚本内零硬编码）

---

## 1. 一键用法

```bash
export WORKDIR="E:/work/AI_CAB/onekey/work/cab3"        # 工作区
export REFDIR="E:/work/AI_CAB/ref-Output/Model_update"  # 参考模型（MAT.K + 03_Control_card.k）
export MESH_START="5.0"    # 起始网格 mm（用户要求的名义尺寸）
export MESH_MIN="2.0"      # 自动调优下限
export CMAX_LIMIT="0.5"    # 边界绝对偏差门限 mm
bash scripts/cab3_auto/run_cab3.sh
# 只跑门禁/组装/渲染（复用已有网格）:  SKIP_HM=1 bash run_cab3.sh
```

| 阶段 | 脚本 | 产物 |
|---|---|---|
| S1 环链分析 | `loop_analyze.py` | `loops_all.json`（按 comp 把所有 line 连成链） |
| S2 环序构建 | `build_loops3.py` | `loops_v3.json`（belt/cavity/holes 正确闭合环） |
| S3 网格 Tcl | `gen_step1_v3.py $MESH` | `cab3_step1_v3.tcl` |
| S4 hmbatch | — | `cab3_step1_v3_mesh.txt` |
| S5 形状门禁 | `shape_gate_v3.py` | `shape_gate_v3_report.json` |
| S6 组装 | `assemble_v3.py` | `cab3_full_v3.k` |
| S7 结构门禁 | `final_gate.py` + `tether_conn_check.py` | 控制台 |
| S8 渲染 | `render_final.py` | `v_final_shape/layers/port.png` |

**S3-S5 是闭环**：形状门禁 FAIL → 网格尺寸减半 → 重跑，直到 PASS 或触底 `MESH_MIN`。
退出码：门禁 PASS=0 / FAIL=1，驱动据此判断。

---

## 2. cab3 几何事实（换项目必须重新确认）

| 项 | 值 |
|---|---|
| comp1 | 109 线 / 12 链，**充气口细节曲线群**（同心弧缝线 + 尖部 1.6mm² 小圆环），仅 1 个闭环 |
| comp2 布带 | 67 线，环面积 52963.2 mm²，含充气口凸舌（伸到 y=202.04） |
| comp3 气腔 | 109 线 = 94 主环 + 3 小闭环(681-685 / 698-702 / 710-714)，环面积 40359.0 mm² |
| comp4 缝线 | 40 线 / 3 环：seam0 370mm²(1.77mm 窄带) / seam1 203mm²(2.26mm) / seam2 562mm² |
| comp5 拉带 | 586 线 / 80 链，10 条 |
| 嵌套 | cavity ⊂ belt；3 缝环 ⊂ cavity；3 小洞 ⊂ cavity |
| 期望区 | belt − cavity = 12604 mm²；cavity − 3缝环 − 3小洞 = 38991 mm² |

### 2.1 充气口凸舌与 773 拆分（cab3 特有，通用教益是"端点落在他线上"）

- comp3 线 **750 的终点 (463.961,186.859) 正好落在 comp3 线 773 上**（<0.5mm）。
- 若不拆，气腔环在 750→773 桥接处产生 **4 处自交（spike）**。
- 拆法：布带环用 773 全长；气腔环只走"交界点→815"段（记作 7730）。
- **通用规则**：链式追逐时若下一条线起点与更早点重合，或落在他线内部，必须拆分/跳过。

### 2.2 充气口封口（v3 新增）

- 气腔自由边界 884 条边中：524 与布带共边、281 与缝线共边、65+8=73 属 3 个小洞、
  **只剩 6 条 / 17.2mm 在凸舌尖端（x 455.9-464.0, y 186.9-202.0）未共边** ——
  这是气腔舌尖戳出布带约 1mm 的那段，也是气腔上下两层唯一没合上的地方。
- 封口做法：把这 6 条边的 `cav_up`/`cav_low` 节点用**捏合四边形**缝起来（PID3），
  节点不搬家、不产生退化单元。参考模型（5P-BAG_004.key）同样只有 ~22 个跨层单元，印证这是小特征。

---

## 3. 形状门禁 v3 的四项指标（交付门径）

| 指标 | 定义 | 门限 |
|---|---|---|
| A 充满度 | 期望区域内采样点被本 PID 覆盖比例 | ≥ 0.995 |
| B 面积自洽 | 网格面积 / 期望区域面积 | 0.90 ~ 1.10 |
| C 边界贴合 | 原始曲线点 → 网格**自由边界边**距离 | cmax ≤ `CMAX_LIMIT`(0.5) **且** cratio ≤ 1.0 |
| D 反向贴合 | 网格自由边界节点 → 原始曲线**线段**距离 | ≤ 0.5mm |

### 3.1 C 的弦误差自适应（关键，P 新增）

直边替代圆弧的固有矢高 = `L²/(8R)`。5mm 网格跨 R=5.8mm 圆弧 → 矢高 0.55mm，
用固定 0.5mm 门限会**误判**（cab3 5mm 实测 cavity C=0.638，全部是诚实弦误差）。

```
allowed(p) = DP_EPS(0.2) + L(最近网格边)² / (8·R)
R = circumradius(边端点a, 边上最远原始曲线点q, 边端点b)   # 自洽，无曲率模型
cratio = max(dist(p, e) / allowed(p))                       # ≤ 1.0 为诚实
```

DP_EPS=0.2 是折线简化的固有偏差，两项相加即"网格能达到的最好水平"。

### 3.2 三个必须躲开的测量伪差（都是本轮实测踩过的）

1. **洞贴合必须用原始线采样点，不能用闭合环。**
   洞环两端点落在气腔主边界上（1.4mm 缺口），`chain_from_seq` 用直线桥接闭合，
   而这条桥接弦横切气腔急弯 → 实测伪差 **0.696mm**，改用原始线点后真实值只有 **0.194mm**。
2. **拉带链要剔"针状突出"。** 链式追逐伪迹：`A →(直线)→ A` 去而又回，面积为零，
   HM automesh 正确忽略它，门禁却报 0.542mm 假 FAIL。剔除条件：
   精确重复点 + 子路径共线（同向或反向）。
3. **D 检查必须用"点→线段"距离**，不能点→点：原始曲线采样间距可达 6.9mm，
   点→点会误报 3.4mm。已用 `SegGrid` 空间索引。

---

## 4. 网格命令选型（实测对比，2026.0.0.27）

| 命令 | cav 单元 | cavC | beltC | min边 | 共形(b-c / c-s) | 结论 |
|---|---|---|---|---|---|---|
| `*interactiveremeshsurf 1 5.0 2 2 2 1 1` | 3088 | 0.638 | 0.297 | 0.435 | 327 / 281 | 基线，C 超限 |
| `*interactiveremeshsurf 1 3.0 ...` | 5356 | **0.289** | 0.297 | 0.435 | 524 / 281 | **采用** |
| `*surface_chordalmesh 1 5.0 0.15` | 25228 | 0.509 | 0.509 | **0.070** | 621 / 81 | 弦误差驱动可用但共形崩、碎单元 |
| `*surface_chordalmesh 1 5.0 0.05` | 29149 | 2.601 | 46.061 | 0.025 | **0 / 0** | 布带直接网格失败 |
| `*defaultmeshsurf_growth 1 5.0 2 2 2 1 1 1 35 0 1.5 5.0 0.15 20 1.3 1 3 1 0` | 2670 | 0.561 | 0.297 | 0.435 | 345 / 281 | 弦误差参数没起作用 |

**结论**：`*surface_chordalmesh` 的签名是 `mark size chordal_dev`（可用，r=0），
但它不顾相邻面的边密度 → 共形性崩（cav-seam 共享边 281→81）、碎到 0.07mm。
**交付用 `*interactiveremeshsurf` + `*setedgedensitylinkwithaspectratio -1`，靠门禁自动调尺寸。**

### 4.1 其它 2026 坑（本轮新确认）

- `*surface_chordalmesh` 在 hmbatch 里 `catch` 到错时 `e` 变量是 `0` 不是错误文本，
  只能靠 `r` 和单元数判断成败。
- **`*readfile cab3.hm` 是 spline 建面的前提**：不读文件、模型为空时
  `*surfacesplineonlinesloop` 报 "Failed to construct spline surface"（合成几何试了一下午才定位）。
- hmbatch 里 `open "绝对路径/report.txt" w` 偶发 "Permission denied"，
  **用相对路径 + `cd` 到运行目录**最稳（`runs/<tag>/`）。
- `foreach _kv {LsDyna Keyword971_R16.0}` 是**单个字符串**不是两个元素，
  `loaduserprofile` 会带两个参数报错被 catch —— 不影响纯几何操作，但要知道它没生效。

---

## 5. cab3 交付结果（2026-10-24，MESH=3.0 / SEAM=2.5）

```
ring      期望面积   网格面积   面积比    A充满   C绝对  C自适应  D反向   判定
belt       12604     12609  1.0004  0.9994  0.297  0.748  0.193  PASS
cavity     38991     38967  0.9994  0.9990  0.289  0.977  0.193  PASS
seam0        370       371  1.0029  1.0000  0.235  0.551  0.183  PASS
seam1        203       201  0.9898  1.0000  0.218  0.506  0.152  PASS
seam2        562       554  0.9866  1.0000  0.196  0.495  0.168  PASS
tether0-9                             1.0000  1.0000  0.000-0.131 0.000 PASS
holes(3)      -         -       -       -    0.194  0.471    -    PASS
→ ALL PASS
```

`cab3_full_v3.k`：13193 节点 / 13770 单元
（PID3=12328 含双层 2×5356 + washer 1610 + 充气口捏合 6；PID2=1075；PID4=250；PID5=117）

结构门禁：G1 重复节点 0 / G2 重复单元 0 / G3 引用完整 0 缺失 /
G5 连通 1 个分量 / G6 跨 PID 共享边 (2,3)=524 (3,4)=281 (2,5)=13。
拉带检查：34 共节点 + 13 共享边，Y 从 -1.0 到 0.0，全模型 1 个连通分量 → 全 PASS。

### 5.1 已知 WARN（需向客户说明，非缺陷）

- `final_gate` G4 报 42120 条边 < 3mm：其中 3220 条是 washer/捏合的**厚度向 0.5mm 边**（Y=±0.5 分层固有，
  与参考模型一致）；其余是 3mm 名义网格下 2-3mm 的边（名义尺寸合规）。
- 4 个布带圆头单元最小边 0.435mm（HM automesh 在 R≈4mm 圆头的固有产物）。
- 规范 2.2"每部件无自由边"按"外边界允许、内部不允许"理解：PID2 自由边 775 / PID3 164 / PID4 281 / PID5 146，
  全部位于模型外边界与充气口，内部无自由边。

---

## 6. 换项目检查清单

1. `loop_analyze.py` 看每个 comp 的链数/闭环/面积，确认哪个是 belt/cavity/seam/hole/tether
2. `build_loops3.py` 写环序（BELT_ORDER / CAV_ORDER / HOLES / seam），跑完看
   `close_gap`、`自交=0`、面积是否与 HM 建面面积一致
3. `render_port.py` 类脚本渲染环叠加图，**目视确认**（用户要求：几何归机器，语义归人，但要出图）
4. `run_cab3.sh` 一键跑，门禁不过自动细化
5. 门禁 PASS 后，把 `MESH` 实际值、C/Cr 数值、`cab3_full_v3.k` 规模写进交付说明
