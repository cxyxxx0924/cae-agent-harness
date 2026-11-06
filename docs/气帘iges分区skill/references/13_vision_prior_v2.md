# 13 · 全自动先验 v2：用三图交叉验证驱动重做特征与模型

> 2026-10-31。数据：`E:/work/AI_CAB/分区训练/{igs,hm}` 三套「原始 IGES + 人工分区 .hm」。
> 结论先说：**旧 v1 方案不可泛化（LODO 低于朴素基线），v2 重做后 LODO 平均 0.961。**
> 修订 `2026-10-31 (9)`：用户指出 `cab2.hm` 的 `L5` 那 18 条不属于 TETHER，已并入 `lines0`，
> 金标准按新 `.hm` 重解构后重训（见 §2.1）。

---

## 1. 三套数据的真实身份（先做同源核对，别重复计数）

| 数据集 | 原始文件 | 人工分区文件 | 线数 | 平面 | 与历史数据的关系 |
|---|---|---|---|---|---|
| cab1 | `igs/cab1.igs` | `hm/cab1.hm` | 338 | X-Z（侧视）| **md5 = `5P-BAG.igs`**，即早期"5P-BAG 泛化测试"那张图 |
| cab2 | `igs/cab2.iges` | `hm/cab2.hm` | 828 | X-Y | **md5 = `golden/newcab/source.iges`**，即 NEW_CAB / `Drawing0904ZHEDIETU.iges` |
| cab3 | `igs/cab3.iges` | `hm/cab3.hm` | 911 | X-Y | **md5 = `S31 CAB_AIR BAG ASSY_6P_20240827.iges`** |

**同源核对方法**：`md5sum` 原始 IGES；再 `md5sum` 人工 .hm。
一旦确认 cab2 与 newcab 是同一张图，就必须把它们当**同一张图**对待——否则训练集里出现重复图纸，
交叉验证会泄漏（在同一张图上训、在同一张图上测）。

**处置决定**：v2 训练集只用 `cab1 + cab2 + cab3` 三张图；
`golden/newcab/`（早期 v14 标注）降级为留档，**不进 v2 训练**。
理由是 `cab2.hm` 是同一张图更新、更干净的人工版：它把 25 个小圆圈符号和 18 条斜向碎线（原 `L5`）
一起降级进 `lines0`——那些碎线只有 ~20 mm 长（`len_diag≈0.01`），属于拉带旁的杂线，不是拉带本体。

---

## 2. 金标准解构：组件名 → 四类的映射怎么定

`hm/*.hm` 的曲线分在几个 comp 里，但 comp 名不是 BELT/CAVITY/…，必须自己判定语义。

```bash
# 1) 导出采样点与组件→线映射（同一 line id 空间）
WORKDIR=<工作区> hmbatch -tcl scripts/t02_export_pts.tcl
WORKDIR=<工作区> hmbatch -tcl scripts/t09_dump_comps.tcl
# 2) 特征 + 几何聚合表 + 逐组件高亮渲染
python scripts/featurize2.py <工作区>
python scripts/ga_analyze_comps.py <工作区>        # 打印聚合表 + out/golden_panels.png
# 3) 定好映射后生成金标签
python scripts/ga_build_golden.py <工作区> --map "L1=BELT,L2=CAVITY,L3=SEAM,L4=TETHER,_lines0_Wireframe=lines0"
```

三张图的映射（`cab2` 已按 2026-10-31 用户修正版 `.hm` 更新）：

| 图 | BELT | CAVITY | SEAM | TETHER | lines0 |
|---|---|---|---|---|---|
| cab1（5P-BAG）| `component1`(7) | `component2`(2) | `component3`(56) | `component4`(249) | `_5P-BAG_Wireframe`(24) |
| cab2（NEW_CAB）| `L1`(35) | `L2`(87) | `L3`(43) | `L4`(531) | `_lines0_Wireframe`(132) |
| cab3（6P）| `component1`(67) | `component2`(109) | `component3`(40) | `component4`(586) | `_lines0_Wireframe`(109) |

分类线数：cab1 314 / cab2 **696** / cab3 802；三图合计 1812 条参与训练。

### 2.1 一次真实的标注纠错（保留为案例）

第一版解构时，`L5`（18 条）被我判成"斜向拉带"归入 TETHER——理由是它们构成一条横跨腔体的
斜向板带（373×258 mm，右端带圆弧钩），位置在顶排硬件内侧。

**用户否掉了这个判断**：这 18 条属于 `lines0`（不参与分区的杂线），并更新了 `cab2.hm`。
核对后确认我方推断确实过头：

- 这 18 条每条的 `len_diag` 仅 **0.009~0.014**（≈20~30 mm），`dens_cnt` 15~18、`cl_size` 6~8，
  是**堆在拉带旁边的一簇碎线**，不是一条连续的拉带板；
