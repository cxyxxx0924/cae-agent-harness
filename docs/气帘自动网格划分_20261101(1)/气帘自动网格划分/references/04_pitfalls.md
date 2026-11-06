# 04 · 坑位清单 P1–P20（2026 专版，动手前扫一遍）

> 标 ★★★ = 会造成**客户侧打不开文件**或**整条链返工**的级别。
> 全部来自 2026-10-20 气帘 cab1 实战，每条都真踩过。

---

## P1 · `*ELEMENT_SHELL` 漏写 eid → 全表 ID 重复 + 幽灵 part，HM 读入直接卡死 ★★★

**现象**：HyperMesh 2026 与 2020 打开生成的 K 文件都"死机"；用户自己的十几兆模型秒读。
**根因**：写入器把单元卡写成 5 列 `pid, n1, n2, n3, n4`，**漏掉第一列 eid**。
LS-DYNA 官方字段顺序是 `eid, pid, n1, n2, n3, n4, ...`，读取器按位置解析：

| 我写的 | 被读成 | 后果 |
|---|---|---|
| pid (2/3/4) | **eid** | 80464 个单元只有 3 个 ID → 全表重复 |
| n1 (36854…) | **pid** | 63058 个**未定义的幽灵 part** |
| n2,n3,n4 | n1,n2,n3 | 拓扑整体错位，n4 丢失 |

8 万次 ID 冲突 + 6 万个不存在的 part → HM 卡死。**这是"读文件死机"的标准症状。**

**正确写法**（三角 5 列、四边 6 列）：
```python
eid = 1
for pid, ns in kelems:                       # ns 已去重, len ∈ {3,4}
    row = f"{eid}, {pid}, {ns[0]}, {ns[1]}, {ns[2]}"
    if len(ns) == 4:
        row += f", {ns[3]}"
    f.write(row + "\n")
    eid += 1                                 # 唯一递增，从 1 起
```
**写完立刻验三条**：① `len(set(eids)) == len(eids)`；② 单元 pid ⊆ `*PART` 的 pid；
③ 单元引用的 nid 全在 `*NODE` 表里。

**为什么没早发现**：`lspp check_keyword_deck` 返回 `ready_for_solver=true` 让人误判——
它只查**语法**（关键字拼写、字段数），**不查 ID 唯一性与引用有效性**。
→ **语法通过 ≠ 文件能读**。必须过 `qa_kfile_strict.py`（P20）。

---

## P2 · 2026 批处理必须先加载用户模板 ★★★

不写 `hm_framework loaduserprofile LsDyna Keyword971_R16.0`，
任何创建实体都报 `No user profile or template file loaded` / `data-name "pid" is not valid`。
**只写 `loaduserprofile LsDyna`（不带版本号）无效**——只定位目录，不解析模板文件。
判据：`[hm_info templatefilename]` 非空。（2020 不需要这句。）

---

## P3 · 2026 建实体数据名变了

| 2020 | 2026 |
|---|---|
| `pid=...` | **`propertyid=...`** |
| `nodeid1=1 nodeid2=2 …` | **`nodes="1 2 3 4"`** |

---

## P4 · 2026 与 2020 网格结果**不等价**，交付链必须锁版本 ★★★

同一个 Tcl 两版跑出来的差异（cab1 实测）：

| | 2020 | 2026 | 差 |
|---|---|---|---|
| 节点 | 87091 | 84489 | −3% |
| 气腔单元 | 38993 | 36559 | **−6.2%** |
| blue 全域 | 45780 | 45748 | −0.07% |

两版都能跑通，但结果对不上。**已交付的 deck 锁死一个版本，中途不许换**，
否则客户侧数量对不上无法追溯。本机已锁定 **2026**。

---

## P5 · 曲线采样命令的两个陷阱

- `hm_getcoordinatesofpointsonline $ln $u`（u∈[0,1]）返回**嵌套列表** `{{x y z}}`，
  必须 while 解包，否则 `lindex $v 0` 拿到的是整个坐标串 → 点"飞了"。
- `hm_getlinepointsatdistance` 是 **5 参数、按弦长**取点，**d=0.0 会卡死**（hmbatch 挂起不返回）。
  → 采样一律用 u∈[0,1] 那条。

---

## P6 · 2026 没有 `hm_entitycount`

改用 `*createmark X 1 "all"` + `llength [hm_getmark X 1]`。
取某 component 下的线：`*createmark lines 1 "by collector" $cid`。
识别"新建了什么"：先记 `hm_entitymaxid`，事后筛 `> i0`。

---

## P7 · 别用 `launch_hypermesh` 代启 GUI

实测起出多余实例（孤儿 hw.exe），要 taskkill 清理，还占内存。
**让用户自己启动** GUI 并打开 Bridge 扩展——用户更清楚自己要的 profile 和 session。

---

## P8 · `load_live_model` 的 `project_id` 必须是项目 id，不是磁盘路径 ★

三步顺序不能反：
```
1) create_project(name="xxx")           → project_20261020_110617_037243
2) 复制输入文件到 <workspace>/projects/<proj>/input/
3) load_live_model(input_name="cab1.hm", project_id="<proj>", replace_current=true)
```
直接传 `path=绝对路径` 或 `project_id=磁盘路径` 都会报 invalid
（`projects.py` 校验的是 workspace 项目注册表）。

---

## P9 · 环有缺口 → 裁切**静默失败**（不报错，就是切不出来） ★★★

cab1 的 R3 环左端有 **6.9mm 缺口**（169 终点 → 157 起点）。
`*surfacemarksplitwithlines` 不报错，只切出两个小碎片（13.8/1.8mm²）。

**处理**：先补桥接线
```tcl
*createnode $x1 0 $z1 0 0 0
*createnode $x2 0 $z2 0 0 0
set n0 [hm_entitymaxid nodes]
*createlist nodes 1 [expr {$n0-1}] [expr {$n0}]
*linecreatefromnodes 1 0 150 5 179
```
补上后 R3 立刻切出 4197.2mm²。**缺口检测靠几何调查出图，不靠猜。**

