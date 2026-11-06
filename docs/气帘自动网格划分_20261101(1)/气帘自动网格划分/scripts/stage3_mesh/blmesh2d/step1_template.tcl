# step1_template.tcl — 通用「分区 → 裁切拓扑 → blmesh 建网格」模板
#   由 scripts/drivers/gen_step1_tcl.py 填充下列占位符后调用, 不要直接跑本文件:
#     @@CASENAME@@   案例名(日志/默认输出名用)
#     @@MODEL@@      input/ 下的 .hm 文件名
#     @@CID_CAV@@    气腔轮廓线所在 collector id
#     @@CID_BELT@@   布带轮廓线所在 collector id
#     @@RINGDEFS@@   ringdefs 列表字面量 —— 由 chain_loops.py 自动成环结果生成
#                    (替代旧版手写 seam0..seamN 的 line id)
#   判据来源: 缝线数量/每条缝线的线集合全部来自 out/loops.json, 不写死。
#   环境变量: WORKDIR  MESHSIZE  SEAMSIZE  BL_THICK(默认4.0)  BL_LAYER(默认1)
#             BL_ETYPE(默认 mixed)  OUTNAME
#   导出: out/<OUTNAME>  (S <tag> <eid> <nodes...> / N <nid> <x> <y> <z>)
foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}
if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }
if {[info exists ::env(MESHSIZE)] && $::env(MESHSIZE) ne ""} { set MESHSIZE $::env(MESHSIZE) } else { set MESHSIZE 5.0 }
if {[info exists ::env(SEAMSIZE)] && $::env(SEAMSIZE) ne ""} { set SEAMSIZE $::env(SEAMSIZE) } else { set SEAMSIZE $MESHSIZE }
if {[info exists ::env(BL_THICK)] && $::env(BL_THICK) ne ""} { set BL_THICK $::env(BL_THICK) } else { set BL_THICK 4.0 }
if {[info exists ::env(BL_LAYER)] && $::env(BL_LAYER) ne ""} { set BL_LAYER $::env(BL_LAYER) } else { set BL_LAYER 1 }
if {[info exists ::env(OUTNAME)] && $::env(OUTNAME) ne ""} { set OUTNAME $::env(OUTNAME) } else { set OUTNAME @@CASENAME@@_step1_bl.txt }
if {[info exists ::env(BL_ETYPE)] && $::env(BL_ETYPE) ne ""} { set BL_ETYPE $::env(BL_ETYPE) } else { set BL_ETYPE mixed }
set rep [open "$P/out/@@CASENAME@@_step1_bl_report.txt" w]
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
proc surf_edges {sid} {
  set l0 [hm_entitymaxid lines]
  *createmark surfaces 1 $sid
  catch {*linefromsurfedgecomp surfaces 1 1}
  set es {}
  *createmark lines 1 all
  foreach ln [hm_getmark lines 1] { if {$ln > $l0} { lappend es $ln } }
  return $es
}
proc edge_len {ln} { set L 0; catch {set L [hm_linelength $ln]}; return $L }
proc split_one {surf edge} {
  set m0 [hm_entitymaxid surfaces]
  *createmark surfaces 1 $surf
  *createmark lines 2 $edge
  set r [catch {*surfacemarksplitwithlines 1 2 0 13 0} e]
  set ns {}
  *createmark surfaces 1 all
  foreach s [hm_getmark surfaces 1] { if {$s > $m0} { lappend ns $s } }
  return [list $r $ns]
}
proc trim_by_edges {surf edges tag junkvar} {
  upvar #0 rep rep; upvar 1 $junkvar junk
  set lenlist {}
  foreach x $edges { lappend lenlist [edge_len $x] }
  set sl [lsort -real -decreasing $lenlist]
  set order {}
  foreach L $sl {
    foreach x $edges { if {[expr {abs([edge_len $x] - $L) < 1e-6}] && [lsearch $order $x] < 0} { lappend order $x } }
  }
  foreach edge $order {
    lassign [split_one $surf $edge] r ns
    if {[llength $ns] == 0} { log "SPLIT $tag edge=$edge len=[format %.1f [edge_len $edge]] r=$r NO-NEW-SURF"; continue }
    set hole [biggest $ns]
    foreach s $ns { if {$s != $hole} { lappend junk $s } }
    log "SPLIT $tag edge=$edge len=[format %.1f [edge_len $edge]] keep=${surf}([format %.1f [surf_area $surf]]) hole=${hole}([format %.1f [surf_area $hole]])"
    return [list $surf $hole]
  }
  log "SPLIT $tag FAIL all edges"
  return [list $surf -1]
}
proc make_ring_surf {lns tag} {
  set i0 [hm_entitymaxid surfaces]
  *createmark lines 1 [lindex $lns 0]
  foreach id [lrange $lns 1 end] { *appendmark lines 1 $id }
  set r [catch {*surfacesplineonlinesloop 1 1 0 1} e]
  set ns [new_surfs $i0]
  if {[llength $ns] == 0} { log "RING $tag SPLINE FAIL r=$r e=$e"; return [list -1 {}] }
  set s [lindex $ns 0]
  log "RING $tag surf=$s area=[format %.1f [surf_area $s]]"
  return [list $s $ns]
}
*readfile "$P/input/@@MODEL@@"
log "readfile done; template=[hm_info templatefilename]"
set junk {}

# ===== 1. 缝线面 —— ringdefs 由 chain_loops.py 自动成环生成, 缝线数量不写死 =====
set ringdefs @@RINGDEFS@@
set seam_ids {}
foreach rd $ringdefs {
    set tag [lindex $rd 0]; set lns [lindex $rd 1]
    lassign [make_ring_surf $lns $tag] sid ns
    if {$sid > 0} { lappend seam_ids $sid }
}
log "seam_ids=$seam_ids"

