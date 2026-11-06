# 02 · 切线搭接判据（核心算法）

> 本技能找"跨类桥接候选线"的唯一数学依据。NEW_CAB 第一次扫描栽在
> "只查 dot<−0.985"上，漏掉一半搭接，用户一眼看出分类错误。

## 1. 数学

两条线 X（端点 E∈{sp,ep}）和 Y（端点 F∈{sp,ep}）平滑搭接的充要条件：

```
端点距离:  |X@E − Y@F| < TOL (NEW_CAB 用 8mm, IGS 断点最大 ~7mm)
切线同向:  (E=='ep') != (F=='ep')  ->  dot(t_X@E, t_Y@F) ≈ +1
           (E=='ep') == (F=='ep')  ->  dot(t_X@E, t_Y@F) ≈ -1
```

直觉：沿 X 走到端点 E 时，若 E 是 X 的终点（ep），要继续走就必须进入 Y 的
起点（sp）——两条线在接点处"首尾相接"，切线同向 dot≈+1。若两个端点同类型
（都是 ep 或都是 sp），接点处两条线"背靠背"，切线反向 dot≈−1。

**错误判据**（v6 用过的）：无条件要求 `dot < −0.985`。
→ 漏掉所有"ep-sp 型"搭接（dot≈+1 的那些）。NEW_CAB 的 L762 和气腔底边
一族就是这么漏的。

## 2. 代码（p03_bridge_scan.py 核心）

```python
TOL = 8.0
def smooth(lid, end, o, oe):
    """lid@end 与 o@oe 是否平滑搭接"""
    e = feat[lid][end]; p = feat[o][oe]
    if abs(e[0]-p[0]) > TOL or abs(e[1]-p[1]) > TOL:
        return False
    mine = feat[lid]["ts"] if end == "sp" else feat[lid]["te"]
    tt   = feat[o]["ts"]   if oe  == "sp" else feat[o]["te"]
    dot = mine[0]*tt[0] + mine[1]*tt[1]
    expect = 1.0 if (end == "ep") != (oe == "ep") else -1.0
    return abs(dot - expect) < 0.02
```

**桥接候选线** = A 类线，其**两端**都平滑搭接到 B 类线（同一类 B）：
极可能是 B 的环碎片误分进 A。输出形如：

```
L762 [TETHER] L=  20.22  bridges -> [BELT]  sp: L763; ep: L764
```

## 3. 单链追踪（p03b_trace_chain.py）

从种子线一端出发，每步取"距离最近且切线连续（dot≈−1 或 +1 按类型）"的
下一跳，输出有序链 + 每处 gap。用于回答"这条碎片到底属于哪个环"。

NEW_CAB 实例：L91.sp 切向 (−0.267,−0.963) 与 L92.ep (0.267,0.964) 正好相反，
且 L91.ep 与 L29.sp 坐标 1e−6 级重合 → L91 是气腔右缘链的一环。

## 4. 数据来源

`out/geom_features.txt`（t01_export_geom.tcl 用 HM 原生几何函数导出）：

```
LINE <id> <length> | <sp x y z> | <ep x y z> | <ts x y z> | <te x y z>
JUNC <id1> <id2> <angle>        # 端点 <1.5mm 匹配的两线夹角
CIRC <id> | <p0> | <mid> | <p1> | <circle_fit>   # 三点圆拟合(弧判定用)
```

解析时 sp/ep/ts/te 只取前两维（x,y）——坐标平面可能是 X-Y 不是 X-Z（P42）。

## 5. 端点半影容差

IGS 曲线有断点，端点焊接容差取 **8mm**（NEW_CAB 实测最大 ~7mm）。
容差太小会漏搭接，太大会把相邻平行线误连。换项目先用
`dangling` 分析（p04 的 QA 段会输出每个悬挂端最近的同类线距离）校准。
