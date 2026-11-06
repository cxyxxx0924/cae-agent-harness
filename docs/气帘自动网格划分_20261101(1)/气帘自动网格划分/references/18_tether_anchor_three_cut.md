# 18 — 拉带锚固边受布带约束：三刀切

> 适用：任何"一层网格已经定死，另一层要沿着它的边界缝上去"的场景。
> 气帘里就是 **拉带(PID5) 缝在布带(PID2) 上**。同样的思路可直接用于拉带↔气腔、
> 缝线↔气腔、以及任何需要跨层共节点的界面。
>
> 首次落地：cab2 v4（`cab2_curtain_airbag_v4.k`），锚固排 8 块全部 5.000mm 等距、偏差 0.000mm。

---

## 1. 病：为什么"硬共节点"必然畸形

旧链路三步：

1. 拉带面在 Z=−1 独立 `automesh 5mm` → 第一排节点落在**它自己的网格相位**上；
2. 组装时按最近邻把拉带第一排吸附到布带节点；
3. 吸附＝把节点挪到布带节点位置。

第 3 步横向位移最多可达一整格（5mm）。两类后果：

| 触发条件 | 后果 | 实测（cab2 v3） |
|---|---|---|
| 两个拉带节点争同一个布带节点 | 输的那个留在 Z=−1，拉出 **60~78° 扭转片** | 每块两端各 1 个 |
| 端点距拉带轮廓只剩 0.2~0.5mm | 薄条单元，最小角归 0° | 翘曲 max **165.7°** |

**结论：问题不在吸附算法，在"拉带第一排节点本来就不在布带的节点相位上"。**
吸附只是把错误暴露出来。换更聪明的吸附（力导向、迭代松弛）只会把 5mm 的错位摊成
一排 2mm 的错位，最小角还是崩。

正确方向：**先让布带定出锚固点位置，再让拉带的网格线穿过这些点。**

---

## 2. 第一步：反求锚固链（`plan_anchors.py`）

```python
# 布带自由边 = 全部边界边 − 与气腔共享的节点
bnd = sorted(bnd_all - cav_n)
# 保留落在【拉带真实轮廓环】内部的点
# 按边界邻接排序成链
```

三条必须遵守的口径：

1. **必须排除布带-气腔界面节点。**
   把它们算进锚固链，组装后 `tether∩cav` 从 0 涨到 30（参考模型要求 0）。
   v3 的 `tether∩belt=94` 里就混着这类误配。
2. **判定用拉带真实轮廓环，不要用凸包。**
   凸包对 L 形/梯形拉带会让范围虚大 70mm。
3. 锚固链长度应尽量接近网格尺寸的整数倍（5mm×n）。非线性长度（圆弧端、圆角）
   会让 automesh 的均分出现累积偏差。

输出格式（`anchors_v4.json`）：

```json
[{"blk": 0, "ids": [1400,...], "chain": [[499.72,382.56], ...],
  "n": 7, "span": 29.996, "hull": [[...]]}]
```

---

## 3. 第二步：三刀切（`gen_tabs_anchored.py`）

### 3.1 为什么不能少切、不能多切

`*surfacemarksplitwithlines` **只接受贯穿面的线**。线落在面内会报
`Selected lines do not form a combined curve`，返回 r=1，面不变。

| 切法 | 实测结果 |
|---|---|
| 只横切一刀（沿链方向过锚固线） | 中间块被凸台轮廓截短 → 间距 **5.137mm**，累积偏差 1.7mm |
| 锚固链拆成 5mm 分段短线逐条切 | 每个公共端点生成**两套节点**（间距 min=0.00），网格不连续，比不切更糟 |
| **三刀**：过链两端各切一刀（沿链**法向**）+ 沿链方向过锚固线切一刀 | 中间块宽度＝锚固段长度（被 5mm 整除）→ 间距 **5.000mm、偏差 0.000mm** |

### 3.2 三条线的构造

