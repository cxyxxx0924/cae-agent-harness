# 16 · 通用泛化流程（case.json 驱动，换案例不改脚本）

> 目标：**换一个气帘/分区模型，只写一份 `case.json`，脚本一行不动。**
> 本文是这条链路的权威说明：能泛到哪、泛不了的地方为什么、怎么验证泛化是"真的等价"而不是"看起来差不多"。

---

## 0. 一句话结论

| 阶段 | 泛化状态 | 依据 |
|---|---|---|
| ① 线采样 | ✅ 完全泛化 | collector 列表从 `case.json` 生成，不写死 comp id |
| ② 线→闭环 | ✅ 完全泛化 | 端点聚类 + 平滑走链，环数量/每条环的线集合全部自动得到 |
| ③ 裁切拓扑 | ✅ 完全泛化 | `ringdefs` 由 `loops.json` 灌入，**缝线几条、每条几条线都不写死** |
| ④ 分面建网格 | ✅ 完全泛化 | 缝线/布带/气腔顺序固定，`blmesh_2d2` 参数来自 `case.json` |
| ⑤ 拉带 / 侧面拉带 | ⚠️ **半泛化** | 拉带是 CAD 里独立围出的结构件，形状差异大；仍需一张案例级轮廓 JSON |
| ⑥ 分层组装 + 捏合 | ✅ 基本泛化 | 层号/PID/Z 偏移/路径全走环境变量；拉带锚固规则已按"性质"而非"坐标"写 |
| ⑦ 门禁 | ✅ 完全泛化 | `qa_kfile_strict` / `auto_gate` / `mesh_quality_gate` 均与分区无关 |

**验证强度**：cab2 上用手写 `ringdefs` 的旧 Tcl 和自动生成的 Tcl 各跑一遍 HyperMesh 2026，
导出文件 **MD5 完全相同**（`cab2_step1_gen.txt` == `cab2_step1_blmix.txt`）。
再把整条 `run_case.sh` 端到端跑一遍，产出的 deck 与交付件 `cab2_curtain_airbag_v3.k`
**MD5 也完全相同**（`601437676741ace6d1db699b6fbb2b52`）。
这不是"近似等价"，是逐字节等价：**一份 20 行的 case.json 就能复现整份交付网格。**

---

## 1. 为什么要泛化这一环：硬编码到底在哪里

旧 `cab2_step1_bl.tcl` 里只有 4 处是案例特有的：

```tcl
set ringdefs [list \
  [list seam0 {17 84 31 42 19 27 103 102 53 54 85 83}] \
  [list seam1 {28 113 60 106 105 38 107 39 112}] \
  [list seam2 {18 109 26 110 20 111 59 108 104}] \
  [list seam3 {13 824 33 41 34 75 74 14 76 73 57 58 823}] ]   ;# ← ① 缝线环的线号
*createmark lines 1 "by collector" 3    ;# ← ② 气腔轮廓在哪个 comp
*createmark lines 1 "by collector" 2    ;# ← ③ 布带轮廓在哪个 comp
*readfile "$P/input/cab2.hm"            ;# ← ④ 模型文件
```

①②③ 都是**几何事实**，本来就能算出来，人工抄写只是因为没有把前一步接上。
④ 是纯配置。

> 注意：`ringdefs` 里那 4 组线号**恰好等于** `chain_loops.py` 在 `L3` 上的自动输出
> （见 `out/loops_gen.json`：4 个闭环，lids 逐一对上）。
> 也就是说人工抄的这一段，本来就是机器算出来的东西——这就是泛化的锚点。

---

## 2. 新链路：三层职责

```
case.json          ← 唯一的案例知识（cid/tag/pid/Z/尺寸/门限）
    │
    ├─ stage1_survey/export_lines_pts.tcl   线 → 点云文本（CID 从 case.json 来）
    │      ↓ out/lines_pts.txt
    ├─ stage2_partition/chain_loops.py      点云 → 闭环（纯几何，无案例知识）
    │      ↓ out/loops.json
    ├─ drivers/gen_step1_tcl.py             loops + case → step1_gen.tcl
    │      ↓ out/step1_gen.tcl
    ├─ hmbatch                              建面/裁切/分面建网格（blmesh）
    │      ↓ out/<case>_step1_bl.txt
    ├─ stage4_assemble/assemble_cab2.py     分层组装 + 拉带捏合 → deck
    │      ↓ *.k
    └─ gate/                                三道门禁
```

**设计原则：案例知识只允许出现在 `case.json` 里。**
脚本里出现任何一个具体数字（线号、comp id、坐标、文件名），都算 bug。

---

## 3. case.json 契约

