hm_framework loaduserprofile LsDyna Keyword971_R16.0
*elementorder 1
*setedgedensitylinkwithaspectratio -1
set fp [open {E:/work/AI_CAB/分区训练/washer_probe/expL.log} w]
proc log {s} { global fp; puts $fp $s; flush $fp }

proc mkline {a b} {
  *createlist nodes 1 $a $b
  *linecreatefromnodes 1 0 150 5 179
  return [hm_entitymaxid lines]
}

# 气帘脖子形轮廓（V 形凹口 + 窄颈）
set PTS {{0 0} {120 0} {120 80} {70 80} {63 46} {60 40} {57 46} {50 80} {0 80}}

proc build {dx} {
  global PTS
  set nids {}
  foreach p $PTS {
    *createnode [expr {[lindex $p 0] + $dx}] [lindex $p 1] 0 0 0
    lappend nids [hm_entitymaxid nodes]
  }
  set ln {}
  set m [llength $nids]
  for {set i 0} {$i < $m} {incr i} {
    lappend ln [mkline [lindex $nids $i] [lindex $nids [expr {($i+1) % $m}]]]
  }
  *createmark lines 1 {*}$ln
  catch {*surfacesplineonlinesloop 1 1 0 1}
  return [list [hm_entitymaxid surfaces] $ln]
}

proc dump {s tag} {
  global fp
  *createmark nodes 1 "by surface" $s
  set ns [hm_getmark nodes 1]
  *createmark elems 1 "by surface" $s
  set es [hm_getmark elems 1]
  global fp
  foreach n $ns {
    puts $fp "N $tag $n [hm_getentityvalue nodes $n x 0] [hm_getentityvalue nodes $n y 0]"
  }
  foreach e $es {
    *createmark nodes 1 "by elems" $e
    puts $fp "E $tag $e [join [hm_getmark nodes 1] { }]"
  }
  return [list [llength $ns] [llength $es]]
}

# ---------- A: 普通 automesh ----------
set r1 [build 0]
set sA [lindex $r1 0]
*createmark surfaces 1 $sA
catch {*interactiveremeshsurf 1 5.0 2 2 2 1 1}
catch {*automesh 0 2 2}
catch {*storemeshtodatabase}
log "A automesh: nodes/elems = [dump $sA A]"

# ---------- B: blmesh_2d2 1 层 4mm ----------
set r2 [build 200]
set sB [lindex $r2 0]
set lnB [lindex $r2 1]
*createmark surfs 1 $sB
catch {*createstringarray 2 {element_size: 5.0} {element_type: quads}}
log "B blmesh r=[catch {*blmesh_2d2 surfs 1 1 4.0 1.0 1 2 1} e] e=$e"
catch {*storemeshtodatabase}
log "B blmesh: nodes/elems = [dump $sB B]"

close $fp