---

## P10 · composite 线**裁不动**，必须先建面再取边线 ★★★

`hm_getlinetype $ln` 返回 composite 的线（cab1 的 L3 两条线就是），
直接扔给 `*surfacemarksplitwithlines` 会**静默失败**（只出 13.8/1.8mm² 碎片）。

**绕过**（唯一可靠手段）：
```tcl
*surfacesplineonlinesloop 1 1 0 1            ;# 先建面
*createmark surfaces 1 $sid
*linefromsurfedgecomp surfaces 1 1           ;# 从面边缘取【普通线】
```
用取到的边线去裁，立刻成功（L3 裁 BLUE → CAV 956944 + BELT 197662）。

---

## P11 · 往返退化发夹线会让 spline 建面失败

cab1 的 157/170 是"**去程 + 原路返回**"的退化线（前后半采样点完全重合，dmax≈0）。
塞进环里 → `*surfacesplineonlinesloop` 返回 0 个面。

**判定**：闭合线取前后半对应点求最大距离，≈0 即往返线。
**处理**：`*linesplitatpoint` 拆成两段，取单程那条进环定义。

---

## P12 · 缝面不能用 spline 面，必须用**裁切产生的洞内面** ★★★

用 ① 建的 spline 缝面 + CAV 各自 mesh → **共节点 0**。
原因：spline 面边界与 CAV 洞边在 HM 内部**不是同一条 topo edge**，各自离散必错开。

**正解**：裁 CAV 时用 `trim_by` 返回的 **hole（洞内面）**当缝面，
它本来就是从 CAV 上切下来的，边界即 CAV 洞边 → 共节点 100%（161/161/147/132/465）。
原 spline 缝面丢进 junk 删掉。

---

## P13 · 几何调查必须**出图给人看**，不要"自动识别"猜语义 ★

用户明确要求：几何/图形类工作交互语言是**图像**，
不要用自动搜索去猜环的语义——"肯定会出错"。

标准动作：
1. `export_lines_pts.tcl` 导出所有线采样点
2. `render_lines.py` 渲染标准底图（固定坐标系：向右 +X、向上 +Z）
3. 出放大图逐环确认：闭环？往返线？缺口？重复线？
4. **人在图上确认语义** → 再落进脚本的环定义

cab1 靠这套查出了 P9/P10/P11 三个问题，纯代码试探会浪费几小时。

---

## P14 · `*linesplitatpoint` 的参数是**节点 id**，不是坐标

直接传坐标报"找不到节点"。先 `*createnode` 建节点，拿 `hm_entitymaxid nodes` 再拆。

---

## P15 · `*linecreatefromnodes` 必须先 `*createlist`

直接把两个节点 id 当参数传**无效**（不报错也不建线）。
```tcl
*createlist nodes 1 $n1 $n2
*linecreatefromnodes 1 0 150 5 179
```

---

## P16 · automesh 三步缺一不可

```tcl
*interactiveremeshsurf 1 $sz 2 2 2 1 1    ;# ① 布种子
*automesh 0 2 2                            ;# ② 执行
*storemeshtodatabase 1                     ;# ③ ★ 落库
```
缺 ③ → 网格生成了但没保存，导出 0 单元。
另：`*elementorder 1` + `*setedgedensitylinkwithaspectratio -1` 先设好。

---

## P17 · 边界贴合靠**同源拓扑**，不靠投影缝合 ★★★

用户两次点名的要求："网格边界必须严格贴合各环几何曲线"。
- ✗ 投影缝合：PIP 锯齿边偏离最多 5mm，还会带来折叠/短边
- ✓ 同源裁切：边界即 CAD 曲线的 topo edge，automesh 后严丝合缝（见 `assets/v2026_seam_zoom.png`）

---

## P18 · 网格修整**不准乱删**（用户两次点名） ★★★

曾经删"面积<2mm² 或最小角<3°"的单元 → belt 2427 自由边 / seam 1195 自由边 = 满身破洞。

**只准删两种**：
1. **真退化**：去重后独立节点 < 3
2. **完全重复**：节点集完全一致

小面积、小角度、短边一律**保留**，用"微调节点位置"修（斥力/回插），
接受条件是"不折叠且无短边"，不是删掉。

---

## P19 · 2026 没装 LS-DYNA 导入 translator，批处理验证不了 K 文件 ★

`*feinput` / `*feinputwithdata2` 报 **`The translator does not exist`**
（2026 安装树里没有 dyna 导入模块）。2020 的模板路径也对不上。

→ **不能用 2026 hmbatch 做 K 文件回读验证**。可选通道：
- 静态严格校验 `scripts/qa_kfile_strict.py`（首选，秒级）
- LS-PrePost（`mcp__lspp-mcp`）真读
- 用户 GUI 手动打开

**另**：K 文件**不能**用 `*readfile` 读 —— 那是 HM 数据库格式通道，
必报 `The file specified is not a HyperMesh database`。K 走 `*feinput*` 系列。

---

## P20 · 交付门禁：K 文件出盘前必须过 `qa_kfile_strict.py` ★★★

P1 的制度化。`scripts/qa_kfile_strict.py` 设计原则：
- **独立解析**，不 import 任何写入脚本、不复用字段假设（字段顺序硬编码在文件头常量）
- 检查项比真实读取器更严：纯 ASCII、eid 唯一且 >0、pid 必须在 `*PART` 集合中、
  nid 必须存在且 >0、无重复单元（同节点集）、单元内无重复节点、`*SECTION`/`*MAT` 引用完整
- 汇总报数不刷屏（8 万行只打样例 + 总数）
- **退出码 0 = 可交付，1 = 禁止交付**，可挂流水线