```json
{
  "case": "cab2",
  "model": "cab2.hm",
  "plane": "xy",
  "thickness_axis": "z",
  "loop_tol": 0.8,

  "layers": [
    {"role": "belt",   "cid": 2, "tag": "L1", "pid": 2, "z": [0.0]},
    {"role": "cavity", "cid": 3, "tag": "L2", "pid": 3, "z": [-0.5, 0.5]},
    {"role": "seam",   "cid": 4, "tag": "L3", "pid": 4, "z": [0.0]},
    {"role": "tether", "cid": 5, "tag": "L4", "pid": 5, "z": [-1.0]}
  ],

  "parts": ["belt", "cavity", "seam", "tether", "side"],

  "seam":  {"min_area": 200, "sort": "area_desc", "max_count": 40},
  "mesh":  {"size": 5.0, "seam_size": 5.0, "bl_thick": 4.0,
            "bl_layer": 1, "bl_etype": "mixed"},
  "quality_gate": {"min_angle_quad": 30.0, "tria_ratio_max": 0.08},

  "assemble": {
    "anchored_tethers": true,
    "tab_tol": 0.35, "snap_inside_tol": 3.0, "weak_anchor_min": 1,
    "edge_band": 4.0,
    "tabs_polys": "out/tether_full.json",
    "step2": "tabs_triple_export.txt",
    "step2b": "cab2_step2b_side2.txt"
  },

  "gates": {
    "gate_case": "cases/cab2/gate_case_v8.json",
    "partition_manifest": "out/ref_manifest_v3.json"
  }
}
```

| 字段 | 作用 | 怎么填 |
|---|---|---|
| `cid` | HyperMesh collector id | `survey_comps.tcl` 的输出里抄；**不是** comp 顺序号 |
| `tag` | `lines_pts.txt` 里的前缀 | 与 `export_lines_pts.tcl` 的 `COMPS` 必须一致 |
| `pid` | 导出 K 的 PID | 与下游 deck/材料对应 |
| `z` | 该层厚度方向偏移（列表=双层） | 气腔 `[-0.5, 0.5]`、布带/缝线 `[0.0]`、拉带 `[-1.0]` |
| `seam.min_area` | 低于此面积的闭环不算缝线 | 滤掉草图圆角/小圈；cab2 取 200 |
| `seam.max_count` | 最多取几个缝线环 | 防 CAD 脏线被误判；不填=不限制 |
| `mesh.bl_*` | 边界层厚度/层数/单元类型 | 见 `references/14`、`15`；`bl_etype` 用 `mixed` |

`role` 名字是固定的四个：`belt` / `cavity` / `seam` / `tether`。
没有拉带的产品，删掉 `tether` 条目 + 跳过 ⑤ 即可。

### 3.1 `parts` / `assemble` / `gates`（2026-11-01 新增，防"整块丢"）

| 字段 | 作用 | 为什么必须有 |
|---|---|---|
| `parts` | 必需网格部件清单，注入 `REQUIRE_PARTS` | **cab2 曾整块丢侧拉带，五项门禁全 PASS**（`04_pitfalls.md` P48）。缺件现在直接 `SystemExit` |
| `assemble.anchored_tethers` | 是否跑 ⑥b 三刀切锚固 | 参数化后不再靠命令行记环境变量 |
| `assemble.tab_tol / snap_inside_tol / weak_anchor_min` | 吸附与弱锚判据 | 定版 0.35 / 3.0 / **1**（默认 8 会误伤凸台，P53） |
| `assemble.step2 / step2b` | 拉带 txt 文件名（**只写文件名**） | 带 `out/` 前缀会被拼成 `out/out/`（P54） |
| `gates.gate_case` | auto_gate 配置 | 可用相对 WORKDIR 或技能根目录 |
| `gates.partition_manifest` | 分区覆盖基线 | **不写 = 没有防丢块门禁** |

> 完整字段表与填写方法见 `cases/README.md`；接新案例的端到端步骤见
> `references/00_RUNBOOK_接新气帘.md`。

---

## 4. chain_loops.py：环是怎么算出来的

1. **端点聚类**：所有线的起点/终点按 `--tol`（默认 0.8mm）空间哈希合并成"节点"。
   CAD 里"看起来接上"的两条线端点常常差 0.01~0.5mm，不聚类就一条环都走不通。
2. **建图**：节点=端点 cluster，边=线。度≠2 的节点是分叉或断头。
3. **平滑走链**：在每个节点从候选线里选**方向点积最大**的那条（相当于"走直线不拐弯"）。
   回到起点即闭环。这比"就近连"稳，因为缝线拐角处往往有多条线交汇。
4. **闭环排序**：按面积降序。面积用鞋带公式，平面自动识别（点数波动最小的轴 = 厚度轴）。

输出 `loops.json` 结构：