```python
def cut_lines(chain, poly, margin=1.25):
    """三条切线 (x0,y0,x1,y1): P0 处法向 / Pn 处法向 / 过中点沿链方向"""
    p0, pn = chain[0], chain[-1]
    d = norm((pn[0]-p0[0], pn[1]-p0[1]))     # 链方向
    n = (-d[1], d[0])                        # 链法向
    x0, y0, x1, y1 = bbox(poly)
    L = math.hypot(x1-x0, y1-y0) * margin     # 必须延伸到面外
    def thru(p, dv):
        return (p[0]-dv[0]*L, p[1]-dv[1]*L, p[0]+dv[0]*L, p[1]+dv[1]*L)
    mid = ((p0[0]+pn[0])/2, (p0[1]+pn[1])/2)
    return [thru(p0, n), thru(pn, n), thru(mid, d)]
```

```
        ┌───┐  ← 竖切 P0 处（沿法向，两端都延伸出凸台外）
   ┌────┤ A ├────┐
   │    └───┘    │
   │  B  │ C │ D │      C = 锚固块，宽度 = 锚固段长度
   │    └───┘    │      横切 = 沿链方向过锚固线
   └────┤   ├────┘
        └───┘  ← 竖切 Pn 处
```

### 3.3 Tcl 关键序列

```tcl
*readfile "$P/input/cab2.hm"
*elementorder 1                          ;# 必须在 readfile 之后！
*setedgedensitylinkwithaspectratio -1

# 建轮廓面
*createlist nodes 1 $u $v
*linecreatefromnodes 1 0 150 5 179
*surfacesplineonlinesloop 1 1 0 1

# 三刀切
*createmark surfaces 1 $sid
*createmark lines 2 $cut0
*appendmark lines 2 $cut1
*appendmark lines 2 $cut2
*surfacemarksplitwithlines 1 2 0 13 0

# 逐块 automesh（新面 id > 切之前的 maxid）
*createmark surfaces 1 $s
*interactiveremeshsurf 1 $sz 2 2 2 1 1
*automesh 0 2 2
*storemeshtodatabase 1
```

**顺序铁律：建面 → 切 → automesh，逐块做。**
先建完全部面再切，面 id 会串块（新面 id 靠 `> $maxid_before_cut` 识别）。

---

## 4. 端点取舍（最容易翻车的地方）

### 4.1 端点必须落在面内

链端点若在凸台轮廓**外** 1.5~4.7mm，竖切线切不到面，中间块被轮廓截短，
间距从 5.00 变成 4.73，累积偏差 1.57mm。

→ `trim_chain()`：把链裁剪到面内。

### 4.2 端点距轮廓太近必须外推到边界

端点距轮廓只剩 0.2~0.5mm 时，竖切线切出一条薄条；automessh 在薄条里生成退化单元；
组装时薄条的两个拉带节点争同一个布带节点，输的那个留在 Z=−1，拉出 60~78° 扭转片
（实测 v4d 每块两端各 1 个）。

→ 端点外推到凸台边界，切缝落在轮廓上，中间块从轮廓起算，薄条消失。

### 4.3 但外推阈值必须小：只对 `dmin ≤ 0.6mm` 外推

阈值放大到 2.5mm 反而破坏对齐：块0 端点距边界 1.47mm 被推走，
锚固点整体平移，6 个点里只剩 3 个能配上布带节点。

```python
NEAR = 0.6
if dmin(p) > NEAR:
    return p        # 离得远的端点原地保留
```

---

## 5. 组装：吸附容差要收紧

```bash
TAB_TOL=0.35 SNAP_INSIDE_TOL=0 STEP1=out/cab2_step1_bl.txt \
STEP2=tabs_anchored_export.txt python assemble_cab2.py
```

锚固排已经横向对齐，只剩下 Z 从 −1 抬到 0：

| | v3 | **v4** |
|---|---|---|
| 吸附最大位移 | 3.00mm | **0.26mm** |
| `TAB_TOL` | 3.0 | **0.35** |
| `SNAP_INSIDE_TOL` | 3.0 | **0** |

