# build_step1_2026.tcl — 2026 第一步: 缝线环/气腔环/布带环 三面网格
#   拓扑: 缝面 spline 建面 → 面取边线 → BLUE 裁 L3 边线得 CAV+BELT → CAV 裁缝面边线得洞
#   网格: 先小后大 (SEAM → CAV → BELT), 共享边节点复用 ⇒ 界面共节点
#   导出: out/step1_mesh_2026.txt  (S <tag> <eid> <nodes...> / N <nid> <x> <y> <z>)
foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}
if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }
set MESHSIZE 5.0
set EQTOL 0.05
set rep [open "$P/out/step1_2026_report.txt" w]
proc log {m} { upvar #0 rep rep; puts $rep $m; flush $rep }
proc surf_area {sid} { set a 0; catch {set a [hm_getareaofsurface surfaces $sid]}; return $a }
proc new_surfs {m0} {
  *createmark surfaces 1 all
  set ns {}
  foreach s [hm_getmark surfaces 1] { if {$s > $m0} { lappend ns $s } }
  return $ns
}
proc biggest {ids} {
  set b -1; set ba -1
  foreach s $ids { set a [surf_area $s]; if {$a > $ba} { set ba $a; set b $s } }
  return $b
}
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
  catch {*linefromsurfedgecomp surfaces 1 1}
  set es {}
  *createmark lines 1 all
  foreach ln [hm_getmark lines 1] { if {$ln > $l0} { lappend es $ln } }
  log "RING $tag surf=$s area=[format %.1f [surf_area $s]] edges=[llength $es]"
  return [list $s $es $ns]
}
proc trim_by {surf lns tag junkvar} {
  upvar #0 rep rep; upvar 1 $junkvar junk
  set m0 [hm_entitymaxid surfaces]
  *createmark surfaces 1 $surf
  eval "*createmark lines 2 $lns"
  set r [catch {*surfacemarksplitwithlines 1 2 0 13 0} e]
  set ns [new_surfs $m0]
  if {[llength $ns] == 0} { log "TRIM $tag FAIL r=$r e=$e"; return [list $surf -1] }
  set hole [biggest $ns]
  set body [biggest [concat [list $surf] $ns]]
  foreach s $ns { if {$s != $hole && $s != $body} { lappend junk $s } }
  log "TRIM $tag hole=$hole area=[format %.1f [surf_area $hole]] body=$body area=[format %.1f [surf_area $body]]"
  return [list $body $hole]
}

*readfile "$P/input/cab1.hm"
set junk {}

# ===== 1. 缝环准备: 补桥 + 拆 157 =====
set n0 [hm_entitymaxid nodes]
*createnode 1354.826 0 815.648 0 0 0
*createnode 1360.685 0 812.014 0 0 0
*createlist nodes 1 [expr {$n0+1}] [expr {$n0+2}]
catch {*linecreatefromnodes 1 0 150 5 179}
set bridge [hm_entitymaxid lines]
*createnode 1417.96 0 836.748 0 0 0
set nid [hm_entitymaxid nodes]
set lm0 [hm_entitymaxid lines]
catch {*linesplitatpoint 157 $nid}
set half157 -1
*createmark lines 1 all
foreach ln [hm_getmark lines 1] {
    if {$ln <= $lm0} { continue }
    set sp [hm_getlinestartpoint $ln]; set ep [hm_getlineendpoint $ln]
    set s1 [expr {abs([lindex $sp 0]-1360.685)+abs([lindex $sp 2]-812.014)}]
    set s2 [expr {abs([lindex $ep 0]-1360.685)+abs([lindex $ep 2]-812.014)}]
    if {$s1 < 2.0 || $s2 < 2.0} { set half157 $ln }
}
log "bridge=$bridge half157=$half157"

# ===== 2. 5 个缝面 =====
set ringdefs [list \
  [list seam0 {337}] \
  [list seam1 {336}] \
  [list seam2 {193}] \
  [list seam3 [list $half157 $bridge 158 159 160 161 162 163 164 165 166 167 168 169]] \
  [list seam4 {140 141 142 144 146 147 148 149 150 151 152 153 154 155}] ]
set seam_ids {}
foreach rd $ringdefs {
    set tag [lindex $rd 0]; set lns [lindex $rd 1]
    if {[lsearch $lns -1] >= 0} { log "RING $tag SKIP"; continue }
    lassign [make_ring_surf $lns $tag] sid es ns
    if {$sid > 0} { lappend seam_ids $sid }
}
log "seam_ids=$seam_ids"

# ===== 3. L3 面 -> 边线 =====
*createmark lines 1 "by collector" 3
set i0 [hm_entitymaxid surfaces]
*surfacesplineonlinesloop 1 1 0 1
set SL3 [lindex [new_surfs $i0] 0]
set l0 [hm_entitymaxid lines]
*createmark surfaces 1 $SL3
catch {*linefromsurfedgecomp surfaces 1 1}
set l3edges {}
*createmark lines 1 all
foreach ln [hm_getmark lines 1] { if {$ln > $l0} { lappend l3edges $ln } }
log "SL3=$SL3 area=[format %.1f [surf_area $SL3]] edges=[llength $l3edges]"