```bash
python scripts/qa_kfile_strict.py out/cab1_step1_2026.k      # 单文件
python scripts/qa_kfile_strict.py out/*.k                     # 批量（退出码汇总）
```

**存量体检（2026-10-20）**：
| 文件 | 判定 |
|---|---|
| `cab1_step1_2026.k`（修复后） | **PASS** |
| `cab1_stage2.k` | FAIL — 幽灵 PID + 2434 退化四边形 |
| `cab1_full.k` | FAIL — 11723 退化四边形 |
| `cab1_step1.k` | FAIL — 548 退化四边形 |

> **退化四边形**（三角写成 6 列 `n4==n3`）虽"能算"，但违反公司规范
> "禁止重复单元与重复节点"，且部分读取器报警 → **一律写 5 列** `eid,pid,n1,n2,n3`。
>
> `*PART` 解析提醒：数据行**可能无逗号**（定宽/空格分隔），必须先按"能否转数值"判定。
> 先试 `split(",")` 会把它误当 title 行 → pid 全部漏掉（本脚本已踩并修复）。

---

## 附：Tcl 自身的坑（与版本无关，每次都中）

```tcl
lappend keep [format "%s(%.0f)" $s $a]     ;# ✓
lappend keep "$s([format %.0f $a])"        ;# ✗ 被当数组引用
lappend junk $SL3                          ;# ✓
foreach s $junk { lappend junk $SL3 }      ;# ✗ 迭代中改自身 → 无限膨胀
```

**运行铁律**：路径全英文（中文路径 hmbatch 必挂）；
残留 `hw.exe` 先 `taskkill //F //IM hw.exe`；
`*readfile` 返回 1 不代表失败，以实体计数为准。

---

## P21 · 拉带节点合并目标必须限定为"单层布带(PID2)"，绝不能并到气腔/缝线 ★★★

`step1_mesh_2026.txt` 导出含 belt/cavity/seam **全部 44499 节点**。若合并目标用全部节点，
拉带会一并并到气腔(PID3)/缝线(PID4)上 → 连接错乱。

**参考模型实证**（P22）：拉带(PID8)只与单层布带(PID6)共节点(115)，与气腔双层(PID4)共节点数=0。
→ 合并目标必须取 **belt 单元引用的节点**（本模型 PID2，共 9222 个），见 `assemble_tabs.py` §2。
判定：合并后 `shared = pid5_nodes & pid2_nodes`，不应有节点落进 PID3/PID4。

---

## P22 · 拉带↔布带连接是**直接节点捏合**，不是 CNRB ★★

曾误判：`*CONSTRAINED_NODAL_RIGID_BODY` id 10000145 + `*SET_NODE_LIST` 10200008
（含节点 (1890.96,0,1314.79)/(1890.95,-0.5,1314.82)）是拉带连接 → **错**。
实测该 CNRB 是**布带↔气腔顶**的连接，与拉带无关。

**正解**：拉带靠与布带**共享节点**（Y0 真共节点）连接，参考模型共 115 个。
本技能的 `assemble_tabs.py` 用 TOL 内合并复用布带节点 gid 实现，不引入约束。

---

## P23 · 拉带边界全并到布带会产生**零厚度重合单元** → 必须 de-dup（与 QA 同口径） ★★★

拉带在重叠区节点全并到布带后，个别拉带单元 4 节点全部落在布带上，
与某布带单元**节点集完全相同** → 零厚度重合伪单元（HM 里叠了一层）。

- 参考模型零重合单元（靠"共节点"而非"共单元"连接）。
- **处理**：装配时剔除节点集（`tuple(sorted(ns))` 无序比对，与 `qa_kfile_strict.py` 口径一致）
  与既有单元相同的拉带单元。这是**合法去重**，不是"乱删"（P18）——伪单元非真实几何。
- 当前基线：剔除 44 个，PID5 余 3233 单元，QA PASS。

---

## P24 · 捏合用**全局 1-to-1 贪心**，杜绝单元内两节点并到同一布带节点 ★★

早期用"每节点取最近 + 冲突循环改选次近" → 密集处多个拉带节点抢同一布带节点，
改选又制造新冲突 → **12 个退化单元被丢**（单元内 <3 独立节点）。

**正解**：把所有 (拉带节点, 布带节点, 距离) 三元组按距离升序，贪心分配，
**每个布带节点至多被一个拉带节点复用** → 结构上不可能出现单元内两节点并到同一布带节点
→ 零退化丢单元。落空的密集节点保留为独立节点（取新 gid），几何仍贴布带。
（见 `assemble_tabs.py` §4）

---

## P25 · 凸台分上下两片时，共享"膝弦边"靠坐标 dedup + HM 确定性离散 ★

凸台 up/dn 两片在膝弦处分割，共享一条弦边。**不能**让两片各自独立离散弦边 → 节点错开不共节点。

- 生成 Tcl 时弦边**只建一次**，up/dn 用同一组节点（`coord_map[(round(x,6),round(z,6))]` 查表）。
- 装配端再加 `round 1e-4` 坐标 dedup 安全网。
- 验证：up/dn 共享节点 X 坐标 3 位小数一致（如 1252.147 / 1261.597），共节点天然成立。

---

## P26 · 拉带 mesh 不能用 grouped automesh，必须**逐面 automesh** ★

早期把 16 个面塞进一个 component group 调一次 automesh → **只 mesh 了第一个面**，其余 `_dn` 全 0 单元。
`build_tabs_2026.tcl` 已改为**每块面独立** `*automesh` 循环（P16 三步齐全：布种子→执行→落库）。

---

## P27 · 左下拉带"完全没连接"、左上"只连 2 处"的根因是合并目标/TOL 错配 ★★

用户截图反馈的两种失败，根因都是早期合并只 snap 了拉带节点里距布带**自由边 1.5mm** 的少数节点（仅 53 个）。
**正解**：对拉带**全部节点**做 TOL(3mm, XZ) 内对**全部 9222 布带节点**的合并 → 2283/3596（belt-only 版 674）节点连上，
重叠段外周围全部共节点（验证见 `07_tab_tether_meshing.md` §4 区域报告）。

