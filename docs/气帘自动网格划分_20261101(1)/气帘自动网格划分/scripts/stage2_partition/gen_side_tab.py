# -*- coding: utf-8 -*-
"""
侧面拉带 (cab2 第二步补漏) -> Tcl
------------------------------------------------------------------
用户指出的红圈: 一条横向拉带 X 1572~1771, 主条宽 10.2mm,
右端眼环 (宽到 23.8mm) + 凸销, 从布带端面 X=1620.2 的缺口
(Y 161.6~181.8, L1 762) 穿出。

轮廓来源 side_tether.json (L4 线栅格并集 + DP, 面积 2330.6)。

左端: CAD 里 1572~1620 这段落在布带内部、与布带面重叠 -> FE 里不重复建面
      (布带已覆盖该区), 拉带左端直接落在布带边界 X=1620.2 上, 宽度取
      161.7~181.7 (= 缺口宽) -> 与布带边界那排节点 (Y 159/164/169/174/179/184,
      间距 5mm) 最近邻 1-to-1 捏合。
      这符合参考模型规则: 拉带根部与布带共节点 (参考 PID6∩PID7=164,
      PID6∩PID8=115), 拉带与气腔共节点=0。

眼环孔/缝制纹按"细小 curve 可忽略"填实。
"""
import json

SRC = "side_tether.json"
OUT_TCL = "cab2_step2b_side.tcl"

d = json.load(open(SRC, encoding="utf-8"))[0]
raw = [tuple(q) for q in d["pts"]]

# 找到左端封口两点 (X 最小的那两个, 即 17/18)
i0 = min(range(len(raw)), key=lambda i: raw[i][0])
# 保证 i0 是下角 (Y 较小)
if raw[(i0 + 1) % len(raw)][0] < raw[i0 - 1][0]:
    i0 = (i0 + 1) % len(raw)
seq = raw[i0:] + raw[:i0]
assert abs(seq[0][0] - 1572.4) < 1, seq[0]

# seq[0]/seq[-1] 是左端封口两点, 都要去掉; seq[-2] 与 poly 首点重复, 也去掉
tail = seq[2:-2]
# 左端 Y 直接取布带边界那排节点的实测值 (间距 5mm) -> 捏合零位移
X_BELT, X_NECK = 1620.2, 1645.0
Y_LO, Y_HI = 159.01, 184.02

poly = [
    (1719.40, 167.00),   # 主条上边右端
    (X_NECK, 167.00),
    (X_BELT, Y_LO),      # 左端下角 (= 布带缺口下缘)
    (X_BELT, Y_HI),      # 左端上角 (= 布带缺口上缘)
    (X_NECK, 177.20),
] + tail


def sarea(p):
    s = 0.0
    for i in range(len(p)):
        j = (i + 1) % len(p)
        s += p[i][0] * p[j][1] - p[j][0] * p[i][1]
    return s / 2


A = abs(sarea(poly))
xs = [q[0] for q in poly]; ys = [q[1] for q in poly]
print(f"侧面拉带多边形 {len(poly)} 点  面积 {A:.1f} mm²")
print(f"  X[{min(xs):.1f},{max(xs):.1f}]  Y[{min(ys):.1f},{max(ys):.1f}]")
print(f"  左端 {Y_LO:.2f}~{Y_HI:.2f} (宽 {Y_HI-Y_LO:.1f}) -> {X_NECK-X_BELT:.0f}mm 内收到 9.4mm 主条")
print(f"  对齐布带边界节点 Y=159.01/164.02/169.02/174.02/179.02/184.02 (6 个, 零位移)")

L = []
w = L.append
w("# cab2 step2b: side tether (red-circled, exits through belt end notch L1 762)")
w("# outline: side_tether.json (L4 raster union + DP 0.8mm), left end snapped to belt boundary")
foreach = """foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}"""
w(foreach)
w('if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }')
w('if {[info exists ::env(MESHSIZE)] && $::env(MESHSIZE) ne ""} { set TSIZE $::env(MESHSIZE) } else { set TSIZE 5.0 }')
w('set rep [open "$P/out/cab2_step2b_report.txt" w]')
w('proc log {m} { upvar #0 rep rep; puts $rep $m; flush $rep }')
w('*readfile "$P/input/cab2.hm"')
w('log "readfile done"')
w('*elementorder 1')
w('*setedgedensitylinkwithaspectratio -1')
w('set nids {}')
for q in poly:
    w('*createnode %.5f %.5f 0 0 0' % (q[0], q[1]))
    w('lappend nids [hm_entitymaxid nodes]')
w('set nl [llength $nids]')
w('set lns {}')
w('for {set i 0} {$i < $nl} {incr i} {')
w('  set a [lindex $nids $i]; set b [lindex $nids [expr {($i+1) % $nl}]]')
w('  *createlist nodes 1 $a $b')
w('  catch {*linecreatefromnodes 1 0 150 5 179}')
w('  lappend lns [hm_entitymaxid lines]')
w('}')
w('set s0 [hm_entitymaxid surfaces]')
w('*createmark lines 1 [lindex $lns 0]')
w('foreach ln [lrange $lns 1 end] { *appendmark lines 1 $ln }')
w('set r [catch {*surfacesplineonlinesloop 1 1 0 1} e]')
w('set sid -1')
w('*createmark surfaces 1 all')
w('foreach s [hm_getmark surfaces 1] { if {$s > $s0} { set sid $s } }')
w('if {$sid < 0} { log "SIDE SPLINE FAIL r=$r e=$e"; close $rep; puts "__HW_DONE__"; exit }')
w('log "SIDE surf=$sid area=[format %.1f [hm_getareaofsurface surfaces $sid]]"')
w('*createmark surfaces 1 $sid')
w('catch {*interactiveremeshsurf 1 $TSIZE 2 2 2 1 1}')
w('catch {*automesh 0 2 2}')
w('catch {*storemeshtodatabase 1}')
w('*createmark elems 1 "by surface" $sid')
w('set es [hm_getmark elems 1]')
w('set nq 0; set nt 0')
w('foreach el $es {')
w('  set nds [hm_getentityarray elems $el nodes]')
w('  if {[llength $nds] == 4} { incr nq } elseif {[llength $nds] == 3} { incr nt }')
w('}')
w('log "SIDE elems=[llength $es] quad=$nq tria=$nt"')
w('set fo [open "$P/out/cab2_step2b_side.txt" w]')
w('set allnodes {}')
w('foreach el $es {')
w('  set nds [hm_getentityarray elems $el nodes]')
w('  puts $fo "S side $el $nds"')
w('  foreach nd $nds { lappend allnodes $nd }')
w('}')
w('set uniq [lsort -integer -unique $allnodes]')
w('foreach nd $uniq {')
w('  puts $fo "N $nd [hm_nodevalue $nd x] [hm_nodevalue $nd y] [hm_nodevalue $nd z]"')
w('}')
w('close $fo')
w('log "EXPORT side nodes=[llength $uniq]"')
# 左端一排节点 (与布带捏合用)
w('set edge {}')
w('foreach nd $uniq {')
w('  set x [hm_nodevalue $nd x]')
w('  if {$x < 1622.5} { lappend edge "$nd [hm_nodevalue $nd y]" }')
w('}')
w('log "SIDE edge candidates: [expr {[llength $edge]/2}]"')
w('close $rep')
w('puts "__HW_DONE__"')

open(OUT_TCL, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print(f"\n写出 {OUT_TCL}")
