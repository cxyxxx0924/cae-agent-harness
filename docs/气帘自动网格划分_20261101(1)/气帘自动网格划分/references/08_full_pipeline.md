# 08 · 全链路流水线：IGS → 几何清理 → 分区 → 网格完成（一键交付）

> 本文是 cab1 气帘项目**已跑通并交付**的完整链路（2026-10-20/21 实测基线）。
> 从客户 IGS 文件开始，到过门禁的 LS-DYNA deck 结束，共 7 个阶段。
> 每阶段给出：**命令 → 输入/输出 → 预期数字（cab1 基线）→ 失败分支**。
>
> 一键复现：`bash scripts/run_pipeline.sh`（`SKIP_IMPORT=1` 跳过已有 .hm 的导入）。
> 所有脚本在 `scripts/`，全部认 **`WORKDIR` 环境变量**（Python `os.environ` /
> Tcl `::env(WORKDIR)`，缺省 cab1）——换项目 `P=/path/to/proj bash scripts/run_pipeline.sh`
> 即可，`run_pipeline.sh` 负责导出；也可照旧改各脚本头部 `set P` / `P =` 那一行。

---

## 0. 链路总览

```
cab_hm1.iges ──① 导入──▶ cab1.hm ──② 调查/清理──▶ 组件清单 + 线点云 + 标准底图
                                                    │
                            ┌───────────────────────┘
                            ▼
                     ③ 分区识别 (Python 几何聚类) ──▶ tabs_polys.json (9 区域)
                            │
              ┌─────────────┴──────────────┐
              ▼                            ▼
   ④ 裁切拓扑三面网格              ⑤ 拉带网格 (逐片 spline+automesh)
   build_step1_2026.tcl            gen_tabs_tcl.py → build_tabs_2026.tcl
   → step1_mesh_2026.txt           → tabs_mesh_2026.txt
   → assemble_step1_2026.py        → assemble_tabs.py (Y=-1 分层 + 捏合 PID2)
   → cab1_step1_2026_pre_tabs.k         │
              │                         ▼
              │               ⑥ 充气口捏合 (assemble_port.py)
              └────────────┬────────────┘
                           ▼
              ⑦ 门禁 + 渲染 → cab1_step1_2026.k 【交付】
                 qa_kfile_strict.py / diag_long_edges.py
                 diag_cavity_port.py / diag_strap_ends.py
```

**阶段间唯一中间文件**：`out/tabs_lines_pts.txt`（线点云）、`out/tabs_polys.json`（分区）、
`out/step1_mesh_2026.txt`（三面网格）、`out/tabs_mesh_2026.txt`（拉带网格）。
**K 文件是链上唯一的"真"模型载体**——任何引用 K 节点/单元的步骤，id+坐标必须从 K 本身解析（P29）。

---

## ① IGS → .hm（导入）

```bash
HMB="D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe"   # 或 2020 版
"$HMB" -tcl scripts/import_igs_2026.tcl -noconcurrent
```

| | |
|---|---|
| 输入 | `input/cab_hm1.iges`（CATIA 导出，338 条线） |
| 输出 | `input/cab1.hm`（二进制 HM 库）+ `out/import_igs_report.txt` |
| 脚本 | `import_igs_2026.tcl` |

要点（2026-10-20 实测）：
- `*geomimport "iges_altair" <path>` 是批处理导入的正确命令；`hm_importfile` 在 2026 已不存在。
- **批处理导入把全部线放进一个 comp**（名字 = IGES 根组名 "5P-BAG"），不按 IGES 组自动建 component。
  项目里的 cab1.hm 是 GUI 导入时整理好的 5 comp 结构（保留即可，后续全部走 `*readfile`）。
- 存库：`*writefile <path> 1`（二进制）。**K 文件不能 `*readfile`**（按 HM 库解析，必失败，P19）。
- 换 CAD 格式只改 translator：`step_ct` / `iges_altair` / `parasolid_parasolid`。

> 已持有干净 .hm 的项目跳过本阶段。GUI/MCP 通道导入用 `mcp__hyperworks__import_live_cad`
> （translator 同名），导入后手动存 .hm 再进批处理链。

---

## ② 几何调查与自动清理（分区依据）

**原则**（用户协作约定，P13）：几何调查的产出是**固定坐标系的标准底图**，
语义判断归人（用户在图上指认），几何计算归机器。不做"自动识别猜语义"。

```bash
# 2a. 组件清单 + spline 面积实证 → out/survey_comps.txt
"$HMB" -tcl scripts/survey_comps.tcl -noconcurrent

# 2b. 各 component 线采样点云 → out/lines_pts.txt (供渲染/环几何基准)
"$HMB" -tcl scripts/export_lines_pts.tcl -noconcurrent

# 2c. 拉带(component4)线采样点云 → out/tabs_lines_pts.txt
"$HMB" -tcl scripts/export_tabs.tcl -noconcurrent

# 2d. 渲染标准底图 (matplotlib, XZ 平面, 向右+X 向上+Z)
$PY scripts/render_lines.py            # lines_pts.txt → v_lines_*.png
```

