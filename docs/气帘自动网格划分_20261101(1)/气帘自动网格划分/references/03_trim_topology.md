# 03 · 裁切拓扑：多环共节点的标准解 ★核心

> 沉淀自 2026-10-20 气帘 cab1 三面网格（缝线环 PID4×5 / 气腔环 PID3 / 布带环 PID2）。
> 结果：缝面↔气腔共节点 **100%**，缝面自由边 **0**，最小边长 3.0mm 达标。

---

## 1. 问题：多环嵌套网格的两难

气帘这类件是**嵌套环**：外轮廓（布带）⊃ 气腔轮廓（L3）⊃ 若干缝线环。
要求是：

1. 每个环单独成 PID，方便赋材料厚度
2. **界面共节点**（不能靠接触，要真捏合）
3. **网格边界严格贴合各环 CAD 曲线**
4. 网格完整无破洞

### 旧做法（失败）

各环**各自建 spline 面 → 各自 automesh → Python 侧 PIP 分组 + 边界投影缝合**：

| 问题 | 表现 |
|---|---|
| 界面不共节点 | 两套独立网格在界面处节点错开，靠投影硬拉 |
| 边界偏离曲线 | PIP 分组产生锯齿边，实测偏离最多 5mm |
| 缝合变形 | 投影拉节点 → 邻域折叠 177 个、短边一堆 |
| 修整时乱删 | 为消折叠删单元 → 满身破洞（用户点名批评） |

**根因**：把"拓扑问题"当"几何问题"解。共节点应该是**建模阶段用拓扑保证**的，
不是后处理用算法兜的。

### 新做法（裁切拓扑）

**只用一套面，通过裁切切出所有分区** —— 一次裁切产生的两块面
**共享同一条 topo edge**，automesh 时自然离散出相同节点。

---

## 2. 流程（cab1 实例）

```
comp 线框（338 条线，4 个 component）
  │
  │ ① 缝环 spline 建面 ×5            *surfacesplineonlinesloop
  │      取边线                       *linefromsurfedgecomp
  │      ↓（得到的 es 是普通线，绕开 composite 限制）
  │
  │ ② L3 spline 建面 → 取边线         （L3 原线是 composite，直接裁会静默失败）
  │
  │ ③ BLUE = 外轮廓全域面             comp2 七条线 spline
  │      用 L3 边线裁 BLUE            *surfacemarksplitwithlines
  │      ⇒ CAV(内 956944mm²) + BELT(外 197662mm²)       ← ★共享 topo edge
  │
  │ ④ 用 5 个缝面边线依次裁 CAV
  │      ⇒ CAV(带5洞) + 洞内面 ×5
  │      ↓
  │      **洞内面 = 真正的缝面**（与 CAV 共享 topo edge）
  │      删除 ① 建的 spline 缝面（它们和洞边不是同一条 edge）
  │
  │ ⑤ automesh 先小后大：SEAM → CAV → BELT
  │
  │ ⑥ equivalence2 0.05  ← 节点数应【零变化】
```

### ④ 的关键洞察（最难的一步）

**缝面不能沿用 ① 建的 spline 面。**

实测：用 spline 缝面 + CAV 各自 mesh → **共节点 0**。
原因：spline 面是独立建的，它的边界和 CAV 洞边在 HM 内部**不是同一条 topo edge**，
automesh 各自离散，节点必然错开。

**必须用裁切产生的洞内面当缝面** —— 它本来就是从 CAV 上切下来的，
边界即 CAV 的洞边，automesh 后共节点 100%。

```tcl
# 正确：收集裁切产生的洞内面
set seam_holes {}
foreach rd $ringdefs {
    lassign [trim_by $SCAV $es "SEAM_$tag" junk] SCAV hole
    if {$hole > 0} { lappend seam_holes $hole }     ;# ★ 洞内面入列
}
# 删掉原 spline 缝面
foreach s $seam_ids { lappend junk $s }
```
对应 P12。

---

## 3. 关键代码（`scripts/build_step1_2026.tcl` 精要）