```json
{ "L3": { "loops": [{"lids":[17,84,...], "area":7472.7, "perim":2142.9,
                     "bbox":[117.4,989.4,-52.5,237.4], "npts":289}, ...],
          "opens": [{"lids":[...], "L":3097.3, "gap":1985.4}] },
  "__meta__": {"tol":0.8, "plane":"xy", "thin_axis":"z"} }
```

**`opens` 是诊断资产，不是垃圾。** 开放链 = CAD 本身没闭合的地方（缺口/未搭接）。
cab2 的 `L1`（布带）全是开链、最长一条缺口 1985mm —— 说明布带外轮廓在 CAD 里本来就不闭合，
HyperMesh 的 `*surfacesplineonlinesloop` 会自动桥接缺口。**如果某天成环突然多出一个假环，
先看 `opens` 的 gap，大概率是容差把两条不相干的线粘上了。**

---

## 5. gen_step1_tcl.py：模板 + 填充

模板 `scripts/stage3_mesh/blmesh2d/step1_template.tcl` 只有 5 个占位符：

| 占位符 | 来源 |
|---|---|
| `@@CASENAME@@` | `case.json` → `case` |
| `@@MODEL@@` | `case.json` → `model` |
| `@@CID_CAV@@` | `layers[cavity].cid` |
| `@@CID_BELT@@` | `layers[belt].cid` |
| `@@RINGDEFS@@` | `loops.json` 里 `seam.tag` 的闭环 → Tcl 字面量 |

生成的 `ringdefs` 片段：

```tcl
set ringdefs [list \
  [list seam0 {17 84 31 42 19 27 103 102 53 54 85 83}] \
  [list seam1 {...}] \
  [list seam2 {...}] \
  [list seam3 {...}] ]
```

> **坑**：外层 `[list ...]` 不能省。省了会退化成 `set ringdefs [list a] [list b] ...`，
> Tcl 报 `wrong # args`。生成器里 `tcl_ringdefs()` 已处理，手工改模板时注意。

生成器还会做**残留占位符检查**（`re.findall(r"@@[A-Z_]+@@")`），漏填直接退出而不是让 hmbatch 静默出错。

---

## 6. 分面建网格的顺序铁律（泛化后依然成立）

```
① 缝线面（小面先做）  try_mesh seam_i  ← 先把界面节点落地
② 布带面             try_mesh belt
③ 气腔 blmesh_2d2     ← 必须最后，才能复用①②已生成的边界节点
```

原因见 `references/14 §4.1`：`SCAV`/`SBELT` 由同一张面 `*surfacemarksplitwithlines` 裁出、
共享拓扑边；邻居先划、blmesh 最后，**边界节点直接复用** →
`cav∩belt=1615` 一个不丢、坐标合并计数 0。
反过来先 blmesh 再划邻居，就会得到两套节点 ID，只能靠组装层按坐标合并兜底（`MERGE_TOL`）。

必须前置的两条命令（否则**静默 0 单元**，不报错）：

```tcl
*elementorder 1
*setedgedensitylinkwithaspectratio -1
```

---

## 7. 组装层：泛化靠"性质"不靠"坐标"

`assemble_cab2.py` 里容易被写死的是拉带锚固，现在的两条规则都是**性质判定**：

1. **锚固点选取**：先取拉带节点里"落在布带外边界一定带宽内"的那一轮；
   若某块拉带这一轮取到的点数 < `WEAK_ANCHOR_MIN`（默认 8），才启用布带**内部**锚固排。
   —— 不能无条件开内部锚固，否则凸台会被二次焊接（实测最小角 p1 40.8°→28.4°）。
2. **候选池排除界面节点**：`belt_n ∩ cav_n` 的节点不能当锚点。
   挂上去会让拉带与气腔共节点，违反参考模型的 `PID4∩PID7=0` 性质（实测产生 `tether∩cav=30`）。

参考模型的三条性质（`references/15 §3`）是验收标准：
`tether∩belt > 0`、`tether∩seam = 0`、`tether∩cav = 0`。

---

## 8. 三道门禁与退出码

| 门禁 | 判什么 | 退出码 |
|---|---|---|
| `gate/qa_kfile_strict.py` | 拓扑卫生：重复节点/重复单元/孤儿/缺引用/单位制/ASCII | 0/1 |
| `gate/auto_gate/run_gate.py --case <gate_case.json>` | 业务口径：Y 分层 / 环面积周长 / 环几何贴合 / 拉带连接 | 0/1/2 |
| `gate/mesh_quality_gate.py` | 碰撞网格形状：最小角/aspect/雅可比/翘曲/三角占比/尺寸梯度 | 0 PASS / 1 WARN / 2 FAIL |

`mesh_quality_gate.py` 是**唯一可以独立于本项目使用**的门禁：给任何壳网格 K 和一组判据就能打分，
还输出不合格单元的聚类中心坐标，直接拿去定位修复。