- 它们只是视觉上首尾相接、看起来像一条斜带。链长 `ch_len=0.217`、`ch_ext=0.154`，
  在 828 条线里根本不是"链"的规模。

修复代价极小，因为**修复发生在标签层、不在特征层**：

```bash
# 1) 从更新后的 .hm 重新导出（几何未变 → line id 空间不变，828 条一一对应）
WORKDIR=<wd> hmbatch -tcl scripts/t02_export_pts.tcl
WORKDIR=<wd> hmbatch -tcl scripts/t09_dump_comps.tcl     # _lines0_Wireframe 114→132，L5 消失
# 2) 只改 --map，去掉 L5=TETHER
python scripts/ga_build_golden.py <wd> --map "L1=BELT,L2=CAVITY,L3=SEAM,L4=TETHER,_lines0_Wireframe=lines0"
# 3) 特征文件 md5 与修复前完全一致（6e5d0abf…），不需要重算；直接重训
python scripts/train_v2.py
```

实测效果：LODO 平均 0.957 → **0.961**，长度加权 0.936 → **0.943**（cab2 自身 0.951→0.964）。
原因是那 18 条碎线此前一直在教模型"这种一簇短线段可以是 TETHER 结构件"，
现在它们退出监督，`TETHER` 的正样本变纯了。

**教训**：金标准的错比特征的错更贵，但**改起来更便宜**——只要分成"标签层/特征层"两层，
改标签不需要重算任何几何量。判 `TETHER` 之前先看 `len_diag` 与 `cl_size`：
**成片但每条都很短 = 符号/杂线，不是结构件。**

**注意**：`ga_analyze_comps.py` 的聚合表里 `midr`（线中点距质心）对**长折线**极不稳定——
cab1 的 `component2` 只有 2 条长折线，中点被拉到一侧，聚合表显示它比 BELT 更"靠外"，
但渲染图一目了然它是内侧轮廓。**聚合表用来排除，渲染图用来定案。**

---

## 3. 第一刀：证明 v1 不可泛化

v1 = `featurize.py`（19 个特征）+ 单棵决策树（269 节点），同图 100% 拟合。
做**留一图交叉验证**（每次留一张图，用其余图训练，测留出图）：

| 留出图 | v1 条数准确率 | "全猜 TETHER"朴素基线 |
|---|---|---|
| cab1 | 0.761 | 0.793 |
| cab2 | 0.706 | 0.769 |
| cab3 | 0.823 | 0.731 |

**两张图不如朴素基线**——即模型没学到可迁移规律，只在背坐标。

特征消融进一步排除"是模型不够强"的可能：
去掉位置特征（`cx_n/cy_n/sin_ang/cos_ang`）、再换 RandomForest，指标仍在 0.65~0.83 徘徊。
说明问题在**特征本身没有跨图判别力**。

三个病根：
1. **绝对位置特征**：`cx_n/cy_n` 直接编码"这条线在图里的哪个方位"，换图即失效。
2. **凸包距离**当"离边界多远"：气帘细长，82% 的线都贴着凸包 → 无判别力
   （这是早期"三条纯几何路线全失败"的同一根因）。
3. **按最大线长归一**：分母被个别超长线支配，导致同一条线在不同图上尺度差异巨大。

---

## 4. v2 特征：三条有物理含义的量

### 4.1 轮廓内向深度 `dep_min / dep_med / dep_max`

```python
# featurize2.build_silhouette()
img   = 所有线按 1200px 长边栅格化
sil   = binary_fill_holes(binary_dilation(img, r))  → binary_erosion(r)   # r≈0.006*N
dt_in = distance_transform_edt(sil)                                      # 内向深度(px)
```

把"布片实体"还原出来，再量每条线离实体边界多远。归一化除以栅格边长（而不是图纸尺寸），
所以对任意单位/任意图幅都可比。

| 类 | cab1 | cab2 | cab3 |
|---|---|---|---|
| BELT `dep_min` | 0.001 | 0.001 | 0.001 |
| CAVITY | 0.001\* | 0.017 | 0.018 |
| SEAM | 0.097 | 0.065 | 0.067 |
| TETHER | 0.003 | 0.005 | 0.005 |

\* cab1 的 CAVITY 只有 2 条长折线，部分段落压在轮廓上，深度被拉低——这是"线粒度与语义粒度不一致"的固有噪声。

### 4.2 切向连续链 `ch_n / ch_len / ch_ext / ch_closed / ch_span / ch_rad / ch_dep`

在每个焊接节点上，把切向夹角最小（`dot > 0.7`）的两条线配对，然后沿配对走链。
链的规模/闭合性/跨度直接量化"这是不是一个环"。