---

## P28 · 参考模型 PID 解码别想当然，以脚本实测为准 ★★

旧技能文档写"component4=外轮廓"被实测推翻（实为气腔）。本技能 cab1 实测 PID 映射：
- PID2 = 单层布带（本模型对应 step1 的 belt）
- PID3 = 127 单元夹层；PID4 = 气腔双层 75482 单元（Y-0.5~0.6）
- PID6 = 单层布带 9405 单元；PID7 = 气腔侧 2247；PID8 = 拉带 1054（Y -1.12→0）

任何"看起来像"的推断都先跑 `ref_conn_map.py` 量共节点数，再下结论。

---

## P29 · 中间导出文件的 nid ≠ K 文件的 gid（重编号），跨文件引用 id 必炸 ★★★

**现象**：拉带装配后 HM 里全模型"飞丝"（拉带/布带/气腔都拉出十几~几十毫米的斜线），
但 `qa_kfile_strict.py` 全项 PASS——QA 查拓扑合法性，**不查空间合理性**。

**根因**：`assemble_step1_2026.py` 写 K 时对节点做了 **gid 重编号**
（`for nid in sorted(nodes): gid_of[nid] = next_gid`，气腔内层节点还一拆二）：
- 导出 `step1_mesh_2026.txt` 的 nid **不连续**（HM 删过节点，min=4, max=44502）
- K 的 gid = txt nid 的**排序序号** → 两个 id 空间**整体错位**（实测 0/44499 个 id 同坐标，差 3 个排名起）
- 拉带合并时拿 txt 的 nid+坐标找"3mm 内布带节点"，写进 K 后该 gid 实际在隔壁 → 每个合并都拉丝

**铁律**：**任何"引用 K 文件节点/单元"的后续装配，目标 id 与坐标必须直接从目标 K 文件解析**
（`*NODE` + 对应 PID 的 `*ELEMENT_SHELL`），绝不从中间导出文件（txt/json）拿 id。
中间导出只用于渲染/统计，不用于 id 引用。

**配套门禁**：交付前加一条**空间合理性检查**——扫最长边
（`scripts/diag_long_edges.py`：XZ>20mm 或 3D>30mm 计数必须为 0）。
QA 拓扑 PASS + 空间 PASS 才许交付。


## P30 · 拉带与布带只能"一条边"啮合，左拉带必须是【末端竖边】★★★

**现象**（用户 2026-10-20 看图否决）：凸台/拉带与布带**整个重叠区全部共节点**——
用户："与部件层整个区域全部网格啮合，这肯定有问题。你只要找一条平行边，
可以参考一下那个参考模型，它只有一条边啮合就行了。"

**根因**：早期把"3mm 内的所有拉带节点"无差别并到布带 → 重叠区全捏合。

**规则**（参考模型 `5P-BAG_004.key` 实测 + 用户 2026-10-21 追认）：
- **凸台片**（`tab*_up/dn`）：只并该片**最高连接 Z 附近 8mm（EDGE_BAND）**的顶帽边
  → 一条**水平线**（平行布带长度方向）。用户确认无问题。
- **左区长拉带**（`tabc*`/`tabh*`）：只并该片**最右端 3mm（END_BAND）**的节点
  → 一条**竖线**（垂直布带长度方向）。用户："啮合点应该在拉带的顶端，
  粘合线应该都是垂直于布带的长度方向。"
- 参考 R8 实证：带体 Y−0.5 到 x1074 → 2 个爬坡单元抬到 Y0 → 末端竖边 3 共节点。

## P31 · HORIZ 长条别用"全线缓冲并集"取外环：装饰线会上轮廓、开运算还会整体外鼓 ★★

**现象**：HORIZ 横条外环面积 3263mm²（CAD 真实 2270），右端是一根 7mm 斜刺，
末端连接节点散乱 → 1-to-1 贪心把拉带节点并到十几毫米外的布带节点，连接区出现 7.1mm 自由边。

**根因**：旧构造 `unary_union(全线).buffer(2) → 填洞 → buffer(-2.5).buffer(2.5)`：
1. **净膨胀 +2mm**：`+2/-2.5/+2.5` ≠ 开运算，开运算必须 **±同值净零** → 带宽 9.5→13.5mm、扇形接口外鼓 2mm；
2. **锯齿 L308（表面装饰，X 振幅 ±5mm 超出带体）被并进外环** → 右端成斜刺/乱齿；
3. 末端是 CAD 斜切倒角 → 没有竖直末端边可粘合。

**修法**（`tabs_extract.py` HORIZ 分支）：
1. 主轮廓线 = 区域**最长线闭合成环**（L305）= 干净拉带体；右端**补竖直边**（末端 10mm 带填满）；
2. 其余线缓冲并集 → 填洞 → **±2 开运算**：4mm 厚装饰带（锯齿/缝线/挂刺）全被腐蚀掉，只剩实体扇形接口；
3. 两者并集（在带体左端自然重叠连通）。

**铁律**：锯齿/缝线/挂刺是**表面装饰，绝不上轮廓**（参考模型 R8 带体 z947–957 干净无锯齿）。

## P32 · 密集装饰弧的包络近似 + 5mm 网格 ⇒ simplify 容差要放到 2mm ★

**现象**：扇形接口（110 条密集扇贝弧）包络里有 1.3–2.9mm 微锯齿边，
5mm automesh 忠实照扫 → 产出 6 条 <3mm 单元边（公司规范 2.2 硬条款：最小单元尺寸 >3mm）。

**修法**：HORIZ 区域 `simplify(2.0)`（其它区域仍 0.4）。12 点外环、最小边 5.88mm，
网格最小边 3.68mm、R8 短边 97→0。连接关键几何（末端竖边/带体直边）是 90° 角，
simplify 只删点不移动点，完全不受影响。

