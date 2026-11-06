# 12 · auto_gate 自动校验套件（零依赖 / 自出图 / 规则可迭代）

> 2026-10-25 沉淀。位置：`scripts/gate/auto_gate/`。
> 定位：把散在 `qa_kfile_strict.py` / `geom_match_check.py` / `tether_conn_check.py` /
> `diag_*.py` 的门禁收敛成**一个案例无关、全自动、自己出图、门限可迭代**的统一套件。
> 设计目标：后续每个新气帘案例都用它校验，不过就迭代 `gate_rules.json`——**训练技能的主战场**。

---

## 0. 为什么需要它（与旧门禁的关系）

旧门禁三件事做不到：
1. **不自动出图**：靠 matplotlib/numpy，客户环境没有就瞎；
2. **口径写死在代码里**：每加一个案例要改代码，容易把上一个案例的修正覆盖掉；
3. **假阳性无处置通道**：cab1 实战中两处 FAIL（belt 30.5mm 边界偏差、拉带"误连气腔 50 节点"）
   都是**度量口径误报**，旧脚本只有 FAIL 一种声音，逼工程师人工甄别。

auto_gate 的对策：**PASS / WARN / FAIL 三级**（WARN = 提示工程师决策，不阻断交付）、
**门限外置**（`gate_rules.json`）、**图自出**（纯 Python SVG，浏览器可开）。

---

## 1. 组成与调用

```
scripts/gate/auto_gate/
├── run_gate.py       编排器：串起 5 大检查，出 JSON+文本报告+SVG 图
├── checks.py         5 大检查实现（拓扑/分层/环面积周长/环几何/拉带连接）
├── kio.py            K 解析器（自由格式 + 80 列定宽，LS-DYNA 两种都吃）
├── svgfig.py         纯 Python SVG 引擎（polyline/points/bars，零第三方依赖）
├── clean_kfile.py    清洗器：删孤儿节点（定义但无单元引用）/ 重复单元，幂等
├── gate_rules.json   ★门限与口径（活文档，带 _changelog，每次迭代记一行）
└── README.md         快速上手
```

```bash
# 单案例校验（案例配置在 cases/）
python scripts/gate/auto_gate/run_gate.py --case cases/cab1_clean/gate_case.json
# 自定义规则/出图目录/报告路径
python scripts/gate/auto_gate/run_gate.py --case <case.json> \
  --rules <gate_rules.json> --figdir <dir> --out <report.json>
# 先清洗再校验（推荐：cab1 实测清出 33,790 个孤儿节点，占 29%）
python scripts/gate/auto_gate/clean_kfile.py --in out/mesh.k --out out/mesh_clean.k
```

**退出码**：0 = PASS/WARN（可交付）；1 = 存在 FAIL（不许交付）。
**产出**：`gate_report.json`（机器读）+ `gate_report.txt`（人读）+ `gate_figs/*.svg`（6 张审查图）。

**案例配置**（`cases/<案例>/gate_case.json`）：`k_file` / `cad_lines_2d`（支持 `${WORKDIR}` 占位）/
`map`（图纸→模型映射，气帘为 `xy`：图纸 X=模型X、图纸 Y=模型Z）/ `pid_scheme`（角色→PID，
**必须以 survey_comps.tcl 面积实证为准**，P28）/ `cad_tag` / `layers` / `mesh_nominal_mm`。

---

## 2. 五大检查与判据

### ① 拓扑门禁（checks.check_topology）
重复节点（同坐标）/ 重复单元（同拓扑）/ 悬空引用（单元引用了不存在的节点）/ 孤儿节点 /
最小边长 / 长边（XZ>20mm、3D>30mm）。**判据**：重复/悬空 = FAIL；孤儿 = FAIL（可自动清）；
最小边 <3mm（规范 2.2）= WARN（密集弧包络处良性，工程师决策是否 remesh）；长边 = FAIL。

### ② Y 分层核验（checks.check_layers）
每个角色的节点 Y 应落在 `layers` 指定值（±tol）。**豁免**：期望双层（±0.5）时 Y0 边界节点合法；
**跨角色界面节点豁免**——拉带接布带的共节点在布带侧就是 Y0（曾把 146 个正常界面节点误报 FAIL，
2026-10-25.2 修）。

### ③ 环面积 + 节点路程（checks.check_ring_area_perim）
环面积 = 单元在 XZ 平面投影面积之和（闭合环用凸包）；节点路程（周长）= 凸包周长。
**判据**：面积比与周长比在 `[0.98, 1.05]`（`area_perim` 段）→ PASS；超出 → WARN/FAIL。
闭合环（气腔/缝线）无自由边，周长必须用凸包口径——用自由边会得到 0。

### ④ 环几何匹配（checks.check_ring_geometry）★反假阳性核心
逐 **CAD 线**（不是逐环汇总！）算 CAD→网格自由边最差偏差，再做**跨 PID 覆盖三级判定**：
- 自有 fabric 覆盖（`cover_tol_mm` 内）→ **局部特征 WARN**（如缝线切口、尖角）；
- 他 PID fabric 覆盖 → **跨 PID/错标 WARN**（如 cab1 的 BELT75 充气口领圈实际被气腔 fabric 覆盖，
  疑 CAD 标 BELT 错标——**不是 belt 缺口**）；