| 类 | `ch_len`（链周长/图幅对角线）| `ch_dep`（链中位深度）|
|---|---|---|
| BELT | 0.04 / 0.32 / 0.30 | 0.001 / 0.001 / 0.001 |
| CAVITY | 1.27 / 1.86 / 2.80 | 0.016 / 0.021 / 0.032 |
| SEAM | 0.51 / 0.42 / 0.80 | 0.106 / 0.069 / 0.073 |
| TETHER | 0.009 / 0.010 / 0.008 | 0.004 / 0.007 / 0.006 |

注意 `ch_len > 1` 意味着这条链的周长比图幅对角线还长——只有"绕整圈的气腔环"会这样。
`ch_len ≈ 0.01` 且 `ch_n = 1` 意味着"一条孤立短线"——硬件符号。

### 4.3 局部密集度 `dens_cnt / cl_size`

- `dens_cnt`：中点邻域半径 `0.02*diag` 内的其它线条数。
- `cl_size`：只把"短线（< 3×中位线长）"互相焊接，得到的符号级连通块规模。

TETHER 是 15~26 / 簇 4~16 条；结构线 0~11 / 簇 0。

### 4.4 图内百分位 `rk_*` + `dep_rel`

同一物理量在不同图上整体水平会漂（例如 cab1 侧视图整体更深）。
把每个量在本图内的百分位也作为特征，等价于"在本图里这条线算深还是浅"，消除图间阈值漂移。

---

## 5. 模型：两阶段森林 + 一条物理兜底规则

**为什么要两阶段**：单模型的混淆矩阵显示，"结构线"与"符号件"在特征空间里犬牙交错，
相互拉扯；而 `symbol vs structure` 这一步本身极易分。

```
A 段（500 树）: symbol(TETHER+lines0) vs structure(BELT/CAVITY/SEAM)
B 段（500 树）: structure 内分 BELT / CAVITY / SEAM
合成:  P(TETHER) = P_A(symbol)
       P(BELT/CAVITY/SEAM) = P_A(structure) × P_B(该类的条件概率)
```

**物理兜底规则**（v2 唯一硬规则）：

```
ch_dep > 0.055 且 ch_len < 0.90  →  SEAM
```

含义：链的中位内向深度明显偏深（在腔体内部）而链又不够长（不是绕整圈的气腔环），
就是气腔内部的缝线环。三图实测：

| 图 | 命中 | 其中 SEAM | 误伤 |
|---|---|---|---|
| cab1 | 57 | 55/56 | 2（全为 lines0）|
| cab2 | 39 | 31/43 | 8（全为 lines0）|
| cab3 | 44 | 40/40 | 4（3 lines0 + 1 CAVITY）|

**零有害误判**——误伤的都是 lines0（本来就是"不分类"的桶）。

**运行期零 sklearn**：`train_v2.py` 把两棵森林导出成 JSON（500+500 棵树，4.9MB，
只在叶节点存概率分布），`auto_partition2.py` 纯 Python 走树。

---

## 6. 结果

### 6.1 留一图交叉验证（唯一诚实口径）

| 留出图 | 条数准确率 | 结构长度加权 | BELT 长度召回 | CAVITY | SEAM | TETHER |
|---|---|---|---|---|---|---|
| cab1 | 0.971 | 0.919 | 0.97 | 1.00 | 0.88 | 0.87 |
| cab2 | 0.964 | 0.944 | 0.96 | 0.87 | 1.00 | 0.97 |
| cab3 | 0.949 | 0.964 | 0.94 | 0.93 | 1.00 | 1.00 |
| **平均** | **0.961** | **0.943** | | | | |

对比 v1 平均 0.763。**同一套特征、同一套代码，只是换了对的物理量。**

### 6.2 端到端（全新工作区从原始 IGES 导入）

三张图分别跑 `run_auto2.sh`，全部 `VERIFY_FAIL=0`：

| 图 | BELT | CAVITY | SEAM | TETHER | lines0 | 与人工金标准 |
|---|---|---|---|---|---|---|
| cab1 | 7 | 3 | 58 | 270 | 0 | 已分类线 **314/314 全对** |
| cab2 | 38 | 89 | 51 | 650 | 0 | **692/696**（4 条差异）|
| cab3 | 69 | 109 | 44 | 689 | 0 | 797/802（5 条差异）|

逐条比对可直接复现（读两份 json，先对齐 id 空间再比）：

```bash
python scripts/eval_vs_golden.py            # 不传参 → 读技能自带 cases/v2_<name>/（冻结的交付快照）
python scripts/eval_vs_golden.py --pred-root <新工作区父目录>/   # 比对新跑的结果
```

