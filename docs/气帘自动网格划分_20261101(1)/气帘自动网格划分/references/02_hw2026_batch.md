# 02 · 2026 hmbatch 铁律与命令签名速查

> 全部经 2026.0.0.27 实测。标 ★ 的是 2026 特有（2020 不同或不存在）。

---

## 1. ★ 开头必须加载用户模板

```tcl
hm_framework loaduserprofile LsDyna Keyword971_R16.0
```

**不写的后果**：任何创建实体都报
```
No user profile or template file loaded
data-name "pid" is not valid
```
**只写 `loaduserprofile LsDyna`（不带版本号）无效** —— 它只定位目录，
不会解析出模板文件。必须带 `Keyword971_R16.0` 这样的子版本。

稳妥写法（多档回落）：
```tcl
foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}
```
判据：`[hm_info templatefilename]` 非空。
2026 正确解析结果：`.../templates/feoutput/ls-dyna971/dyna.key`

**2020 不需要这一句**——这是 2026 独有的坑。

---

## 2. ★ 查询类命令变化

```tcl
# 没有 hm_entitycount！改用 mark
*createmark elems 1 "all" ; set n [llength [hm_getmark elems 1]]

# 取某 collector 下的实体
*createmark lines 1 "by collector" $comp_id
set lns [hm_getmark lines 1]

# 当前最大 id（用来识别"新建了什么"）
set i0 [hm_entitymaxid surfaces]
...建面...
*createmark surfaces 1 all
foreach s [hm_getmark surfaces 1] { if {$s > $i0} { lappend new $s } }
```

| 目的 | 命令 |
|---|---|
| 实体计数 | `*createmark X 1 "all"` + `hm_getmark` |
| 标记数量 | `hm_marklength X 1` |
| 最大 id | `hm_entitymaxid X` |
| 属性值 | `hm_getvalue Xs id=$id dataname=name` |
| 模板 | `hm_info templatefilename`、`hm_info -appinfo SPECIFIEDPATH TEMPLATES_DIR` |

---

## 3. 建实体数据名变化（⚠ 2026 hmbatch 实测：`*createentity elems` 不可用，见 P33）

```tcl
*createentity elems config=quad4 propertyid=$pid nodes="1 2 3 4"   ;# 仅 MCP live bridge (GUI Python API) 有效
```
| 2020 | 2026 |
|---|---|
| `pid=...` | **`propertyid=...`** |
| `nodeid1=1 nodeid2=2 nodeid3=3 nodeid4=4` | **`nodes="1 2 3 4"`** |

**2026-10-20 hmbatch 实证（P33）**：上述 `*createentity elems` 在 hmbatch 报
`Invalid element config specified`；`collector=`/`propertyid=`/`mark=` 参数报 data-name not valid；
`*createentity nodes` 建的节点 mark 查不回。→ **hmbatch 批处理建元素只有一条路：
spline 建面 → automesh**（P34：automesh 前必须先 `*elementorder 1` +
`*setedgedensitylinkwithaspectratio -1`，且在 `*readfile` 之后）。

---

## 4. 曲线采样与量测（几何调查必用）

```tcl
set L    [hm_linelength $ln]                       ;# 线长
set sp   [hm_getlinestartpoint $ln]                ;# 起点 {x y z}
set ep   [hm_getlineendpoint $ln]                  ;# 终点
set type [hm_getlinetype $ln]                      ;# composite 判定 ★关键

# ★ 采样（返回嵌套列表，必须解包）
set r [catch {hm_getcoordinatesofpointsonline $ln $u} v]   ;# u ∈ [0,1]
set vv $v
while {[llength $vv] == 1 && [llength [lindex $vv 0]] >= 3} { set vv [lindex $vv 0] }
lassign $vv x y z
```

**两个陷阱**：
- `hm_getcoordinatesofpointsonline` 返回 `{{x y z}}`（**包了一层**），
  直接 `lindex $v 0` 拿到的是整个坐标串，必须 while 解包。
- `hm_getlinepointsatdistance line d x y z` 是 **5 参数、按弦长**取点，
  且 **d=0.0 会卡死**（hmbatch 挂起不返回）。采样一律用 u∈[0,1] 那条。