`TAB_TOL` 放松到 3mm 会把"本来就不该配"的节点也吸过去，等于把三刀切的成果又抹掉。

---

## 6. 验收：三层指标

### 6.1 逐凸台几何（`tab_anchor_stat.py`）

沿每条锚固链建局部坐标（s 沿链、t 法向），只统计"同时含 Z=0 与 Z=−1 节点"的过渡单元：

| cab2 v4 | 值 |
|---|---|
| 过渡排宽度 | 5.00~5.07mm（7/8 块恒 5.00） |
| 上下边错位 σ | 0.00~0.10mm |
| 三角单元 | 0 |

对照 v3：宽度 0.33~10.00mm，σ 最高 1.72，两块有 10.00mm 双格宽。

### 6.2 过渡排质量（`anchor_metric.py`）

| 指标 | 判据 | v3 | **v4** |
|---|---|---|---|
| 过渡单元数 | — | 186 | **136** |
| 最小角 p1 | >0 | 0.0° | **8.3°** |
| 翘曲 max | ≤15° | **165.70°** | **32.97°** |
| 翘曲 >15° 单元 | 0 | 53（28.5%） | **23（16.9%）** |
| 蝴蝶结（共线） | 0 | 0 | **0** |

翘曲的**正确算法**（别用单三角法向，会恒出 180°）：

```python
n1 = np.cross(P[1]-P[0], P[2]-P[0])      # 三角 0-1-2
n2 = np.cross(P[2]-P[0], P[3]-P[0])      # 三角 0-2-3
warp = degrees(arccos(clip(dot(n1,n2)/(|n1||n2|), -1, 1)))
```

### 6.3 连接性质（`tether_conn_check.py`）

```
组分 8 | PASS 8 | FAIL 0 | 未连接 0
拉带↔布带 58 | 拉带↔气腔 0 | 拉带↔缝线 0 | 退化 0
```

---

## 7. 已知极限（说清楚，别指望它全自动）

### 7.0 先看清"过渡排"到底由什么组成

按「单元里有几个节点在锚固线上」分类（cab2 v4 实测）：

| 类型 | 数量 | 宽度 | 说明 |
|---|---|---|---|
| **双节点过渡**（2 个在锚固线上） | **99** | **5.00mm**，错位 σ ≤0.10 | 这是锚固排本体，本方法的成果 |
| 单节点翻边（1 个在锚固线上） | 36 | — | 每块 4~5 个，位于锚固段两端与侧边折角＝缝边翻折的物理形态 |
| 单节点翻边中翘曲 >15° | 23 | — | 最差 32.97° |

**验收时务必分开统计**。只看"所有跨 Z 单元"会把 36 个翻边单元混进来，得到"过渡排 17% 不合格"的悲观结论；
只看"双节点单元"则是干净的 5.00mm。`tab_anchor_stat.py` 用的是后者（要求上下边各 ≥2 点），
`anchor_metric.py` 用的是前者（宽口径）。

| 残留 | 成因 | 能否自动修 |
|---|---|---|
| 单节点翻边 15~33° 翘曲 | 布带 Z=0、拉带 Z=−1，1mm 面外偏置必须在过渡排抬起；过渡排纵深仅 2mm → 坡度 26.5° | 需改 Z 斜坡（0 → −0.5 → −1 两阶过渡），翘曲约减半，代价是拉带不再等厚 |
| 每块凸台**顶角** 0.3~0.9mm 窄条（最短 0.317mm） | 竖切弦线在凸台顶角附近与侧边近乎平行，夹出窄条 | **不能**在现框架内修：外贴轮廓会破坏 5mm 整除，间距漂到 5.1~5.3，锚固点超出吸附容差 → 回到老毛病 |
| 拉带扁平区 0° 最小角 | 拉带简化成平面，四节点共线 | 不修：硬转三角形会切断缝线共节点 |

