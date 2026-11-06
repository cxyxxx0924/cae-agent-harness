# 04 · 实战案例：NEW_CAB 四分区（2026-10-21）

> `Drawing0904ZHEDIETU.iges`，828 条线，IGS 导入后 1 个 comp（lines0）。
> 终态：BELT 119 / CAVITY 78 / SEAM 59 / TETHER 572 → `newcab_partitioned.hm`。
> 工作区：`E:/work/AI_CAB/onekey/work/newcab`（中性名副本 =
> skill 标准命名，见 SKILL.md §3）。

## 1. 几何全貌

- 坐标平面 **X-Y**（z≡0，P42）——不是 cab1 的 X-Z
- 布带 x[−365.2,1620.2] y[−167.0,497.4]；气腔 x[−350.7,1579.3] y[−152.6,357.4]
- 充气口领圈 x 537–926，从 y=357.45 升到 y=497.37：
  外壁 L470(14°)→L189(28°)→L249(rim)→右侧锯齿 L196/L188/L187/L195/L194/L193/L192/L191/L250/L135；
  内壁 L166→L471→L134，起点 = 气腔顶边缺口左端 (478.11, 357.45)
- 气腔顶边缺口 410mm（x 478→888）——图纸固有
- 7 凸台跨布带顶边，x≈ −275/−5/283/489/962/1275/1483，城堡状带肩栈
- 气腔底部 7 个水滴；缝线 4 哑铃 + 充气口气道缝；左 2 革眼（40mm 圆+十字）；
  右梯带（双轨+锯齿缝+末端扣具 x 1572–1771）+ 右矩形补丁（跨布带右缘）
- IGS 导出有**重复线**（HyperMesh 导出artifact）：如 L233/L237/L241/L245 是同一条
  25.64mm 线，L234/L238/L242/L246 是同一条 20.94mm 线——缝线组分里看到"重复段"不是bug

## 2. 版本演进（v1→v8）

| 版本 | 动作 | 结果 |
|---|---|---|
| v1–v5 | 种子分类（bbox + 区域规则 + 端点连通） | 凸台/革眼/补丁对；**充气口+水滴源头误入 TETHER**（用户一眼看出） |
| v6 | 首次切线扫描 | **判据有偏**（只查 dot<−0.985）→ 漏 L762 和气腔底边一族 |
| v7 | 修正判据（端点类型配对）+ 追踪 L91/L163 | BELT 119 / CAVITY 71 / SEAM 58 / TETHER 580 |
| v8 | bridge_scan 全量 + 12 条修正 + 渲染复核 | **BELT 119 / CAVITY 78 / SEAM 59 / TETHER 572** ✓ |

## 3. v8 修正清单（12 条，全部由 bridge_scan 找出）

| 线 | 原类 → 新类 | 依据 |
|---|---|---|
| L130 / L95 / L93 | TETHER → CAVITY | 气腔底边三段，全在 y=−152.554 直线上 |
| L69 / L66 / L70 | TETHER → CAVITY | 气腔右腰链 L65→L69→L66→L70→L67，平滑 0 缝隙 |
| L68 | TETHER → CAVITY | 气腔右上角碎片 L72→L68→L30 |
| L91 | TETHER → CAVITY | L91.ep 与 L29.sp 坐标 1e−6 重合；L91.sp 切向与 L92.ep 正好相反 |
| L762 | TETHER → BELT | 布带右缘 20.22mm 缺口补段，与 L763/L764 切线连续（dot=+1） |
| L163 / L205 | BELT/CAVITY → SEAM | 缝线通道内 1–2mm 小连接段 |

## 4. 渲染复核（每版必做）

- `out/v_partition.png`：4 面板（BELT 红 / CAVITY 蓝 / SEAM 绿 / TETHER 橙）
- `out/v_partition_all.png`：总览
- 局部 zoom：右上凸台区、右缘梯带（x 1572–1771，确认是 TETHER 连通体）、
  缝线左半（确认端头是多段弧拼的半圆）
- 缝线闭环 QA：4 哑铃全部 0 悬挂端（q09_seam_check.py）

## 5. 落地与校验（双重，不靠自说自话）

**搬移时**（t07_make_comps.tcl）：
- 新建 4 comp → `*createmark lines 1 "by id"` + `*movemark lines 1 <comp名>`
- 逐 comp 用 `by collector name` 拿回 id 集合，与 class_lists.tcl **逐一比对**
- lines0 残留 0；ALL_OK=1

**回读时**（t08_verify_partitioned.tcl，独立脚本不复用写入假设）：
- 重新 `*readfile` → 逐 comp 数线（119/78/59/572=828）+ 从线端点算 bbox
- cross-check：by collector name vs by id 双路计数一致
- 抽样线长/端点与分区前 `geom_features.txt` 逐位一致（L766/L209/L169/L2…）

**skill 回归**（2026-10-21，用本目录脚本重跑全链）：
p05/p06/q09 重跑 counts 逐位重现；t07 重搬 id 集合一致；t08 VERIFY_FAIL=0。
skill 生成的 `partitioned.hm` 与原交付 `newcab_partitioned.hm` 语义等价
（二进制头部字节差是 hm 格式内嵌会话元数据；几何等价由 t08 抽样线长逐位一致保证）。

## 6. 踩坑记录（本案例独有）

1. **切线判据只查 dot<−0.985** → 漏一半搭接。判据必须按端点类型配对（P36）
2. **把端点追踪的"V 头"当缝线端头形状** → 实际是多段弧拼的半圆（P37），
   查 CIRC 三点圆拟合才确认
3. **`*readfile` 失败背锅中文路径** → 真相是目标文件不存在，hmbatch 整体中止、
   报告不生成，看到旧报告 VERIFY_FAIL=0 以为成功（P39/P40）。
   教训：**定位错误先读错误栈，别归因于传说**
4. IGS 重复线 → 不是 bug，是导出 artifact；分类时按原样保留
5. 凸台 shoulder stacks 一度想删 → 属于已确认 TETHER 凸台，保留；
   BELT 顶边 9–52mm 缺口留给网格阶段桥接

## 7. 遗留（图纸固有，非缺陷）

- 气腔顶边充气口根部 410mm 缺口
- 凸台区 19 / 布带 22 / 气腔 20 条既有短边 <3mm（与连接修复无关）
- 下一步（未开始）：`partitioned.hm` → 裁切拓扑建面 → automesh → Y 分层 → K → 门禁
  （在 hypermesh2026-curve-to-mesh 技能）
