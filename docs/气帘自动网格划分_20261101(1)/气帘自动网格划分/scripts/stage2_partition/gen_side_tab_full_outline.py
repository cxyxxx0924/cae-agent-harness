# -*- coding: utf-8 -*-
"""
侧面拉带 v2 —— 用完整 CAD 轮廓 (X 1572.4~1771.2), 不再砍掉布带内的重叠段
------------------------------------------------------------------
v1 的错误: 认为 "1572~1620 落在布带内、布带已覆盖 -> 不重复建面"。
实际拉带是独立 Z 层 (Z=-1), 与布带 (Z=0) 不是同一张面; 砍掉该段后:
  ① 拉带与布带的缝接位置退到布带端面 X=1620.2, 而不是 CAD 的真实锚固端 X=1572.4;
  ② 布带-拉带重叠区 (48mm x 10mm) 缺失 -> 该处连接/接触位置算不准。

v2 规则 (与参考模型 5P-BAG_004 一致):
  · 轮廓按 CAD 全长建立 (含重叠段);
  · 根部一排节点 (X 最小的那一排) 与布带节点共节点 (= 缝线), 收 Z0;
  · 其余节点在拉带平面 Z=-1;
  · 拉带与气腔共节点必须 = 0。
"""
import json

SRC = "side_tether.json"
OUT_TCL = "cab2_step2b_side2.tcl"

d = json.load(open(SRC, encoding="utf-8"))[0]
raw = [tuple(q) for q in d["pts"]]
# 去掉末尾重复闭合点
if abs(raw[0][0] - raw[-1][0]) < 1e-6 and abs(raw[0][1] - raw[-1][1]) < 1e-6:
    raw = raw[:-1]


def sarea(p):
    s = 0.0
    for i in range(len(p)):
        j = (i + 1) % len(p)
        s += p[i][0] * p[j][1] - p[j][0] * p[i][1]
    return s / 2


# 保证逆时针
poly = raw if sarea(raw) > 0 else raw[::-1]
A = abs(sarea(poly))
xs = [q[0] for q in poly]; ys = [q[1] for q in poly]
print(f"侧面拉带 v2  多边形 {len(poly)} 点  面积 {A:.1f} mm²")
print(f"  X[{min(xs):.1f},{max(xs):.1f}]  Y[{min(ys):.1f},{max(ys):.1f}]")
print(f"  根部锚固端 X={min(xs):.1f} (布带内), 穿出点 X=1620.2 (布带端面缺口 L1 762)")
print(f"  与布带重叠段长 {1620.2-min(xs):.1f}mm, 宽约 10mm -> 面积约 {(1620.2-min(xs))*10.2:.0f} mm²")

L = []
w = L.append
w("# cab2 step2b v2: side tether — FULL CAD outline incl. the in-belt overlap")
w("# root row (min X) is the sew line; it gets merged 1:1 onto belt nodes at Z0 in assemble")
w("""foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}""")
w('if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }')
w('if {[info exists ::env(MESHSIZE)] && $::env(MESHSIZE) ne ""} { set TSIZE $::env(MESHSIZE) } else { set TSIZE 5.0 }')
w('set rep [open "$P/out/cab2_step2b_report2.txt" w]')
w('proc log {m} { upvar #0 rep rep; puts $rep $m; flush $rep }')
w('*readfile "$P/input/cab2.hm"')
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
w('if {$sid < 0} { log "SIDE2 SPLINE FAIL r=$r e=$e"; close $rep; puts "__HW_DONE__"; exit }')
w('log "SIDE2 surf=$sid area=[format %.1f [hm_getareaofsurface surfaces $sid]]"')
w('*createmark surfaces 1 $sid')
# 长条窄带: 强制 2 排, 用 TSIZE 控制
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
w('log "SIDE2 elems=[llength $es] quad=$nq tria=$nt"')
w('set fo [open "$P/out/cab2_step2b_side2.txt" w]')
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
w('log "EXPORT side2 nodes=[llength $uniq]"')
w('set mn 1e9; set mx -1e9')
w('foreach nd $uniq { set x [hm_nodevalue $nd x]; if {$x<$mn} {set mn $x}; if {$x>$mx} {set mx $x} }')
w('log "SIDE2 X range $mn .. $mx"')
w('close $rep')
w('puts "__HW_DONE__"')

open(OUT_TCL, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print(f"\n写出 {OUT_TCL}")