# ===== 2. 气腔轮廓面 (collector @@CID_CAV@@) =====
*createmark lines 1 "by collector" @@CID_CAV@@
set i0 [hm_entitymaxid surfaces]
*surfacesplineonlinesloop 1 1 0 1
set SL3 [lindex [new_surfs $i0] 0]
set l3edges [surf_edges $SL3]
log "SL3=$SL3 area=[format %.1f [surf_area $SL3]] edges=[llength $l3edges]"

# ===== 3. 布带外轮廓面 (collector @@CID_BELT@@) → 裁 L2 得 布带环 + 气腔 =====
*createmark lines 1 "by collector" @@CID_BELT@@
set i1 [hm_entitymaxid surfaces]
*surfacesplineonlinesloop 1 1 0 1
set SBLUE [lindex [new_surfs $i1] 0]
log "SBLUE=$SBLUE area=[format %.1f [surf_area $SBLUE]]"
lassign [trim_by_edges $SBLUE $l3edges "L2" junk] SBLUE SCAV
set SBELT $SBLUE
log "SCAV=${SCAV} area=[format %.1f [surf_area $SCAV]]  SBELT=${SBELT} area=[format %.1f [surf_area $SBELT]]"

# ===== 4. 气腔裁各缝线洞 (数量 = ringdefs 长度) =====
set seam_holes {}
set si 0
foreach rd $ringdefs {
    set tag [lindex $rd 0]
    set sid [lindex $seam_ids $si]
    incr si
    if {$sid <= 0} { continue }
    set es [surf_edges $sid]
    if {[llength $es] == 0} { log "TRIM seam $tag no edge"; continue }
    lassign [trim_by_edges $SCAV $es "SEAM_$tag" junk] SCAV hole
    if {$hole > 0} { lappend seam_holes $hole }
}
log "seam_holes=$seam_holes"
log "FINAL SCAV=${SCAV}([format %.1f [surf_area $SCAV]]) SBELT=${SBELT}([format %.1f [surf_area $SBELT]])"

# ===== 5. 删多余面 =====
lappend junk $SL3
foreach s $seam_ids { lappend junk $s }
set jl {}
foreach s $junk {
    if {$s == $SCAV || $s == $SBELT || [lsearch $seam_holes $s] >= 0} { continue }
    lappend jl $s
}
if {[llength $jl] > 0} {
    *createmark surfaces 1 [lindex $jl 0]
    foreach s [lrange $jl 1 end] { *appendmark surfaces 1 $s }
    if {[hm_marklength surfaces 1] > 0} { catch {*deletemark surfaces 1} }
}
*createmark surfaces 1 all
set keep {}
foreach s [hm_getmark surfaces 1] { lappend keep [format "%s(%.0f)" $s [surf_area $s]] }
log "KEEP surfaces: $keep"

# ===== 6. 网格 =====
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
  log "MESH $tag surf=$sid sz=$sz elems=[llength $es] quad=$nq tria=$nt"
  return [llength $es]
}
# 缝线、布带照旧(小面先做, 保证边界节点先落地)
set si 0
foreach s $seam_holes {
  set n [try_mesh "seam$si" $s $SEAMSIZE]
  if {$n == 0} { set n [try_mesh "seam$si-retry" $s 3.0] }
  incr si
}
try_mesh belt $SBELT $MESHSIZE

# ---- 气腔: blmesh_2d2 一次成型 (贴边 BL_LAYER 层 × BL_THICK, 核心 MESHSIZE) ----
*createmark surfs 1 $SCAV
catch {*createstringarray 2 "element_size: $MESHSIZE" "element_type: $BL_ETYPE"}
set rb [catch {*blmesh_2d2 surfs 1 $BL_LAYER $BL_THICK 1.0 1 2 1} eb]
catch {*storemeshtodatabase 1}
*createmark elems 1 "by surface" $SCAV
set cav_es [hm_getmark elems 1]
set nq 0; set nt 0
foreach el $cav_es {
  set nds [hm_getentityarray elems $el nodes]
  if {[llength $nds] == 4} { incr nq } elseif {[llength $nds] == 3} { incr nt }
}
log "MESH cav blmesh r=$rb e=$eb layer=$BL_LAYER thick=$BL_THICK core=$MESHSIZE etype=$BL_ETYPE elems=[llength $cav_es] quad=$nq tria=$nt"
if {[llength $cav_es] == 0} {
  log "BLMESH FAILED -> fallback automesh"
  try_mesh cav $SCAV $MESHSIZE
}

# ===== 7. 导出 =====
set fo [open "$P/out/$OUTNAME" w]
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
foreach pair [list [list belt $SBELT] [list cav $SCAV]] {
  set tag [lindex $pair 0]; set s [lindex $pair 1]
  *createmark elems 1 "by surface" $s
  foreach el [hm_getmark elems 1] {
    set nds [hm_getentityarray elems $el nodes]
    puts $fo "S $tag $el $nds"
    foreach nd $nds { lappend allnodes $nd }
  }
}
set uniq [lsort -integer -unique $allnodes]
foreach nd $uniq {
  puts $fo "N $nd [hm_nodevalue $nd x] [hm_nodevalue $nd y] [hm_nodevalue $nd z]"
}
close $fo
log "EXPORT nodes=[llength $uniq]"
# 界面一致性(气腔自由边节点与布带/缝线是否共用)由 assemble_cab2.py 在合并阶段统计,
# 这里不再重复 —— HM 侧统计需按单元反查节点, 在 4 万节点量级上既慢又易踩 API 差异。
close $rep
puts "__HW_DONE__"