# ===== 4. BLUE -> CAV + BELT =====
*createmark lines 1 "by collector" 2
set i1 [hm_entitymaxid surfaces]
*surfacesplineonlinesloop 1 1 0 1
set SBLUE [lindex [new_surfs $i1] 0]
log "SBLUE=$SBLUE area=[format %.1f [surf_area $SBLUE]]"
lassign [trim_by $SBLUE $l3edges "L3" junk] SCAV dummy
set SBELT -1
*createmark surfaces 1 all
foreach s [hm_getmark surfaces 1] {
    if {$s == $SCAV || $s == $SL3 || [lsearch $seam_ids $s] >= 0} { continue }
    if {[surf_area $s] > 50000} { set SBELT $s }
}
log "SCAV=$SCAV area=[format %.1f [surf_area $SCAV]]  SBELT=$SBELT area=[format %.1f [surf_area $SBELT]]"

# ===== 5. CAV 裁 5 个缝洞 (洞内面=真缝面, 与 CAV 共享 topo edge ⇒ 共节点) =====
set seam_holes {}
foreach rd $ringdefs {
    set tag [lindex $rd 0]
    set idx [lsearch $ringdefs $rd]
    set sid [lindex $seam_ids $idx]
    if {$sid <= 0} { continue }
    set l0 [hm_entitymaxid lines]
    *createmark surfaces 1 $sid
    catch {*linefromsurfedgecomp surfaces 1 1}
    set es {}
    *createmark lines 1 all
    foreach ln [hm_getmark lines 1] { if {$ln > $l0} { lappend es $ln } }
    if {[llength $es] == 0} { log "TRIM seam $tag no edge"; continue }
    lassign [trim_by $SCAV $es "SEAM_$tag" junk] SCAV hole
    if {$hole > 0} { lappend seam_holes $hole }
}
log "seam_holes=$seam_holes"
log "FINAL SCAV=$SCAV area=[format %.1f [surf_area $SCAV]]  junk=$junk"

# ===== 6. 删多余面 (L3_SRC + 碎片 + 洞内面) =====
lappend junk $SL3
if {[llength $junk] > 0} {
    *createmark surfaces 1 [lindex $junk 0]
    foreach s [lrange $junk 1 end] { *appendmark surfaces 1 $s }
    if {[hm_marklength surfaces 1] > 0} { catch {*deletemark surfaces 1} }
}
*createmark surfaces 1 all
set keep {}
foreach s [hm_getmark surfaces 1] { lappend keep [format "%s(%.0f)" $s [surf_area $s]] }
log "KEEP surfaces: $keep"

# ===== 7. automesh (先小后大) =====
*elementorder 1
*setedgedensitylinkwithaspectratio -1
proc try_mesh {tag sid sz} {
  upvar #0 rep rep
  *createmark surfaces 1 $sid
  set e1 "-"; set r1 [catch {*interactiveremeshsurf 1 $sz 2 2 2 1 1} e1]
  set e2 "-"; set r2 [catch {*automesh 0 2 2} e2]
  catch {*storemeshtodatabase 1}
  *createmark elems 1 "by surface" $sid
  set es [hm_getmark elems 1]
  set nq 0; set nt 0
  foreach el $es {
    set nds [hm_getentityarray elems $el nodes]
    if {[llength $nds] == 4} { incr nq } elseif {[llength $nds] == 3} { incr nt }
  }
  log "MESH $tag surf=$sid sz=$sz elems=[llength $es] quad=$nq tria=$nt r1=$r1/$e1 r2=$r2/$e2"
  return [llength $es]
}
set si 0
foreach s $seam_holes {
  set n [try_mesh "seam$si" $s $MESHSIZE]
  if {$n == 0} { set n [try_mesh "seam$si-3mm" $s 3.0] }
  incr si
}
try_mesh cav $SCAV $MESHSIZE
try_mesh belt $SBELT $MESHSIZE

# ===== 8. equivalence =====
*createmark nodes 1 all
set nn0 [hm_marklength nodes 1]
set e "-"; set r [catch {*equivalence2 $EQTOL} e]
*createmark nodes 1 all
set nn1 [hm_marklength nodes 1]
log "equivalence2 $EQTOL: r=$r nodes $nn0 -> $nn1"

# ===== 9. 导出 =====
set fo [open "$P/out/step1_mesh_2026.txt" w]
set allnodes {}
set si 0
foreach s $seam_holes {
  *createmark elems 1 "by surface" $s
  foreach el [hm_getmark elems 1] {
    set nds [hm_getentityarray elems $el nodes]
    puts $fo "S seam$si $el $nds"
    foreach nd $nds { lappend allnodes $nd }
  }
  incr si
}
*createmark elems 1 "by surface" $SCAV
foreach el [hm_getmark elems 1] {
  set nds [hm_getentityarray elems $el nodes]
  puts $fo "S cav $el $nds"
  foreach nd $nds { lappend allnodes $nd }
}
*createmark elems 1 "by surface" $SBELT
foreach el [hm_getmark elems 1] {
  set nds [hm_getentityarray elems $el nodes]
  puts $fo "S belt $el $nds"
  foreach nd $nds { lappend allnodes $nd }
}
set uniq [lsort -integer -unique $allnodes]
foreach nd $uniq {
  puts $fo "N $nd [hm_nodevalue $nd x] [hm_nodevalue $nd y] [hm_nodevalue $nd z]"
}
close $fo
log "EXPORT nodes=[llength $uniq]"
close $rep
puts "__HW_DONE__"