**cab1 实证结果**（`survey_comps.tcl`，PID = component id，以面积/几何为准，P28）：

| comp id | 名称 | 线数 | spline 面积 | 判定 |
|---|---|---|---|---|
| 1 | `_5P-BAG_Wireframe` | 24 | 9,031 | 原始线框，忽略 |
| 2 | `component1` | 7 | **1,154,213** | 布带外轮廓 → PID2 |
| 3 | `component2` | 2 (composite) | **955,347** | 气腔 → PID3 |
| 4 | `component3` | 56 | **4,627** | 缝线 5 区 → PID4 |
| 5 | `component4` | 249 | **128,062** | 拉带相关 → PID5（automesh 直接失败，需简化） |

**自动清理动作**（此阶段在 Python/Tcl 侧完成，不动网格）：
1. 线点云去重 / 往返退化线检测（同一对端点只留一条）；
2. 端点焊接（容差 ~2.6mm）→ 断链修复；
3. 环缺口补桥（人工在底图上确认后写死补桥线段，见 03 §3）；
4. 装饰线与结构线分离（锯齿/缝线/挂刺是表面装饰，绝不上轮廓，P31）。

**失败分支**：
- `readfile` 报 `not a HyperMesh database` → 你在拿 K 文件当 .hm 读（P19）。
- spline 面积 0 / 失败 → 该 comp 是散线，先补链成环（P9）。
- 面积与客户图样对不上 → 别信 comp 名字/颜色，以面积+底图目视为准（P28）。

---

## ③ 分区识别（tabs_extract.py）

```bash
$PY scripts/tabs_extract.py     # tabs_lines_pts.txt → tabs_polys.json
```

输入 249 条拉带线，输出 **9 个区域多边形**（cab1）：

| 区域 | 类型 | 中心 | 面积 | 说明 |
|---|---|---|---|---|
| R0–R6 | 凸台 ×7 | x 1678–2987 | ~3.7k | 每区分 **up/dn 两片**（Y=-1 分层），共享膝弦边 |
| R7 | CURVE | (1044, 1225) | 5,632 | 左弯条，CAD 天然竖直右端边 |
| R8 | HORIZ | (928, 952) | 2,270 | 左横条，末端斜切需**补直成竖直边** |

算法链：聚类成区域 → 端点焊接 → polygonize 提环 → boss_split（肩→膝分割，up=帽+柱+穹顶，
dn=矩形）→ 内环剔除 → simplify（**HORIZ 单独 2.0，其余 0.4**，P32）。

**铁律**：
- HORIZ 外环 = 主轮廓线（最长线闭合成环 = 干净带体）∪ 装饰线开运算包络（扇形接口）。
  锯齿/缝线/挂刺不上轮廓（P31）；开运算必须 **±同值净零**。
- 凸台上片穹顶要有"实质穹顶"检查（面积 ≥1.4× 柱截面 且 顶超柱顶），否则回退凸包（BOSS3 个案）。
- 跑完**必须目视复核** `v_tabs_regions.png`：聚类偶发重复/漏区。

**失败分支**：区域数 ≠ 9 → 聚类参数（距离阈值/最小线数）或源线质量问题，回 ② 查底图。

---

## ④ 裁切拓扑三面网格（step1：缝面 / 气腔 / 布带）

```bash
"$HMB" -tcl scripts/build_step1_2026.tcl -noconcurrent   # → out/step1_mesh_2026.txt
$PY scripts/assemble_step1_2026.py                        # → out/cab1_step1_2026_pre_tabs.k
$PY scripts/verify_step1_2026.py                          # 共节点/自由边/短边/折叠
```

方法：**一套面切出所有分区**（03 文档核心），缝面用**洞内面**（P12），界面共节点由 HM 拓扑保证：

| 步骤 | 命令 | cab1 实测 |
|---|---|---|
| 5 缝线环 spline 建面 | `*surfacesplineonlinesloop` | surf 1–5，4,627~9,848 mm² |
| 取缝面边线（绕开 composite） | `*linefromsurfedgecomp` | 普通线 |
| 外轮廓 spline 建面 | 同上 | BLUE 全域 1,154,050 mm² |
| BLUE 裁 L3 线 | `*surfacemarksplitwithlines` | CAV 956,944 + BELT 197,662 |
| CAV 裁 5 缝面边线 | 同上 ×5 | CAV 929,103 + 洞内面 ×5 |
| automesh 先小后大 | seam → cav → belt，size 5.0 | quad 主导，r1/r2 全 0/1 |
| equivalence2 0.05 | 拓扑已共节点 | 节点数 44502→44502（零变化） |