三图的交付快照（`partitioned.hm` + 渲染 + `t08` 校验报告 + 分类 json）已随技能冻结在
`cases/v2_cab{1,2,3}/`，见 `cases/README.md`。

差异全部是"金标准 lines0 → 被判成某类"（把本不分类的散碎线也归了类），视觉无害；
cab2 另有 4 条结构互换（`CAVITY→BELT` 1、`TETHER→BELT` 2、`TETHER→CAVITY` 1），都在顶排硬件与
气腔环的接触处，属符号簇与结构线的边界样本。
v2 不产出 lines0 残线，`t08` 的 TOTAL 即全图线数。

---

## 7. 已知边界与残余误差来源（诚实栏）

1. **人工标注本身不自洽的地方，模型无法满足**。
   cab3 的密集硬件符号簇（`cl_size≥20`，361 条）里，人工标了 TETHER 274 / BELT 30 / lines0 49 / CAVITY 8；
   cab2 同一类符号全标 TETHER。这批样本互相矛盾，是当前最大的残余误差来源（BELT 按条数召回被它拉低到 0.57~0.89）。
   但它们都是符号内部的毫米级碎线，**不影响视觉与后续网格化**。
2. **BELT 的"条数召回"与"长度召回"差距大**（0.61 vs 0.94）。被硬件符号切碎的短布带段容易判成 TETHER，
   但主包络永远是对的。若下游关心"每一段短布带"，需要把符号与包络的接触处标得更细。
3. **lines0 不可学**，也不该学。它是人工"选择忽略"的桶，边界随人变。v2 的策略是"全部落类"，
   把散碎线并进 TETHER，视觉上更干净。
4. **三张图之外的构型**（不同气囊结构、不同画法）仍需实证。先跑、先看渲染图，
   差异大就按 §2 交互铁律做幂等 delta，并把新图并入 `golden/` 重训（五步法见 `golden/README.md`）。

---

## 8. 重训与扩展（怎么加第四张图）

```bash
# 1) 新图人工分区得到 <name>.hm
# 2) 建工作区并解构
mkdir -p <wd>/out && cp <name>.hm <wd>/curves.hm
WORKDIR=<wd> hmbatch -tcl scripts/t02_export_pts.tcl
WORKDIR=<wd> hmbatch -tcl scripts/t09_dump_comps.tcl
python scripts/featurize2.py <wd>
python scripts/ga_analyze_comps.py <wd>          # 看 out/golden_panels.png 定映射
python scripts/ga_build_golden.py <wd> --map "..."
# 3) golden/<name>/ 落 7 件：<name>.hm + source.iges + comp_lines.json + comp_agg.json +
#    golden_panels.png + lines_pts.txt + (golden_line_comp.json, features2.json) + source.txt
# 4) 在 train_v2.py 的 DRAWS 里登记一行，重跑
python scripts/train_v2.py                       # 先看 LODO 报告，确认没有图被拖坏
python scripts/rebuild_from_golden.py <name>     # 确认新图能离线复算特征
```

**判据**：新增一张图后，原有各图的 LODO 指标不应明显下降；若下降，说明新图与旧图存在标注口径冲突，
先解决口径（对齐"什么样的线算 SEAM"）再合库。

---

## 9. 踩坑记录（这一轮新踩的）

- **同源核对**：`cab2.iges` 与 `newcab/source.iges` md5 相同。不做核对就会把同一张图当两张图，
  交叉验证直接泄漏（同图训练+同图测试会给出虚高的"泛化"成绩）。
- **键类型**：`featurize.compute_features()` 返回 **int 键**，`features.json` 里是 **str 键**。
  混用会 `KeyError` 或产出大量假的"不一致"（上一轮曾出现 687 个假差异，实际只有 4 个）。
  **跨 ID 空间比对前，先显式验证两侧键空间与键类型。**
- **渲染投影**：cab1 是 X-Z 平面。渲染时若固定取 `(x,y)` 会画成一条水平线；
  必须按 `meta.use_z` 取 `(x,z)`。
- **聚合表会骗人**：`midr` 对长折线不稳定（见 §2 末尾）。定案靠渲染图。
- **"看起来是一条带" ≠ 一条带**：cab2 的 `L5` 首尾相接像斜拉带，实际是 18 条 20~30 mm 的碎线。
  判结构件先看 `len_diag`/`cl_size`，再看渲染；见 §2.1。
- **标签层与特征层必须分开**：改标签只要重跑 `ga_build_golden.py`（`--map` 一行），
  特征文件 md5 不变、不用重算几何；这正是分层带来的容错。
- **Tcl 的 `[`**：`puts "$name\": ["` 里的 `[` 会触发命令替换，必须写 `\[`。