**采样+渲染标准底图是几何调查的标准动作**——不要靠"自动识别"猜环的语义，
先出图，人来看，再按坐标做空间匹配。

---

## 5. 建面 / 裁切 / 拆线

```tcl
# spline 面（从选中的线环）
*createmark lines 1 $first
foreach id [lrange $lns 1 end] { *appendmark lines 1 $id }
*surfacesplineonlinesloop 1 1 0 1

# 面面积
set a [hm_getareaofsurface surfaces $sid]

# ★ 从面边缘提取普通线（绕开 composite 的唯一可靠手段）
*createmark surfaces 1 $sid
*linefromsurfedgecomp surfaces 1 1

# ★ 裁切（surfaces mark=1, lines mark=2）
*createmark surfaces 1 $target
*createmark lines 2 {*}$tool_lines
*surfacemarksplitwithlines 1 2 0 13 0

# ★ 拆线（参数是【节点 id】，不是坐标）
*createnode $x 0 $z 0 0 0
set nid [hm_entitymaxid nodes]
*linesplitatpoint $ln $nid

# ★ 两节点建线（必须先 createlist）
*createnode $x1 0 $z1 0 0 0
*createnode $x2 0 $z2 0 0 0
set n0 [hm_entitymaxid nodes]
*createlist nodes 1 [expr {$n0-1}] [expr {$n0}]
*linecreatefromnodes 1 0 150 5 179
```

**`*linecreatefromnodes` 签名**：`<list_mark> <break_angle> <max_angle> <flags>`
直接传两个节点 id 当参数**无效**（不报错也不建线），必须先 `*createlist`。

---

## 6. automesh / equivalence / 导出

```tcl
*elementorder 1
*setedgedensitylinkwithaspectratio -1

proc try_mesh {sid sz} {
  *createmark surfaces 1 $sid
  catch {*interactiveremeshsurf 1 $sz 2 2 2 1 1}   ;# 先交互剖分（布种子）
  catch {*automesh 0 2 2}                          ;# 再执行
  catch {*storemeshtodatabase 1}                   ;# ★ 落库，不写这步网格不保存
  *createmark elems 1 "by surface" $sid
  return [llength [hm_getmark elems 1]]
}

# 节点编号
foreach el [hm_getmark elems 1] { set nds [hm_getentityarray elems $el nodes] }
set x [hm_nodevalue $nd x]

# 缝合（拓扑正确时节点数应不变）
*createmark nodes 1 all ; set n0 [hm_marklength nodes 1]
*equivalence2 0.05
*createmark nodes 1 all ; set n1 [hm_marklength nodes 1]   ;# n0 == n1 才是真共节点

# 删除
*createmark surfaces 1 $a ; *appendmark surfaces 1 $b
if {[hm_marklength surfaces 1] > 0} { catch {*deletemark surfaces 1} }
```

**顺序铁律**：`*interactiveremeshsurf` → `*automesh` → `*storemeshtodatabase`，
三步缺一不可（缺最后一步 = 网格生成但没落库，导出为 0）。

---

## 7. Tcl 自身坑（与版本无关，但每次都中）

```tcl
# 数组/括号误解析
lappend keep [format "%s(%.0f)" $s $a]     ;# ✓
lappend keep "$s([format %.0f $a])"        ;# ✗ 被当成数组引用

# 列表重复添加
lappend junk $SL3                          ;# ✓
foreach s $junk { lappend junk $SL3 }      ;# ✗ 迭代中改自身

# 空列表展开
*createmark lines 2 {*}$lns                ;# ✓ Tcl 8.5+
eval "*createmark lines 2 $lns"            ;# ✓ 兼容写法
```

---

## 8. 运行方式

```bash
HMB="/d/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe"
"$HMB" -tcl "E:/path/to/script.tcl"

# 2020（旧链，已锁定不再新增）
"/e/BaiduNetdiskDownload/Hyperworks2020/2020/hwdesktop/hm/bin/win64/hmbatch.exe" -tcl x.tcl
```

**路径必须全英文**——中文路径 hmbatch 必挂。
残留 `hw.exe` 会占资源，发现异常先 `taskkill //F //IM hw.exe`。
`*readfile` 返回 1 不代表失败（实测返回 1 但导入成功），以实体计数为准。