**同时满足「精确等距」和「无窄条」的两条出路**：
1. **锚固边显式节点序列** —— 把锚固链的点直接建成边上的固定节点，再对该块做保形网格
   （`*surfaceedgesetfixed` 或手工铺面），彻底摆脱 automesh 均分；
2. **微调竖切弦线方向** —— 让竖切线在 P0 附近从"沿链法向"微旋到"与凸台侧边平行"，
   消除顶角窄条，代价是中间块不再是等宽矩形。

两条都是结构性改动，不要在一次调试里顺手改。

---

## 8. 复用清单（换案例照着走）

```
1. 交付层网格（布带/气腔/缝线），确认边界自由边干净
2. plan_anchors.py  →  anchors.json（外边界 − 界面节点 ∩ 拉带真实轮廓环）
3. 检查每条链 span 是否接近 5mm×n；圆弧端会带偏差
4. gen_tabs_anchored.py  →  tabs_anchored.tcl + tabs_anchored_export.txt
5. hmbatch 跑 tcl，看 report 里每块 "面数 / 单元数"
6. tab_anchor_stat.py 验宽度与错位 σ（应为 5.00 / 0.00）
7. assemble_cab2.py（TAB_TOL=0.35, SNAP_INSIDE_TOL=0）
8. anchor_metric.py 验过渡排质量
9. tether_conn_check.py 验 tether∩belt>0、tether∩cav=0、tether∩seam=0
10. render_anchor_side.py 出侧视图做视觉确认
```

---

## 9. HM2026 命令陷阱（本轮踩过的）

| 陷阱 | 表现 | 正解 |
|---|---|---|
| `*elementorder` / `*setedgedensitylinkwithaspectratio` 放在 `*readfile` 之前 | `FatalError: 'The model has not been saved, continue? (y/n)'`，exit=127 | 放到 readfile 之后 |
| `hm_getmaxid` | 不存在 | `hm_entitymaxid` |
| `*createnode` 后假设 id = maxid+1 | readfile 后模型已有节点，id 完全不同 → 线引用错节点 → 同上 FatalError | `set var [hm_entitymaxid nodes]` |
| `hm_nodevalue $nd` 直接 set | 返回 `{x y z}` 花括号串，`llength` 判成 1 | `lindex [hm_nodevalue $nd] 0` |
| `*surfacemark_splitwithlines` | 不存在（多一个下划线） | `*surfacemarksplitwithlines 1 2 0 13 0` |
| `*automesh` 单独调用 | 不生成网格 | 必须紧跟 `*interactiveremeshsurf 1 $sz 2 2 2 1 1` |
| `*surfaceaddpoint` | r=0 但网格与基线完全相同（假成功） | 弃用，回到三刀切 |
| `*surfaceaddpointsfixed` | r=1 参数不对 | 弃用 |
| `*reset` | 不存在 | 用不同坐标区块隔离 |
| Tcl 里写 `[debug]` | 被当命令替换报错 | 改 `DBG` |
| 导出格式 `T tether ...` | 组装脚本 `load()` 只认 `S`/`N` | 用 `S tether <eid> <nodes...>` |
| 模型已存在时重复 `*readfile` | 弹未保存确认 | 每个 tcl 只 readfile 一次，多块在同一会话里顺序做 |

---

## 10. 「显式节点序列」(方案 A) 实测：不如三刀切（2026-11-01 第二轮）

`gen_tabs_anchored.py --mode {triple|polyline|band|hybrid}` 四个模式全部实测过，
同一份 anchors、同一份凸台轮廓、同一次组装参数：

| 模式 | 做法 | 锚固排宽度 | 错位 σ 均值 | 翘曲 max | PID5 <3mm 短边 |
|---|---|---|---|---|---|
| **`triple`**（默认，推荐） | 锚固线 1 刀 + 链两端竖切 2 刀 → 等宽锚固带 | **5.00**（7/8 块精确） | **0.03** | **32.97°** | 235 |
| `polyline` | 沿锚固点建折线，一刀切成两半（真正的"显式节点序列"） | 4.36~5.95 | 0.41 | 81.88° | 188 |
| `band` | 折线 + 上下各一条 5mm 偏置折线 | 4.18~5.32 | 0.08 | 81.59° | 256 |
| `hybrid` | 锚固线换折线，两条竖切保留 | 3.76~5.84 | 0.37 | 78.10° | — |

