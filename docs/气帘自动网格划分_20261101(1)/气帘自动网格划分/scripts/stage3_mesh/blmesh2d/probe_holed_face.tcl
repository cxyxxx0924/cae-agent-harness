hm_framework loaduserprofile LsDyna Keyword971_R16.0
*elementorder 1
*setedgedensitylinkwithaspectratio -1
set fp [open {E:/work/AI_CAB/分区训练/washer_probe/expS.log} w]
proc log {s} { global fp; puts $fp $s; flush $fp }
proc mkline {a b} {
  *createlist nodes 1 $a $b
  *linecreatefromnodes 1 0 150 5 179
  return [hm_entitymaxid lines]
}
proc addnode {x y} { *createnode $x $y 0 0 0; return [hm_entitymaxid nodes] }
proc area {s} { set a 0; catch {set a [hm_getareaofsurface surfaces $s]}; return $a }

proc build_holed {dx} {
  set o1 [addnode $dx 0]; set o2 [addnode [expr {$dx+120}] 0]
  set o3 [addnode [expr {$dx+120}] 80]; set o4 [addnode $dx 80]
  set OL {}
  lappend OL [mkline $o1 $o2]; lappend OL [mkline $o2 $o3]
  lappend OL [mkline $o3 $o4]; lappend OL [mkline $o4 $o1]
  *createmark lines 1 {*}$OL
  catch {*surfacesplineonlinesloop 1 1 0 1}
  set S [hm_entitymaxid surfaces]
  # 内孔 40x24
  set i1 [addnode [expr {$dx+40}] 28]; set i2 [addnode [expr {$dx+80}] 28]
  set i3 [addnode [expr {$dx+80}] 52]; set i4 [addnode [expr {$dx+40}] 52]
  set IL {}
  lappend IL [mkline $i1 $i2]; lappend IL [mkline $i2 $i3]
  lappend IL [mkline $i3 $i4]; lappend IL [mkline $i4 $i1]
  *createmark surfaces 1 $S
  *createmark lines 1 {*}$IL
  catch {*surfacemarksplitwithlines 1 1}
  # 找出带孔面（面积大的）与小面
  *createmark surfaces 1 "all"
  set big -1; set small {}
  foreach s [hm_getmark surfaces 1] {
    set a [area $s]
    if {$a > 4000} { if {[expr {abs($a-8640)}] < 50} { set big $s } }
  }
  if {$big < 0} { return -1 }
  # 删掉内小面
  foreach s [hm_getmark surfaces 1] {
    if {$s != $big} {
      *createmark surfaces 1 $s
      catch {*deletemark surfaces 1}
    }
  }
  return $big
}

# ---------- A: 普通 automesh ----------
set sA [build_holed 0]
log "A holed surf=$sA area=[format %.1f [area $sA]]"
*createmark surfaces 1 $sA
catch {*interactiveremeshsurf 1 5.0 2 2 2 1 1}
catch {*automesh 0 2 2}
catch {*storemeshtodatabase}

# ---------- B: blmesh ----------
set sB [build_holed 200]
log "B holed surf=$sB area=[format %.1f [area $sB]]"
*createmark surfs 1 $sB
catch {*createstringarray 2 {element_size: 5.0} {element_type: quads}}
log "B blmesh r=[catch {*blmesh_2d2 surfs 1 1 4.0 1.0 1 2 1} e] e=$e"
catch {*storemeshtodatabase}

foreach side [list [list A $sA] [list B $sB]] {
  set tg [lindex $side 0]
  set s [lindex $side 1]
  *createmark nodes 1 "by surface" $s
  set nn [llength [hm_getmark nodes 1]]
  *createmark elems 1 "by surface" $s
  set ne [llength [hm_getmark elems 1]]
  log "$tg: nodes=$nn elems=$ne"
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