**cab1 基线**（`step1_2026_report.txt`）：网格导出 seam 1,087 + cav 35,604 + belt 8,169 = **44,860 单元**；
assemble 后 `cab1_step1_2026_pre_tabs.k` = **111,927 节点 / 80,464 单元**
（PID2 布带 8,169 Y0 + PID3 气腔 71,208 双 ply Y±0.5 + PID4 缝线 1,087 Y0），交界共节点 100%。

**Y 分层约定**（用户 2026-10-18 规范）：布带 PID2 = Y0 单层；气腔 PID3 = Y±0.5 双层；
缝线 PID4 = Y0 单层；交界捏合共节点在 Y0。

**失败分支**：共节点 0 → 缝面用了 spline 面而非洞内面（P12）；裁切只出碎片 → composite 线（P10）；
automesh 报 `Internal mesh error` 且元素 0 → 漏了 `*elementorder 1` +
`*setedgedensitylinkwithaspectratio -1`（P34，两个 build Tcl 都已带）。

---

## ⑤ 拉带网格 + 与布带节点捏合（PID5）

```bash
$PY scripts/gen_tabs_tcl.py          # tabs_polys.json → build_tabs_2026.tcl
"$HMB" -tcl scripts/build_tabs_2026.tcl -noconcurrent    # → out/tabs_mesh_2026.txt
cp out/cab1_step1_2026_pre_tabs.k out/cab1_step1_2026.k   # 从干净基底重来
$PY scripts/assemble_tabs.py         # 合并进 cab1_step1_2026.k
```

| 项 | 规则 | 依据 |
|---|---|---|
| 建面 | 每片 spline + **逐面 automesh**（分组版批处理只网格化首个面，P26） | — |
| 凸台上下片 | 同组一次 automesh，**共享膝弦边**共节点（同线确定性离散 + 组装坐标 dedup 双保险，P25） | — |
| Y 分层 | 拉带体 Y=-1；与布带连接处爬坡到 Y0 | 用户分层约定 |
| 合并目标 | **只并到单层布带 PID2**，绝不并气腔/缝线 | 参考模型 PID8∩PID4=0（P21/P22） |
| 匹配算法 | **全局 1-to-1 贪心**（距离升序，每布带节点至多复用一次） | P24，零退化丢单元 |
| 去重 | 节点集相同的单元剔除（零厚度重合伪单元） | P23，与 QA 同口径 |
| **凸台连接** | 顶帽边：该片**最高连接 Z 附近 8mm（EDGE_BAND）**的水平一条线 | 用户确认无问题 |
| **左拉带连接** | **末端竖边**：该片**最右端 3mm（END_BAND）**的竖直一条线，**垂直布带长度方向** | 用户 2026-10-21 定 + 参考 R8 实证（P30） |

**cab1 基线**：PID5 = **3,279 单元**（7 凸台上下 14 片 2,953 + tabc7 232 + tabh8 94，合并后零丢弃），
**148 唯一共节点**到布带（PID2∩PID5），9 区域全连；
tabc7 末端竖边 **6 共节点**（x1114.5，z1191.7–1216.6），tabh8 末端竖边 **3 共节点**
（x1104.4，z946.5/951.7/956.8）——与参考模型 R8（末端竖边 3 共节点，ramp Y−0.5→0）拓扑一致。

**失败分支**：
- 连接区出现 >20mm 自由边 → 导出 txt 的 nid 被当成 K 的 gid 用了（P29 飞丝），目标 id 必须读 K 本身。
- 左拉带连接节点散乱 → 该片外环没有干净竖直末端边（锯齿/斜切倒角），回 ③ 修多边形（P31）。
- 拉带只 mesh 出第一个面 → grouped automesh 失效（P26）。

---

## ⑥ 充气口捏合（assemble_port.py）

```bash
$PY scripts/assemble_port.py     # 就地改写 cab1_step1_2026.k (幂等)
$PY scripts/diag_cavity_port.py  # 验证: PID3 端口自由边必须 0
```

气腔上下两层在充气口处上下唇贴合：12 对 XZ 重合的唇边节点捏合到中面 Y=0，删 24 个孤儿节点。
端口自由边 26 → **0**。幂等（无自由边就跳过）。

---

## ⑦ 门禁 + 渲染（不过不许交付）