### 为什么 A 输

**"显式节点序列"只控制"点在哪"，控制不了"配对行跟谁平行"。**

折线切保证锚固线上的节点精确落在锚固点（这点 A 做到了，间距 5.000mm 零偏差），
但锚固线**内侧那一行**由 automesh 按自己的主方向布，配对点会偏 1~2mm，
单元就成梯形 → 翘曲从 33° 涨到 82°。

三刀切之所以齐，是因为它切出一个**矩形锚固带**：带内每行都垂直于锚固线，
配对点必然落在正对面 5mm 处。**这是拓扑性质，不是节点坐标性质。**

结论：根因在"带"，不在"点"。想要两者兼得，只能改第三层——放弃 automesh，
手工铺锚固带（`*createelement` 逐行建），再让其余区域 automesh 与之共形。
那是另一个量级的工程量，暂不做。

### 方案 A 唯一真正的收益

`polyline`/`band` 不再需要竖切弦线，**凸台顶角的 0.3mm 窄条消失**
（<3mm 短边 235→188）。如果哪天顶角窄条变成硬门禁，可以只在**凸台顶角那一小块**
局部换用 `polyline` 模式，而不是整体换。

---

## 11. 侧拉带（布带内部锚固）与"整块丢"事故

cab2 另有一条横向长条拉带：X 1572.4~1771.2 / Y 159.8~183.6 / 2330.6mm²，
根部在布带**内部**（X 1572~1620 与布带重叠 47.8mm），不在布带自由边界上，
所以 `plan_anchors.py` 的边界链拿不到它 —— 它走的是组装脚本的「布带内部锚固排」。
必须在组装时给 `SNAP_INSIDE_TOL>0` **且** `WEAK_ANCHOR_MIN=1`：

```
SNAP_INSIDE_TOL=3.0  WEAK_ANCHOR_MIN=1
```
默认 `WEAK_ANCHOR_MIN=8` 会把 6 个凸台（只有 6~7 个外边界锚点）也判成弱锚去做内部
二次焊接，节点被推开 3mm，最小角 p1 掉。设成 1 就只有"0 个外边界锚点"的侧条会用到。

### 事故：整块丢，所有门禁都看不见

v4 只从 `tabs_anchored_export.txt` 重新生成拉带，而 `out/` 被清空后
`cab2_step2b_side2.txt` 不存在，组装脚本只打一行
`WARN 缺 step2b 侧面拉带, 本次不含` 就继续。结果：

- `qa_kfile_strict` 全 PASS（少一块不影响）
- 质量门禁 PASS（剩下的都正常）
- `tether_conn_check` **8 组分 PASS 8 / FAIL 0**（每块都连着布带）
- `auto_gate` 环面积 PASS（**拉带不在 cad_tag 里**）

**唯一能发现它的是新增的 `scripts/gate/partition_cover_check.py`：**

```bash
python partition_cover_check.py delivered.k --write ref_manifest.json   # 首次建基线
python partition_cover_check.py out.k --manifest ref_manifest.json     # 每次核对
# [FAIL] PID5: 组分 9->8 丢失1块(2354mm²@(1683,172))  64683.5 / 62213.4 (-3.82%)
```

它按 PID 比对「面积 / 连通组分逐个质心匹配 / 包围盒」，少一块立刻 FAIL 并报出
丢失块的面积和位置。已接进 `run_case.sh` ⑦d（`PARTITION_MANIFEST=...`）。

**铁律：只要重跑组装，`STEP2` 和 `STEP2B` 必须同时给全，然后跑 ⑦d。**
