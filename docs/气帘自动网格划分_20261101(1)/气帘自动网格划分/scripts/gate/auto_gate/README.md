# auto_gate · 气帘网格自动校验套件（案例无关 / 全自动 / 零依赖）

> 沉淀目标：**训练一套可复用的网格划分+自校验能力**，不是为某一个气帘。
> 客户给不同几何（不同分区/曲线/PID），换一份 `case_*.json` 即可跑同一条链。
> 门禁规则在 `gate_rules.json` 里随每次实战**迭代完善**（见其 `_changelog`）。

## 0. 设计原则

| 原则 | 体现 |
|---|---|
| 全自动、零人工 | 一条命令跑完所有检查+出图+汇总；`clean_kfile` 自动清杂质 |
| 案例无关 | 脚本内**零** cab1/cab3/6P 硬编码；一切由 case 配置 + 规则驱动 |
| 零第三方依赖 | 只用 Python 标准库；出图用**纯 Python SVG**（任意客户环境可开，不挑 matplotlib） |
| 门禁可迭代 | 门限/口径外置 `gate_rules.json`，每战一版，`_changelog` 记录教训 |
| 反假阳性 | 两级口径固化（见 §4），避免"诚实网格被误判 FAIL" |

## 1. 一键用法

```bash
cd scripts/auto_gate
# 先自动清洗孤儿节点(强烈建议, 见 §3)
python clean_kfile.py --in <mesh.k> --out <mesh_clean.k>
# 再跑校验套件
python run_gate.py --case case_cab1.json          # 换案例就换这个文件
```

退出码：`0` = PASS/WARN，`1` = FAIL（可驱动 CI/流水线判断）。
产物：控制台汇总 + `<K同目录>/gate_report.json(.txt)` + `<K同目录>/gate_figs/*.svg`。

## 2. 文件职责

| 文件 | 职责 |
|---|---|
| `gate_rules.json` | **可迭代门禁规则**（门限+反假阳性口径+changelog） |
| `case_*.json` | **案例配置**：输入 K / CAD 线 / PID 方案 / 角色 Y 分层 / CAD tag 映射 |
| `kio.py` | K 解析器（自动识别逗号自由格式 & 80 列定宽）+ 拓扑分析 |
| `svgfig.py` | 纯 Python SVG 引擎（坐标图 + 横向条形图） |
| `checks.py` | 五大检查模块（见 §3） |
| `run_gate.py` | 套件编排器（串检查 + 汇总 + 出图 + 报告） |
| `clean_kfile.py` | 自动清洗：删孤儿节点 |

## 3. 五大自动检查 + 自出图

| 检查 | 判据 | 自出图 |
|---|---|---|
| **拓扑门禁** | 重复节点/单元、孤儿节点、缺失引用、最小边、每 PID 连通分量、自由边 | — |
| **Y 分层核验** | 各角色节点 Y 符合配置；气腔双层+界面收 Y0；跨角色界面节点豁免 | — |
| **环面积 / 节点路程** | 网格凸包面积/周长 vs CAD 凸包（合格带来自规则） | `gate_ring_area_perim.svg`(条形) + `gate_ring_footprint.svg`(脚印叠加) |
| **环几何匹配** | IGES 曲线 → 网格自由边界偏差，**逐 CAD 线拆解** | `gate_geom_<role>.svg`(CAD vs 网格+最差标注) |
| **拉带连接** | 拉带↔布带共节点(应连)、误连缝线(禁)、误连气腔(**界面识别**) | `gate_tether_conn.svg`(连接特写) |

## 4. 反假阳性口径（本套件的核心价值，沉淀自 cab1 实战）

1. **环几何·逐线拆解 + 跨 PID 覆盖**（`ring_geom.per_line_breakdown`）
   环整体 boundary 偏差若仅由少数"局部特征线"驱动，按三级判定：
   - 该线点被**本 PID fabric** 覆盖（点在四边形内 or 距节点 ≤ `cover_tol_mm`）→ 局部特征 → **WARN**
   - 仅被**他 PID fabric** 覆盖 → 跨 PID / 接口 / CAD 错标 → **WARN**（提示核对归属）
   - 任何 PID 都不覆盖 → 真缺口 → **FAIL**
   > cab1 实例：BELT59 主环 2.41mm；BELT74/75（充气口领圈）被**气腔** fabric 覆盖 → 跨 PID WARN，不是 belt 缺口。

2. **拉带·皮带腔界面识别**（`tether.belt_cavity_interface_benign`）
   拉带∩气腔共节点若**同时属于布带**且 `|Y| ≤ interface_y_tol`，属"拉带经布带穿过皮带腔界面"的正常拓扑（参考模型 5P-BAG_004 明确允许），**不计误连**；只有落在气腔双层（`|Y|>`tol）的才算真误连。