**推广**：任何"密集弧/齿的包络近似"都要过一遍**最小边长门禁**（≥3.5mm），
再进网格；别等网格出来查短边。

## P33 · 2026 hmbatch 里 `*createentity elems` 建不出元素 ★★

**现象**（2026-10-20 写冒烟测试实测）：`*createentity elems id=7001 config=quad4 propertyid=9001 nodes="8001 8002 8003 8004"`
报 `Invalid element config specified`；换 config 名（quad/shell/tria3/CQUAD4…）全失败；
`collector=` / `propertyid=` / `mark=` 参数报 `data-name not valid`；
且 `*createentity nodes id=8001 ...` 建的节点 `*createmark nodes 1 "by id" 8001` **查不回（mark=0）**。

**结论**：2026 hmbatch 里 `*createentity` 只能建 comps，**建元素/可靠节点必须走 automesh
或 GUI/MCP bridge**。记忆里"`*createentity elems config=quad4 propertyid=$pid nodes="1 2 3 4"`"
是 **MCP live bridge（GUI 内 Python API）** 的用法，不是 hmbatch 的。
→ 批处理链建元素只有一条路：spline 建面 → automesh。冒烟测试（smoke_2026.tcl）据此只测真实操作。

## P34 · 2026 hmbatch automesh 静默出 0 元素：必须先设两个全局开关 ★★★

**现象**：spline 面建成功，`*automesh 0 2 2` 报
`Internal mesh error, try modifying element densities`，**catch 得住、不崩**，
但元素数 0 —— 后续按 surface 导元素全空， deck 悄悄变空。

**修法**：`*readfile` **之后**、automesh **之前**：
```tcl
*elementorder 1
*setedgedensitylinkwithaspectratio -1
```
build_step1_2026.tcl / build_tabs_2026.tcl 均已带（2026-10-20 实测 cab1  Belt 面 18,153 元素）。

**注意顺序**：这两个开关放在 `*readfile` **之前**会触发
`Invalid interactive routine called while in batch mode`（FatalError，不可 catch）→ 整脚本毙。

---

## P35 · hmbatch 把线搬进 component：`*movemark` 第三参是 **comp 名称**，不是 id ★★

NEW_CAB 四分区落地实测（2026-10-21）：

| 写法 | 结果 |
|---|---|
| `*movemark lines 1 BELT` | ✅ 成功（第三参 = collector **名字**） |
| `*movemark lines 1 2`（传 id） | ❌ `Components specified not found in model` |
| `*movemark lines 1 comps 2`（传 mark） | ❌ 同上 |
| `*collectormarkmove lines 1 2` | ❌ `Lines are not a valid data type for this function`（只收 FE 实体） |
| `*renamecollectorbyid comps 1 BELT` | ⚠️ 返回 0 看似成功，comp 名字却变成 **"11"** → **不可信，别用** |

**正解**（建 comp 只认 `*createentity comps name=X`，自动分配 id 2,3,4…）：
```tcl
*createentity comps name=BELT
*createmark lines 1 "by id" 1 2 3 ...      ;# 每 100 个 id 一块，防命令行过长
*movemark lines 1 BELT
```
**校验**（必须做，防 mark 语义坑）：`*createmark lines 1 "by collector name" BELT` +
`hm_getmark` 拿回 id 列表，`lsort -integer` 与分类真值（json）逐 id 比对，不是只比条数。

**另**：`*writefile` 目标文件**已存在**时会弹 `Overwrite? (y/n)` →
hmbatch 里变成 `Invalid interactive routine called while in batch mode`（**FatalError，不可 catch**）
→ 写盘前必须 `file delete -force $target`。

## P36 · 环链追踪的切线连续判据：必须看**端点类型配对** ★★

两条线 X（端点 E）与 Y（端点 F）续接光滑的充要条件是：
`(E=="ep") != (F=="ep")` → dot ≈ **+1**；否则 dot ≈ **−1**。
即"首接尾/尾接首"才同向。**只查 `dot < −0.985` 是有偏的**，会漏掉一半搭接
（NEW_CAB 实测：L762 dot=+1 是布带右缘补段；整族气腔底边/右腰碎片全因此漏掉）。

配套：链追踪的候选过滤要用**线 id**（`c[1]`）判重，不是距离（`c[0]`）——
用距离会 A→B→A 无限振荡（trace_full.py 踩过）。

## P37 · IGS 缝线"两头圆圈"是**多段弧拼的**，端点分析会误判成 V/方头 ★★

NEW_CAB 实证：缝线带端头的 L27/L103/L20/L28 都是 **33 点弧线**（折线弯曲），
端点邻接看是"V/方头"，实际是**半圆**；整条缝线 = 半圆端 + 5mm 窄带 + 圆端 = 哑铃。

- **自闭合单线搜索只能找到单线圆**（如 L820/L821 革眼）；多段弧圆必须查**折线曲率**。
- **气腔底部会挂水滴**（圆头+茎连到腔体边界，茎是气腔环的一部分，别当独立碎片）。
- **充气口可能与气腔共边界**：口的内壁起点 = 气腔顶边缺口端点（NEW_CAB 410mm 缺口是图纸固有，
  搬任何线都补不上，别为"闭环"硬凑）。
- **坐标平面不一定是 X-Z**：cab1 在 XZ，NEW_CAB 在 **XY** → 导出脚本必须输出 xyz 三轴。

## P38 · Tcl 双引号内 `[` 是命令替换；`puts` 不做格式化 ★

```tcl
log [format "bbox x %.3f .. %.3f" $a $b]   ;# ✓ format 包一层，且格式串里不放 [ ]
log "bbox x[%.3f]" $a                       ;# ✗ ① puts 不格式化 ② [ 被当命令替换
                                                ;#   → invalid command name "%.3f"
```
`proc log {m} {...}` 只收一个参数，多传的 `$a $b` 直接丢；
且双引号内 `[...]` 会当命令执行——格式串要方括号就 `\[` 转义或干脆不用。