- 都无覆盖 → **真缺口 FAIL**（必须回 §4 修网格）。

主边界判据 CAD→mesh；mesh→CAD 仅 WARN（环面开口处天然偏大，P45）。
**重要教训**：覆盖判定必须基于**清洗后的被引用节点**——cab1 先前"belt 最近节点 0.4mm 良性"
的依据是**孤儿节点**，不成立；清洗后重测才发现 BELT74/75 是被气腔覆盖的跨 PID 线。

### ⑤ 拉带连接（checks.check_tether）
每个拉带连通组分必须与布带共节点（≥1）。**皮带腔界面识别**（2026-10-25.2 修）：
拉带∩气腔共节点若**同时属布带且 |Y| ≤ tol** → 良性界面节点（参考模型 5P-BAG_004 明确允许
"拉带∩气腔侧单层"，其值 112；cab1 为 50），不计误连；只有**落在气腔 Y±0.5 双层里**的才算真误连。
另查：共节点占周长 <50%（防整面重叠，P30）、无退化/伪单元、误连缝线 = FAIL。

---

## 3. 自出图清单（gate_figs/*.svg）

| 图 | 内容 |
|---|---|
| `gate_topology.svg` | 全模型节点脚印 + 最小边/长边标注 |
| `gate_layers.svg` | 各角色 Y 分布（分层正确性一眼看穿） |
| `gate_ring_area_perim.svg` | 逐环面积/周长比条形图 |
| `gate_geom_<角色>.svg` | 逐环 CAD 线（红）vs 网格节点（蓝）+ 最差偏差点标注 |
| `gate_tether_conn.svg` | 拉带连通组分与布带连接特写 |

纯 Python SVG：无 matplotlib/numpy 依赖，任意客户环境浏览器直接开。
**协作约定**（用户 P13）：几何归机器、语义归人——图是标准底图，人在图上指认，机器做空间匹配。

---

## 4. 门禁迭代方法（训练主循环）

```
新案例不过 → 看 gate_report.json 定位：
  ├─ 网格真问题（真缺口/真误连/重复/悬空）→ 回流水线修（remesh/补桥/重捏合），不动规则
  └─ 口径/门限问题（假阳性/过严/过松）→ 改 gate_rules.json，并在 _changelog 记一行：
       日期 | 案例 | 触发现象 | 改动 | 回归结果
  └─ 回归：cases/ 下全部旧案例重跑，确认不回退 → 迭代完成
```

**gate_rules.json 结构**（节选）：
```jsonc
{
  "_version": "2026-10-25.2",
  "_changelog": [ { "date": "...", "case": "...", "change": "...", "regression": "..." } ],
  "topology":  { "min_edge_mm": 3.0, "long_edge_xz_mm": 20.0, "long_edge_3d_mm": 30.0 },
  "layers":    { "tol": 0.05, "interface_collapse_tol": 0.05, "exempt_cross_role": true },
  "area_perim":{ "ratio_lo": 0.98, "ratio_hi": 1.05 },
  "ring_geometry": {
    "main_tol_mm": 8.0, "cavity_bnd_mm": 15.0,
    "cross_pid_coverage": { "enabled": true, "cover_tol_mm": 3.0 }   // 三级判定开关
  },
  "tether": {
    "expect_pid": "belt", "perimeter_ratio_max": 0.5,
    "belt_cavity_interface": { "enabled": true, "tol_mm": 0.05 }     // 良性界面豁免
  }
}
```

**已登记迭代**（详见 gate_rules.json `_changelog`）：
- `2026-10-25.1` 套件建立（五大检查 + SVG 引擎 + 三级判定雏形）；
- `2026-10-25.2` cab1 回归修正三项：① 分层豁免跨角色界面节点（146 个正常节点不再误报）；
  ② 环几何跨 PID 覆盖三级判定（BELT74/75 定性为跨 PID WARN 而非 belt 缺口）；
  ③ 拉带皮带腔界面豁免（50 个良性节点不再误报）+ 拓扑加孤儿节点检查
  （cab1 实测抓出 33,790 个孤儿节点——**旧门禁完全没发现**）。

---

## 5. cab1 回归基线（v2026-10-25.2，清洗版 K）

| 检查 | 结果 |
|---|---|
| 拓扑 | WARN（仅 <3mm 尖边：belt 22 / cav 20 / tether 19；0 重复 / 0 悬空 / 0 孤儿） |
| Y 分层 | PASS（146 个界面节点正确豁免） |
| 环面积/周长 | PASS（比值 1.00–1.04） |
| 环几何 | WARN（cavity 2.46mm / seam 2.50mm PASS；belt 主环贴合，BELT74/75 跨 PID WARN） |
| 拉带连接 | PASS（146 连接、0 真误连、50 良性界面） |
| **总判定** | **WARN（PASS 3 / WARN 2 / FAIL 0）** |

两个 WARN 均为"提示工程师决策"性质，非网格破损。