3. **分层·界面豁免**：跨角色共节点可取搭档角色 Y（如拉带接布带 → Y0），不按本角色 Y 强判。

## 5. 如何迭代门禁（每次实战后）

1. 跑套件 → 看哪条判据误报/漏报；
2. 改 `gate_rules.json` 对应门限/口径（**只改这个文件，不改代码**）；
3. 在 `_changelog` 追加一行（版本 + 教训）；
4. 回归跑旧案例，确认没改坏。

> 经验门限起点：`min_edge 3.0`(WARN)、`area_ratio 0.90–1.10`、`perimeter_ratio 0.85–1.20`、
> `boundary_dev_main 5.0`(5mm 网格)、`cover_tol 3.0`、`interface_y_tol 0.6`。

## 6. 接一个新气帘案例

1. 复制 `case_cab1.json` → `case_<新项目>.json`，改：`k_file` / `cad_lines_2d` /
   `pid_scheme`(角色→PID) / `cad_tag`(角色→CAD 线 TAG) / `layers`(角色→厚度轴位置)。
2. （几何事实须重新确认，参考 `references/11_cab3_auto_pipeline.md` §2 的清单式核验。）
3. `python clean_kfile.py --in <k> --out <k_clean>`；`python run_gate.py --case case_<新项目>.json`。
4. 若新几何触发新误报 → 回 §5 迭代 `gate_rules.json`。

### 6.1 厚度轴必须显式声明（cab2 教训，2026-10-31）

本套件的判据内部统一按 **(平面U, 厚度W, 平面V) = (x, y, z)** 布局写死（沉淀自 cab1：
几何在 X-Z 平面、Y 是厚度轴）。**换项目若厚度轴不同，必须配 `thickness_axis`**，
否则分层/几何检查会静默给出无意义结论。

```json
"thickness_axis": "Z"     // cab2: 几何在 X-Y 平面, 厚度轴 = Z
```

| 取值 | 内部重排 | 平面 |
|---|---|---|
| `"Y"`（默认，兼容 cab1） | (x, y, z) 原样 | X-Z |
| `"Z"`（cab2） | (x, z, y) | X-Y |
| `"X"` | (y, x, z) | Y-Z |

`run_gate.py` 启动时会打印实测的**厚度跨度**并做合理性告警
（厚度跨度 > 平面跨度的 50% → 提示疑似配错），报告 JSON 里也留 `thickness_axis` 字段。

> 只做读入时的坐标重排，**不改任何判据逻辑**，cab1 回归不受影响。

### 6.2 CAD 环可能是断开的（cab2 实测）

IGES/DXF 导出的线环常带断口，本套件按"环整体"匹配，断口本身不报 FAIL，但要知道：

- cab2 实测：L1 布带 3 处断口（5.70 / 7.15 / **35.08** mm，均在顶边）；L2 气腔 **1 处 86.00mm**
  （颈部沿 L1 的一段）——这 86mm 正是 hmbatch 裁切时 `SL3` 需要"主环 + 桥接段"两条边的原因。
- 自查方法：端点聚类后统计度=1 的悬挂点，两两最近配对即断口清单
  （参考 `work/cab2_skill/out/find_gap.py`）。
- **别用 flood-fill 求环面积**：断口会让外部灌进来，得到 0 或几 mm²。
  要算面积请用 HyperMesh 裁切面的面积（最权威），或补断口后再栅格化。


## 7. cab1 回归结果（2026-10-25，rules v2026-10-25.2）

清洗删 **33,790** 孤儿节点（原 115,446 → 81,656，占 29%，文件 −15%；单元/引用零改动）。

| 检查 | 结果 |
|---|---|
| 拓扑 | WARN（仅 <3mm 边：belt 22 / cav 20 / tether 19；0 重复/孤儿/悬引用） |
| Y 分层 | PASS（拉带 146 界面节点正确豁免） |
| 环面积/周长 | PASS（面积比 1.003–1.035，周长比 1.001–1.011） |
| 环几何 | WARN（cavity 2.46 / seam 2.50 PASS；belt 主环贴合，BELT74/75 充气口领圈跨 PID WARN） |
| 拉带连接 | PASS（接布带 146；误连缝线 0；皮带腔界面良性 50，真误连 0） |
| **总判定** | **WARN**（PASS 3 / WARN 2 / FAIL 0） |

两个 WARN 均为"提示工程师决策"性质（<3mm 尖角、充气口领圈归属），非网格破损。