---

## P39 · NEW_CAB 凸台矩形环漏编：足印环必须逐一核对落入"带体"层 ★NEW_CAB

NEW_CAB 实测（2026-10-22）：x1483 凸台的 8 线足印 `[550,551,552,553,554,555,556,525]`
初版漏编进 `TETHER_COMPS2` → 穹顶失去宿主悬空，被误保留成浮层。
**教训**：凸台足印环不能只看"总数对不对"，要逐一核对是否落入正确的"带体"层；
足印清单（`assets/ringdef_newcab.json`）必须覆盖所有**存活**凸台，包括被拆片但几何仍属足印的线。
自检由 `gen_ring_spec.py` 从 `ringdef_*.json` 生成，漏一条足印 → 该环对拍直接 FAIL（P41 的由来）。

## P40 · NEW_CAB 拉带连接对齐规则（用户 2026-10-21 确认）★NEW_CAB

- **凸台（tab*_up/dn）** = 顶帽边一条**水平线**（EDGE_BAND=8mm，平行布带长度方向）。
- **左区长拉带（tabc*/tabh*）** = **末端竖边**一条**竖线**（END_BAND=3mm，垂直布带长度方向）；
  用户原话"啮合点在拉带顶端，粘合线垂直于布带的长度方向"。
- 详见 `07_tab_tether_meshing.md` §5.1 拓扑实证 + `tether_conn_check.py`（band 软校验）。

## P41 · 仅靠 QA 拓扑门禁查不出"几何和 CAD 曲线一致与否"——必须逐环对拍 ★本轮沉淀

NEW_CAB 出现 "x1483 凸台矩形环漏编→穹顶悬空" 与 "整环面积翻倍/边界漂移" 类错误。
QA 只查拓扑合法性（eid 唯一/无退化/无自由边），**不查空间几何是否和 CAD 曲线一致**。
→ 新增 `geom_match_check.py`：把每条 CAD 环的几何（质心/面积/形状）与它在网格里的实现（选出的单元集）
逐项对拍，全 FAIL 即说明某环几何没对上 CAD。

## P42 · 自检"链条成多边形"不可取——改用点云凸包 + 最近点边界偏差 ★本轮沉淀

早期把 IGES 线段贪心串成环 → 凸台环串成**蝴蝶结自交多边形**（面积 3515 vs 真实 ~4500）。
改用：① IGES 区域用**点云凸包**（凸环精确、凹环为上界）；② 边界用**最近点查询**
（IGES 采样点到最近网格节点、网格自由边中点到最近 IGES 点）。
**BELT/CAVITY 是环面（带洞）**，单凸包面积无意义 → 这些环 `area_check=false`，只查边界贴合 + 位置。

## P43 · 自检选单元前必须按 PID（层）过滤，否则重叠层误选 ★本轮沉淀

NEW_CAB 的 tether(Y=-1) 与 belt(Y=0) 在 2D X-Z 平面**完全重叠**（tether 是 belt 上的孔）。
纯 2D 选单元会把两层都选入 → 面积翻倍、边界错乱。
→ `geom_match_check.py` 的 `main()` 按 `type2pid`/`mesh_pid`（belt=2/cav=3/seam=4/boss=5）
**先过滤 elems 子集再 check**；`--rings` 里每个环带 `mesh_pid` 字段。

## P44 · 位置判据必须用"节点凸包质心"，不能用面积加权质心 ★本轮沉淀

belt 是条带，面积加权质心沿条带偏移 **121mm**，而凸包质心 = 包围盒中心。
对环面/条带，位置判据改用 **mesh 节点凸包质心** vs **IGES 凸包质心**（两者均≈几何中心，差值≈0）。
boss 等凸实环两者也近似相等，统一用凸包质心即可。

## P45 · 边界判据方向：主判据是 CAD→mesh，不是 mesh→CAD ★本轮沉淀

`mesh自由边→CAD` 在环面开口处天然偏大（哨兵 1e18），不能判 FAIL；
**主判据**应是 `CAD点→最近网格节点`（确认网格是否覆盖 CAD 曲线），`mesh→CAD` 仅作 WARN。
cavity 充气口是**图纸固有开口**（410mm 缺口，x537–926，用户明确"不封闭也没关系"）→
cavity 边界容差 `bnd_tol` 放宽到 **15mm**（per-ring 覆盖），否则误 FAIL。

## P46 · boss 面积比 >1 是拉带垫料外延（正常）——面积判据须单侧 ★本轮沉淀

boss 足印是 CAD 孔洞，网格是绕孔的拉带垫料，面积比 1.06–1.17（mesh > CAD）属正常。
→ 面积判据**单侧**：`ratio < 1-atol`（网格小于 CAD，漏网格）→ FAIL；
`ratio > 1+atol`（网格更大，垫料外延）→ 仅 WARN 不 FAIL。atol 默认 0.15。

## P47 · 坐标映射 map=xy：图纸 X=模型X，图纸 Y=模型Z ★本轮沉淀

NEW_CAB 的 IGS 在 **XY 平面**导出（z=0），但模型层沿 **Y**（belt Y0 / cav Y±0.5 / tether Y-1）。
自检/连接脚本统一 `--map xy`：节点 (x, y, z) → (x, z)，与 IGES 点云 (X, Y_draw) 同坐标系。
（cab1 在 XZ 平面则同样用 xy 映射，因为两者都是"图纸x→模型x，图纸y→模型z"。）

---

# 第二批坑位（P48–P60）：cab2 实测，2026-11-01

> 这一批全部来自 cab2 气帘（HyperMesh 2026 + case.json 驱动）连续五版迭代（v3→v8）。
> 共同特征：**错误发生时流程不报错**——静默降级、只看数字不看组分、
> 显式节点替代拓扑约束。所以前四条都是"防静默"。