```bash
# 结构门禁
$PY scripts/qa_kfile_strict.py out/cab1_step1_2026.k     # 必须 PASS (exit 0)
# 空间合理性门禁 (QA 查拓扑合法性, 不查空间 -> 必须单独过)
$PY scripts/diag_long_edges.py                            # XZ>20mm / 3D>30mm 必须 0
# 专项
$PY scripts/diag_cavity_port.py                           # 端口自由边 0
$PY scripts/diag_strap_ends.py                            # 左右拉带末端竖线共节点
# 渲染交付验证图
$PY scripts/render_step1_2026.py     # 三面网格三图
$PY scripts/render_left_conn.py      # 左拉带连接 (belt灰/strap蓝绿/共节点红)
$PY scripts/render_before_after.py   # 修复前后对比
```

> **⑦b 逐环几何匹配 + 拉带连接检查（2026-10-22 NEW_CAB 沉淀，建议加为几何门禁）**
> 拓扑 QA 只查 eid 唯一/无退化/无自由边，**查不出"几何是否和 CAD 曲线一致"**
> （NEW_CAB 出现过凸台矩形环漏编→穹顶悬空、整环面积翻倍而 QA 全 PASS）。交付前再加两道：

```bash
# 由分区结果 + 足印清单生成逐环定义
$PY scripts/gen_ring_spec.py --classify out/classify_final.json \
  --footprints assets/ringdef_newcab.json --out out/ring_spec.json
# ① 逐环几何匹配: IGES 线段几何 vs 网格几何 (位置/面积/边界)
$PY scripts/geom_match_check.py --lines out/lines_pts.txt --mesh out/cab1_step1_2026.k \
  --rings out/ring_spec.json --map xy --atol 0.15 --bnd 8 --sel-tol 8 --render out/v_geom_match.png
# ② 拉带连接质量: 接对层/不整面重叠/无退化
$PY scripts/tether_conn_check.py --mesh out/cab1_step1_2026.k --map xy \
  --rings out/ring_spec.json --render out/v_tether_conn.png
```

| 门禁 | 判据 | NEW_CAB 实测 |
|---|---|---|
| `geom_match_check.py` | 逐环：凸包比≈1（环面免检）/ 凸包质心偏≈0 / CAD→mesh 覆盖 < bnd_tol（cavity 放宽 15） | 13 环全 PASS |
| `tether_conn_check.py` | 每组分接布带 PID2、误连气腔/缝线=0、周长占比<50%、无退化/伪单元 | 16 组分全 PASS |

完整方法论/参数/副作用见 **`references/10_geom_match_and_tether_check.md`**，坑位见 `04_pitfalls.md` P39–P47。


**cab1 最终基线**（2026-10-21，全部门禁通过）：

| 门禁 | 结果 |
|---|---|
| `qa_kfile_strict.py` | **PASS**（83,743 单元 / 115,367 节点 / pid=[2,3,4,5]，0 致命 0 警告） |
| 长边 | XZ>20mm / 3D>30mm = **0** |
| 充气口自由边 | **0** |
| 左拉带连接 | tabc7 竖线 6 点 / tabh8 竖线 3 点，垂直布带长度方向 |
| R8 短边(<3mm) | **0**（原 97；公司规范 2.2 硬条款） |
| 退化丢单元 | 0（1-to-1 贪心） |

**遗留既有项**（与连接修复无关，登记在短边专项）：凸台区 19 条、布带 22 条、气腔 20 条 <3mm 短边。
**修复铁律**：不准乱删（P18），只删真退化/完全重复；短边用"微调节点位置"或区域重剖修。

---

## 8. K 文件书写格式（写完必检）

历史事故：自创 10 字符定宽把 4 位数坐标+6 位小数切错 → 节点全塌 z=0 → HM 里满图乱线。

- 只用两种规范格式：**逗号自由格式（首选，零歧义+全精度）** 或严格 10 字符定宽；
- 4 位数坐标 + 6 位以上小数**放不进** 10 字符定宽 → 必须自由格式；
- **QA 验证器必须比真实读取器更严**，不能与写入器共享字段假设（上次翻车直接原因）；
- 工具：`fix_kfile_format2.py`（自由格式重写 + 回读精确比对 1e-12）、`qa_full2.py`（回读全量比对）。

---

## 9. 换项目 Checklist

0. **路径**：`P=/path/to/newproj bash scripts/run_pipeline.sh`（WORKDIR 自动导出）；
   或逐个改脚本头部 `P` / `P =`。**必须全英文**，中文路径 hmbatch `-tcl` 必挂（P6）。
1. 重跑 ② 调查，**以面积/几何定 PID**，别继承上一个项目的 comp 语义（P28）；
2. ③ 聚类参数（距离/最小线数/区域数）按新图样调，跑完目视复核；
3. ④ 的补桥点、⑤ 的 END_BAND/EDGE_BAND 都是项目相关几何量，按新模型标定；
4. ⑦ 全部门禁重跑一遍，**特别是长边门禁**（QA PASS ≠ 空间合理）。
