# 10 · 几何匹配自检 + 拉带连接检查（逐环对拍 / 连接质量门禁）

> 2026-10-22 沉淀：仅拓扑 QA（eid 唯一 / 无退化 / 无自由边）**查不出"几何是否和 CAD 曲线一致"**。
> NEW_CAB 出现过"凸台矩形环漏编→穹顶悬空""整环面积翻倍/边界漂移"等错误，QA 全 PASS 却几何错。
> 新增两套独立自检，作为交付前的**几何门禁**：
> - `geom_match_check.py` — 把每条 CAD 环的几何（质心 / 面积 / 形状）与它在网格里的实现逐项对拍。
> - `tether_conn_check.py` — 检查每个拉带连通组分与布带的连接质量（是否接对层、是否整面重叠、有无退化）。

---

## 1. 几何匹配自检 `geom_match_check.py`

### 1.1 为什么需要（而非"链条成多边形"）

早期方案把 IGES 线段贪心串成多边形 → 凸台环串成**蝴蝶结自交**（面积 3515 vs 真实 ~4500），
且 BELT/CAVITY 是**环面（带洞）**，单多边形/凸包面积无意义。本脚本改用更鲁棒的三件套：

1. **IGES 区域 = 点云凸包**（Andrew monotone chain）。凸环精确；凹环/环面是上界。
2. **网格区域 = 空间选择**：选出质心落在 IGES 凸包内（或距凸包边 < `sel_tol`）的单元。
   因此**不依赖 component 命名**——即便装配后所有拉带都是同一个 PID5，也能逐环选对。
3. **边界贴合 = 最近点查询**（IGES 采样点密度足够表示曲线）。

### 1.2 对比维度（每个环）

| 维度 | 判据 | 说明 |
|---|---|---|
| **位置** | 节点凸包质心 vs IGES 凸包质心，偏移 < `max(10mm, 3%·特征长)` | 用凸包质心（条带/环面也鲁棒，P44）；面积加权质心会让条带偏移 121mm |
| **面积** | 仅 `area_check=true`（凸实环，如 boss）生效；用**凸包面积比** | 单侧：mesh<CAD(漏网格)→FAIL；mesh>CAD(垫料外延)→仅 WARN（P46） |
| **形状/边界** | **主判据 CAD→mesh**（每个 CAD 点是否贴到网格节点） < `bnd_tol` | mesh→CAD 仅作 WARN（环面开口处天然偏大，P45） |

环面（BELT/CAVITY/SEAM）设 `area_check=false`，只查位置 + 边界。
**关键铁律**：选单元前必须按 `mesh_pid` **按层过滤**，否则 tether(Y=-1) 与 belt(Y=0) 在 2D X-Z 平面
完全重叠，纯 2D 选单元会把两层都选入（面积翻倍，P43）。

### 1.3 输入

- `--lines lines_pts.txt`：IGES 线段几何，兼容两种格式
  - 技能原生 `export_lines_pts.tcl`：`TAG lid len sp_x sp_z ep_x ep_z | x z;...`
  - IGES 分区技能：`L lid comp x1 y1 z1 x2 y2 z2 | x y z;...`（X-Y 平面）
- `--mesh <file.k | file.dat>`：标准 LS-DYNA K（逗号自由格式/定宽都独立解析）或本技能 `.dat`
  中间格式（`N id x y z` / `E comp eid n1..n4`）。`--map xy` 取 图纸x=模型X、图纸y=模型Z。
- `--rings ring_spec.json`（可选）：逐环定义，见 §1.4。不传则按 comp 自动分组（粗粒度）。

### 1.4 ring_spec.json 格式

```json
{
  "mesh_map": "xy",
  "rings": [
    {"name":"belt","type":"belt","iges_lines":[...],"area_check":false,"mesh_pid":2,"bnd_tol":8},
    {"name":"cavity","type":"cav","iges_lines":[...],"area_check":false,"mesh_pid":3,"bnd_tol":15},
    {"name":"seam","type":"seam","iges_lines":[...],"area_check":false,"mesh_pid":4,"bnd_tol":10},
    {"name":"boss0","type":"tether_boss","iges_lines":[550,551,552,553,554,555,556,525],"mesh_pid":5},
    {"name":"strap_r","type":"tether_strap","iges_lines":[],"constructed":true,"mesh_pid":5}
  ]
}
```
- `iges_lines`：该环在 lines_pts.txt 里的线 id 集合。
- `mesh_pid`：按层过滤（**必填**，否则重叠层误选）。
- `area_check`：环面/多段细线设 `false`；凸实环（boss）设 `true`（默认 true）。
- `bnd_tol`：per-ring 边界容差覆盖（cavity 充气口开口设 15）。
- `constructed:true`：构造件无 IGES 基准，跳过几何对拍（不 FAIL）。