## P48 · 组装阶段缺件只打 WARN → 整块拉带静默丢失（★代价最大）★cab2

**现象**：`cab2 v4` 整块丢掉侧面拉带（196 单元 / 2354mm² / 位于 X 1683, Y 172）。
交付后 **五项门禁全 PASS**：K 校验 0/0、质量不合格 0.09%、连接三性质 PASS、
auto_gate PASS 3/WARN 2、anchor_metric PASS。**没有任何一项报警。**

**根因**：`assemble_cab2.py` 找不到 `out/cab2_step2b_side2.txt` 时只打一行
```
WARN 缺 step2b 侧面拉带, 本次不含
```
然后继续组装。丢的是**整个连通组分**，不是错单元，所以：
- 质量门禁：少了 196 个单元，不合格率反而**更低**
- 连接检查：剩下的 8 块拉带每块都合格
- 组分检查：`tether_conn_check` 是**逐块**判定，不会问"应该有几块"

**修法（已落地）**：
1. `case.json` 增 `parts` 字段声明必需部件（`["belt","cavity","seam","tether","side"]`）；
2. `assemble_cab2.py` 读 `REQUIRE_PARTS`，缺 `side` 直接 `SystemExit`，不再只 WARN；
3. 新增 `gate/partition_cover_check.py`，按 PID 比对**组分个数 + 逐块面积 + 质心**；
4. `run_case.sh` ⑦d 接这道门禁，退出码 2 = 不要交付。

**教训（推广到所有案例）**：
> **"缺省降级"在交付链里是 bug，不是宽容。**
> 凡是"找不到就跳过"的分支，都要能升级成硬失败，并且由案例声明是否需要。

---

## P49 · `out/` 被清空 → 中间产物全失效，但脚本按缺省文件名静默降级 ★cab2

上游：`out/` 目录被清空（原因未确认，可能是清理临时文件）。后果不是"报错"，而是
一连串"看起来正常"的降级：`lines_pts.txt` 没了 → 若 `SKIP_LINES=1` 就用旧路径失败；
`cab2_step2b_side2.txt` 没了 → 走 P48 的 WARN 分支。

**规约**：
- 中间产物**永远只在 `out/`**，不跨目录引用；`out/` 一旦清空必须**整链重跑**，
  不能用 `SKIP_LINES` / `GATE_ONLY` 拼凑（此时门禁查的是不完整模型）。
- 关键中间产物清单（丢掉任何一个都要重跑对应阶段）：
  `lines_pts.txt` → `loops.json` → `step1_gen.tcl` → `<case>_step1_bl.txt`
  → `tabs*.txt` → `<case>_step2b_side*.txt` → `anchors.json` → `tabs_anchored_export.txt`
- 每个阶段开头打印**它读的文件全路径**（`assemble_cab2.py` 已加 `主拉带:` / `侧面拉带:` 两行），
  出问题第一眼看这两行。

---

## P50 · 「显式节点序列」控制不了配对行平行 —— 锚固整齐是拓扑性质 ★cab2 v8

用户点名要试的方案 A（把锚固链的点建成边上固定节点，再保形划网格），做了三代：
`polyline`（折线）/ `band`（折线偏置成带）/ `hybrid`（折线 + 两端补刀），
同一批 8 条锚固链对跑，结果全部输给三刀切：

| 模式 | 过渡排宽 mm | 上下边错位 σ | 翘曲 max | <3mm 短边 |
|---|---|---|---|---|
| **triple 三刀切** | **5.00** | **0.03** | **32.97°** | 235 |
| polyline | 4.36~5.95 | 0.41 | **81.88°** | 188 |
| band | 4.18~5.32 | 0.08 | **81.59°** | 256 |
| hybrid | 3.76~5.84 | 0.37 | **78.10°** | — |

**根因（定论）**：显式节点只保证"锚固点落在该落的位置"，**控制不了 automesh 在锚固线
内侧按哪条主方向布配对行**。行不平行 → 单元成梯形 → 翘曲从 33° 涨到 78~82°。
三刀切之所以齐，是因为它切出一块**矩形锚固带**：中间块宽度 = 锚固段长度（被 5mm 整除），
边上的节点天生就是锚固点。**这是拓扑性质，不是坐标性质。**

**配套死路**（HM2026 实测，别再试）：
`*surfaceaddnodesfixed`（所有参数形式都 r=1，报 `Distance between nodes must exceed
node tolerance` / `Invalid ordered list id found in file`）、`*surfaceaddpointsfixed`、
`*surfaceaddpoint`（假成功，节点没上去）。

**唯一正收益**：顶角窄条 235→188（折线自己替掉了竖切弦）。若某案例窄条是主要矛盾，
可以局部混用；否则一律 `--mode triple`。

> 留了 `--mode` 四选项可复现，别再重新发明。

---

## P51 · 三刀切的线必须**贯穿面**，面内短线报 `Selected lines do not form a combined curve` ★cab2

`*surfacemarksplitwithlines 1 2 0 13 0`（surf mark / line mark）要求每条切线把面**从一侧切到另一侧**。
过锚固链端点沿法向的竖切、沿链方向的纵切，三条都必须贯穿。
面内短线段（想只切局部）→ r=1，报 `Selected lines do not form a combined curve`。
只横切一刀：中间块宽 5.137mm、累积偏差 1.7mm；拆成 5mm 分段短线：公共端点两套节点、网格不连续。

---

## P52 · 锚固链端点必须 `trim_chain`：落面外被截短、贴轮廓出薄条 ★cab2

两个反向坑，同时存在：
- 链端点在面**外** → 中间块被轮廓截短，间距 5.00 → **4.73**；
- 端点距轮廓仅 0.2~0.5mm → 生成薄条 + **78° 扭转片**。