```tcl
# --- 环建面 + 取边线（一体） ---
proc make_ring_surf {lns tag} {
  set i0 [hm_entitymaxid surfaces]
  *createmark lines 1 [lindex $lns 0]
  foreach id [lrange $lns 1 end] { *appendmark lines 1 $id }
  set r [catch {*surfacesplineonlinesloop 1 1 0 1} e]
  set ns [new_surfs $i0]
  if {[llength $ns] == 0} { log "RING $tag SPLINE FAIL r=$r e=$e"; return [list -1 {} {}] }
  set s [lindex $ns 0]
  set l0 [hm_entitymaxid lines]
  *createmark surfaces 1 $s
  catch {*linefromsurfedgecomp surfaces 1 1}          ;# ★ 面→边线
  set es {}; *createmark lines 1 all
  foreach ln [hm_getmark lines 1] { if {$ln > $l0} { lappend es $ln } }
  return [list $s $es $ns]
}

# --- 裁切：返回 (剩余体, 洞) ---
proc trim_by {surf lns tag junkvar} {
  upvar 1 $junkvar junk
  set m0 [hm_entitymaxid surfaces]
  *createmark surfaces 1 $surf
  eval "*createmark lines 2 $lns"
  set r [catch {*surfacemarksplitwithlines 1 2 0 13 0} e]
  set ns [new_surfs $m0]
  if {[llength $ns] == 0} { log "TRIM $tag FAIL r=$r e=$e"; return [list $surf -1] }
  set hole [biggest $ns]                              ;# 洞 = 新面里最大的
  set body [biggest [concat [list $surf] $ns]]        ;# 剩余体 = 全局最大
  foreach s $ns { if {$s != $hole && $s != $body} { lappend junk $s } }
  return [list $body $hole]
}
```

**识别策略**：裁切后新产生的面里，**面积最大的是洞**（缝环/内腔），
**全局最大的是剩余体**（外圈/被挖洞的大面），其余都是碎片 → 进 junk 删掉。

---

## 4. 失败分支与诊断

| 症状 | 根因 | 处理 |
|---|---|---|
| 裁切只出 13.8/1.8mm² 碎片 | 工具线是 **composite** | 先建面再 `*linefromsurfedgecomp` 取边线（P10） |
| `TRIM xxx FAIL` 静默返回 | 环**有缺口**（如 6.9mm） | 补桥接线（P9） |
| 某环建不出 spline | 环含**往返退化线** | 拆线取单程（P11） |
| 缝面共节点 0 | 用了 spline 缝面而非洞内面 | P12 |
| `RING x SPLINE FAIL` | 线序乱 / 重复线 / 非闭环 | 先看渲染底图，人工确认环结构（P13） |
| 裁不出来但也没报错 | 工具线不在面内（y≠0） | 先确认共面：`hm_getcoordinatesofpointsonline` 查 y 范围 |

### 几何调查是前置动作，别跳过

1. `export_lines_pts.tcl` 导出所有线的采样点
2. `render_lines.py` 渲染标准底图（固定坐标系，向右 +X、向上 +Z）
3. 出放大图逐环确认：闭环？往返线？缺口？重复线？
4. **人在图上确认语义**，再落到脚本里的环定义

cab1 就是这么查出来的：
- comp3 的 56 条线里，**157/170 是"去程+原路返回"的退化发夹线**（前后半完全重合）
- R3 环左端有 **6.9mm 缺口**（169 终点 → 157 起点）
- L3 的 2 条线是 **composite**
- 5 个缝环中 3 个是单线自闭环（337/336/193），2 个是多线分量

---

## 5. 通用化模板（换项目改这几处）

```tcl
# 1) 路径
set P "E:/your/project/work"

# 2) component id 映射（先用 list_live_entities 或 by collector 探明）
#    comp A = 外轮廓 / comp B = 内腔 / comp C = 缝线 ...

# 3) 环定义（来自几何调查，不要猜）
set ringdefs [list \
  [list tag1 {line_ids...}] \
  [list tag2 {line_ids...}] ]

# 4) 补桥点（如果环有缺口）
*createnode $x1 0 $z1 0 0 0
*createnode $x2 0 $z2 0 0 0
*createlist nodes 1 $n1 $n2
*linecreatefromnodes 1 0 150 5 179

# 5) 拆线点（如果有往返退化线）
*createnode $midx 0 $midz 0 0 0
*linesplitatpoint $ln [hm_entitymaxid nodes]
```

**mesh 尺寸**：5.0mm 主用；个别小环失败可回落 3.0mm。
`*interactiveremeshsurf 1 $sz 2 2 2 1 1` 的第 2 参数就是目标尺寸。

---

## 6. 验收判据（不达标不许往下走）

| 项 | 判据 | 工具 |
|---|---|---|
| 界面共节点 | seam↔cav **100%**、belt↔cav > 0 | `verify_step1_2026.py` |
| equivalence | 节点数**零变化**（变了说明拓扑没接上） | Tcl 日志 |
| 自由边 | 缝面 **0**；cav 仅外边界 | `verify_step1_2026.py` |
| 最小边长 | ≥ 3.0mm（公司规范） | `verify_step1_2026.py` |
| quad 占比 | belt/cav ≥ 96% | 同上 |
| 边界贴合 | 渲染 zoom 目检，网格边压在 CAD 曲线上 | `render_step1_2026.py` |
| K 文件 | `qa_kfile_strict.py` 退出码 0 | **门禁** |