`gen_ring_spec.py` 由 `--classify classify_final.json`（BELT/CAVITY/SEAM 自动分组）+ 
`--footprints assets/ringdef_newcab.json`（存活凸台足印环 + strap 构造件）生成该 JSON。

### 1.5 用法

```bash
PY="C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
"$PY" scripts/geom_match_check.py \
  --lines out/lines_pts.txt --mesh out/newcab_step1.k --rings out/ring_spec.json \
  --map xy --atol 0.15 --bnd 8 --sel-tol 8 --render out/v_geom_match.png
# 退出码 0 = 全部 PASS; 1 = 存在 FAIL
```

### 1.6 NEW_CAB 实测结果（2026-10-22）

13 环全部 PASS：

| 环 | IGES凸包 | mesh凸包 | 面积比 | 质心偏 | 边偏(C→m) | 结论 |
|---|---|---|---|---|---|---|
| belt | 1,201,626 | 1,201,621 | 1.000 | 0.0 | 2.6 | PASS [面积免检] |
| cavity | 1,095,030 | 1,094,927 | 1.000 | 0.0 | 13.0 | PASS [面积免检, bnd 15] |
| seam | 313,037 | 312,895 | 1.000 | 0.1 | 2.8 | PASS [面积免检] |
| boss0–5,8 | 4,674 | 5,472 | 1.17 | 5.2 | 2.2 | PASS (面积比>1=垫料外延, WARN) |
| boss6,7 | 5,061 | 5,404 | 1.06 | 2.8 | 2.3 | PASS |
| strap_r | — | — | — | — | — | PASS 构造件跳过 |

要点：belt/cav/seam 凸包比 1.000（位置精确）；boss CAD→mesh 覆盖 1.6–2.5mm（曲线贴合）；
cavity 13mm 间隙在充气口图纸固有开口（x537–926）内，属设计性开口。

---

## 2. 拉带连接检查 `tether_conn_check.py`

### 2.1 检查项（基于 5P-BAG_004 参考模型 + NEW_CAB 两轮返工，P21/P22/P23/P24/P29/P30）

1. **每个拉带连通组分都必须与单层布带 PID2 共节点**（至少 1 个）。参考模型：拉带与气腔双层共节点 = 0。
2. **绝不**与气腔 PID3 / 缝线 PID4 共节点（误连 = 错乱）。
3. **一条边啮合，不是整面重叠**：共节点占该组分周长比例应 < 50%（否则 FULL_OVERLAP FAIL）。
   依据：用户 2026-10-20 否决"整个重叠区啮合"——"你只要找一条平行边"。
4. **band 软校验**：凸台=顶帽水平边（高 Z 附近 8mm）；长条=末端竖边（最端 3mm，垂直布带长度方向）。
   位置不符仅 WARN（几何千变万化，不硬 FAIL）。
5. **无退化单元 / 无零厚度重合伪单元**（1-to-1 贪心漏做或跨文件 id 错位 P29 飞丝的典型症状）。

### 2.2 用法

```bash
"$PY" scripts/tether_conn_check.py \
  --mesh out/newcab_step1.k --map xy \
  --belt-pid 2 --cav-pid 3 --seam-pid 4 --tether-pid 5 \
  --rings out/ring_spec.json --render out/v_tether_conn.png
# 退出码 0 = 全部通过; 1 = 存在 FAIL
```

### 2.3 NEW_CAB 实测结果（2026-10-22）

16 个连通组分 **全部 PASS**：

- 接布带 2–14 共节点 / 组件；**误连气腔 0、误连缝线 0**
- 周长占比 1%–15%（无一整面重叠）
- 退化单元 0、重合伪单元 0
- band 识别正确：组分 0–5/11/13/15 = 末端竖边（strap）；6–10/12/14 = 顶帽边（boss）

---

## 3. 接入交付门禁

两套自检应作为 QA 之后的**几何门禁**运行（P41）：

```bash
# ⑦ 门禁（结构 + 几何）
"$PY" scripts/qa_kfile_strict.py  out/newcab_step1.k     # 拓扑门禁 PASS
"$PY" scripts/diag_long_edges.py                             # 长边 0
"$PY" scripts/diag_cavity_port.py                           # 端口自由边 0
"$PY" scripts/tether_conn_check.py --mesh out/newcab_step1.k --map xy --rings out/ring_spec.json
"$PY" scripts/geom_match_check.py --lines out/lines_pts.txt --mesh out/newcab_step1.k \
        --rings out/ring_spec.json --map xy
```

几何门禁的价值：拓扑全 PASS 时仍能抓出"几何没贴 CAD / 拉带没接对层"这类 QA 盲区错误。