---

## 9. 换案例操作清单（新模型接入 5 步）

```bash
# 0) 准备：$WORK/input/<model>.hm（stage0 已导入，线在 4~5 个 collector 里）
cp -r cases/cab2 cases/newcab          # 5 改成新名字
vi cases/newcab/case.json              # 改 case/model/所有 cid/pid/z

# 1) 线采样（确认 COMPS 对得上：每个 collector 都有线、数量合理）
COMPS="$(python scripts/drivers/case_env.py --case cases/newcab/case.json --comps)"
grep -c . out/lines_pts.txt

# 2) 成环 —— 这一步会立刻暴露 CAD 干不干净
python scripts/stage2_partition/chain_loops.py out/lines_pts.txt --out out/loops.json
#    看 seam 那一栏：闭环数 = 缝线条数；有 opens 且 gap 很大 = CAD 缺口

# 3) 生成 Tcl 并干跑检查（不写文件）
python scripts/drivers/gen_step1_tcl.py --case cases/newcab/case.json \
       --loops out/loops.json --out out/step1_gen.tcl --dry-run

# 4) 全链
bash scripts/drivers/run_case.sh --case cases/newcab/case.json --work $WORK
```

**第一次接新案例，`--dry-run` 那步一定要看**：缝线条数、每条缝线的面积、面积合计。
面积合计与"气腔总面积 × 该产品缝线覆盖率"对不上，说明 `min_area` 或 `loop_tol` 要调。

---

## 10. 泛化边界（诚实清单）

| 做不到全自动的东西 | 为什么 | 现在的做法 |
|---|---|---|
| **拉带/侧面拉带的轮廓** | 拉带在 CAD 里是独立围出的结构件，形状随产品变化极大（凸台/长条/钩形/哑铃），且"哪几条线围成一块拉带"本质是**语义判断** | 案例级轮廓 JSON（如 `side_tether.json`）+ `gen_side_tab*.py`；用户口径：几何归机器、语义归人 |
| **充气口封不封口** | 图纸固有没有闭合（cab2 颈部 X 616–881 是开口），封不封是设计决定不是几何事实 | 门禁按 `bnd_tol=15mm` 放宽并报 WARN，等设计确认 |
| **缝线环的取舍**（哪几个闭环是真缝线） | CAD 里常有草图圆角/小圈，`min_area` 能过滤大部分，但边缘情况要看图 | `seam.min_area` + `max_count` + `--dry-run` 人工确认；必要时 `seam.manual` 直接给 lids |
| **bl 边界层厚度** | 与产品布厚/折叠半径有关，不是纯几何 | `case.json` 的 `mesh.bl_thick`；cab2 取 4.0mm（≈参考模型实测带宽） |

---

## 11. 本次验证记录（cab2）

| 项 | 手写版 `cab2_step1_bl.tcl` | 自动生成版 `step1_gen.tcl` |
|---|---|---|
| 缝线面 | 4 个，线号手抄 | 4 个，线号来自 `loops.json` |
| 缝线网格 | 294 / 212 / 194 / 179 | **完全相同** |
| 布带网格 | 5315（quad 5089 / tria 226） | **完全相同** |
| 气腔 blmesh | 37411（quad 36337 / tria 1074） | **完全相同** |
| 裁切边号 | 835 / 853 / 861 / 870 / 880 | **完全相同** |
| 导出文件 MD5 | `3668a99e...` | `3668a99e...` |

结论：**②③④ 三个阶段的泛化是逐字节等价的，不是"差不多"。**
新增的自动化没有引入任何网格质量变化，风险为零。

**端到端复核**（`run_case.sh` 全链，1 次 3m21s）：

| 阶段 | 结果 |
|---|---|
| ② 成环 | L3 → 4 闭环（7492.7/4802.7/4323.8/3772.0），与手抄一致 |
| ③ 生成 | `step1_gen.tcl` 9376 bytes，占位符全填 |
| ④ hmbatch | seam 294/212/194/179、belt 5315、cav 37411，全对 |
| ⑥ 组装 | `cav∩belt=1615  seam∩cav=981  tether∩belt=94  tether∩cav=0` |
| 交付 deck | MD5 `6014376…` == `cab2_curtain_airbag_v3.k` |

> 踩过的坑：`run_case.sh` 把 `STEP1=out/xxx.txt` 传给 `assemble_cab2.py` 时，
> 后者又拼了一次 `P + "out/"`，变成 `out/out/xxx.txt`。
> 已改为三级候选路径探测（原样 → 相对 WORKDIR → 相对 out/）。

---

相关文档：`references/14`（blmesh 前置方法）、`references/15`（质量口径 + 拉带连接）、
`references/04`（坑位全表）、`cases/README.md`（案例配置写法）。
