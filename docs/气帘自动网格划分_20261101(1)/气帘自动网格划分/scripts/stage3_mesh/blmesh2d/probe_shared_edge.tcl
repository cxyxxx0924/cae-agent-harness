hm_framework loaduserprofile LsDyna Keyword971_R16.0
*elementorder 1
*setedgedensitylinkwithaspectratio -1
set fp [open {E:/work/AI_CAB/分区训练/washer_probe/expO.log} w]
proc log {s} { global fp; puts $fp $s; flush $fp }
proc mkline {a b} {
  *createlist nodes 1 $a $b
  *linecreatefromnodes 1 0 150 5 179
  return [hm_entitymaxid lines]
}

*createnode   0  0 0 0 0
*createnode  50  0 0 0 0
*createnode 100  0 0 0 0
*createnode 100 60 0 0 0
*createnode  50 60 0 0 0
*createnode   0 60 0 0 0
set l1 [mkline 1 2]; set l2 [mkline 2 3]; set l3 [mkline 3 4]
set l4 [mkline 4 5]; set l5 [mkline 5 6]; set l6 [mkline 6 1]; set l7 [mkline 2 5]
*createmark lines 1 $l1 $l7 $l5 $l6
catch {*surfacesplineonlinesloop 1 1 0 1}
set sL [hm_entitymaxid surfaces]
*createmark lines 1 $l2 $l3 $l4 $l7
catch {*surfacesplineonlinesloop 1 1 0 1}
set sR [hm_entitymaxid surfaces]
log "sL=$sL sR=$sR 共享线 l7=$l7"

# ===== 关键实验: 两个面放进同一个 blmesh 调用 =====
*createmark surfs 1 $sL $sR
log "mark surfs = [hm_getmark surfs 1]"
catch {*createstringarray 2 {element_size: 5.0} {element_type: quads}}
log "blmesh_2d2 双面 r=[catch {*blmesh_2d2 surfs 1 1 4.0 1.0 1 2 1} e] e=$e"
catch {*storemeshtodatabase}

*createmark nodes 1 "by surface" $sL
set a [hm_getmark nodes 1]
*createmark nodes 1 "by surface" $sR
set b [hm_getmark nodes 1]
log "L 节点=[llength $a]  R 节点=[llength $b]"

set ax {}
foreach n $a {
  if {abs([hm_getentityvalue nodes $n x 0] - 50) < 0.01} { lappend ax $n }
}
set c 0
foreach n $ax { if {[lsearch -exact -integer $b $n] >= 0} { incr c } }
log "==> x=50 上: L 侧 [llength $ax] 个, 共用节点 $c 个"

*createmark elems 1 "by surface" $sL
set ea [hm_getmark elems 1]
*createmark elems 1 "by surface" $sR
set eb [hm_getmark elems 1]
log "L elems=[llength $ea] R elems=[llength $eb]"

# 导出看形态
foreach side [list [list A $sL] [list B $sR]] {
  set tg [lindex $side 0]
  set s [lindex $side 1]
  *createmark nodes 1 "by surface" $s
  foreach n [hm_getmark nodes 1] {
    puts $fp "N $tg $n [hm_getentityvalue nodes $n x 0] [hm_getentityvalue nodes $n y 0]"
  }
  *createmark elems 1 "by surface" $s
  foreach e [hm_getmark elems 1] {
    *createmark nodes 1 "by elems" $e
    puts $fp "E $tg $e [join [hm_getmark nodes 1] { }]"
  }
}
close $fp