修法：`gen_tabs_anchored.py::trim_chain()` 先把链裁到面内，再把"贴轮廓"的端点沿端段方向
**外推到凸台边界**。**外推阈值只能 0.6mm**：放到 2.5mm 时块 0 端点 1.47mm 被推走，
6 个锚固点只剩 3 个能配。

> `trim_chain()` 曾经在技能版重写时丢掉，导致三刀切间距从 5.00 退回 4.73。
> **改这个脚本必须跑回归**（见 P60）。

---

## P53 · `WEAK_ANCHOR_MIN` 默认 8 会误伤凸台；内部锚固块要设 1 ★cab2

侧面拉带是"缝在布带内部"的，根部 47.8mm 与布带重叠，**不在布带自由边界上**，
`plan_anchors.py` 拿不到锚点 → 组装阶段走"布带内部锚固"二次焊接，靠 `SNAP_INSIDE_TOL=3.0` 生效。

但 `WEAK_ANCHOR_MIN=8`（默认）的语义是"外边界锚点少于 8 个就重做内部焊接"：
6 个凸台有 6~7 个外边界锚点，也被判成弱锚 → 节点被推开 3mm、最小角 p1 掉。

**定版 `WEAK_ANCHOR_MIN=1`**：只有"0 个外边界锚点"的侧条走内部锚固。
结果 `tether∩belt = 77`（58 外边界 + 19 内部）。

**判据**：如果某块拉带有 1~7 个外边界锚点，它**不该**被二次焊接；设 1 即可。

---

## P54 · `STEP2/STEP2B` 只给文件名，别带 `out/` 前缀 ★cab2

组装脚本会把相对路径拼成 `<WORKDIR>/out/<basename>`。给 `STEP2=out/xxx.txt` 会变成
`.../out/out/xxx.txt` → 报"缺主拉带网格"。

**正确**：`STEP2=tabs_triple_export.txt`。
（已改成 basename 兼容，但 case.json 里就按文件名写，别赌。）

**同时**：`STEP1` 的解析路径和 `STEP2` 不同（STEP1 允许 `out/` 前缀），两个脚本不要混用习惯。

---

## P55 · 两个脚本的参数形式不同：`partition_cover_check` 要 `--k`；`run_gate.py --case` 不能给绝对路径 ★本机

- `partition_cover_check.py` 的 deck 是**必需选项** `--k`，不是位置参数。位置给会被 argparse 拒。
- `run_gate.py --case E:/...` 在本机跑会被 **SIGTERM**（约 60s 时被杀，疑似沙箱路径规则）。
  用**相对路径** `--case cases/cab2/gate_case_v8.json`，并 `run_in_background=true`
  + 重定向日志，2 分 1 秒跑完 rc=0。

---

## P56 · HM2026 `hm_nodevalue` 返回 `{x y z}` 花括号串 ★cab2

```tcl
set vv [hm_nodevalue $nd]                  ;# 实际是 "{1.0 2.0 0.0}"
set parts [split [string trim [string map {"{" "" "}" ""} $vv]] " "]
```
不处理的话 `llength` 判成 1，`lindex` 取空串 → `can't use empty string as operand of "-"`。
`hm_getmaxid` 在 2026 不存在，用 `hm_entitymaxid`；`*createnode` 返回的 id ≠ maxid+1，
要用 `[hm_entitymaxid nodes]` 重新取。

---

## P57 · `*elementorder` / `*setedgedensitylinkwithaspectratio` 必须在 `*readfile` 之后 ★cab2

写在前面会被 `*readfile` 重置，automesh 出来的网格尺寸不受控。
**顺序**：`hm_framework loaduserprofile ...` → `*readfile` → 建/取面 → `*elementorder 1`
→ `*setedgedensitylinkwithaspectratio -1` → 每面 `*interactiveremeshsurf 1 $sz 2 2 2 1 1`
紧跟 `*automesh 0 2 2` → `*storemeshtodatabase 1`。

---

## P58 · 拉带扁平区共线 → 66 个"不合格"单元其实是退化几何，不是网格错误 ★cab2

PID5 里 66 个不合格单元全部集中在拉带的**扁平直线段**：四点共线 → 最小角 0°、面积 0。
这是 CAD 轮廓本身退化，网格再完美也修不掉。

**口径**：这类单元**保留不删**（P18 硬规矩：不准乱删），在交付报告里单列说明。
`mesh_quality_gate.py` 把它们计入"不合格率"，cab2 v8 是 82/83808 = 0.10%，远低于 5% 门槛。

**不要做的事**：为了让数字好看去删这 66 个单元 —— 会产生自由边（P18）。

---

## P59 · 内联 Python 解析 K 必须先跳过 `$#` 注释行 ★本机

LS-DYNA K 的 `*NODE` / `*ELEMENT_SHELL` 块里有 `$#` 表头注释行（HyperMesh 导出的格式）。
`int(f[0])` 直接崩 `invalid literal for int(): '$#'`。
过滤 `line.strip().startswith('$')` 再解析。

---

## P60 · 改技能脚本必须做 **MD5 回归**（本条是元教训）★cab2

本轮重写 `gen_tabs_anchored.py` 时丢了 `trim_chain()`，三刀切间距从 5.000 退回 4.73，
**没有任何门禁报警**（质量仍 0.09%、连接仍 PASS）。是拿侧视图逐块量出来的。

**规约：技能里任何一个被 cab2 验证过的脚本，改动后必须重跑全链并比对 MD5。**
```bash
bash scripts/drivers/run_case.sh --case cases/cab2/case.json --work /path/to/cab2
md5sum out/curtain_airbag.k   # 必须与 onekey/cab2_curtain_airbag_v8.k 一致
# d8e50902f4a41e8029ba87eb502f18d5
```
2026-11-01 的组装硬化（`REQUIRE_PARTS` / STEP2 命名 / case.json 参数化）就是按这条验的：
MD5 **完全相同**，才允许认为"重构没改行为"。

> 推论：**任何"看起来等价"的重构都不可信，只有 MD5 相同才可信。**
