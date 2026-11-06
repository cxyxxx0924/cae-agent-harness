# survey_comps.tcl — 组件清单 + spline 面积实证 (分区依据, 2026)
#   用途: 流水线第 1 步。回答"哪个 component 是哪个物理分区":
#        ① 逐 comp 列线数/线型; ② 用 comp 的线试 spline 闭合成面, 报面积。
#        cab1 实证: component1(7线)→115 万 mm²=布带外轮廓; component2→95.5 万=气腔;
#        component3(56线)→4627=缝线5区; component4(249线)→12.8 万=拉带相关。
#        → PID=component id, "面积/几何说话", 别信名字/颜色猜 (P28)。
#
# 用法: 改 P/SRC 后 hmbatch.exe -tcl survey_comps.tcl -noconcurrent
# 输出: out/survey_comps.txt

if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }
set HM_IN "cab1.hm"
if {[info exists ::env(HM_IN)] && $::env(HM_IN) ne ""} { set HM_IN $::env(HM_IN) }
set SRC "$P/input/$HM_IN"
set rep [open "$P/out/survey_comps.txt" w]
proc log {m} { upvar #0 rep rep; puts $rep $m; flush $rep }

foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {LsDyna} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}
log "template=[hm_info templatefilename] src=$SRC"

set r [catch {*readfile $SRC} e]
log "readfile -> r=$r e=$e"
if {$r} { close $rep; puts "__HW_FAIL__"; exit 1 }

proc surf_area {sid} { set a 0; catch {set a [hm_getareaofsurface surfaces $sid]}; return $a }
proc new_surfs {m0} {
  *createmark surfaces 1 all
  set ns {}
  foreach s [hm_getmark surfaces 1] { if {$s > $m0} { lappend ns $s } }
  return $ns
}

*createmark comps 1 "all"
set comps [hm_getmark comps 1]
log "comps=[llength $comps]"
foreach cid $comps {
    set nm [hm_getvalue comps id=$cid dataname=name]
    *createmark lines 1 "by collector" $cid
    set lns [hm_getmark lines 1]
    set types {}
    foreach ln $lns {
        set t ERR
        catch {set t [hm_getlinetype $ln]}
        lappend types $t
    }
    log "--- comp id=$cid name=$nm lines=[llength $lns] types=[join $types {,}]"
    # 试 spline 闭合成面 (成环的 comp 才有面积; 散线 comp 面积=0)
    set m0 [hm_entitymaxid surfaces]
    *createmark lines 1 "by collector" $cid
    set rr [catch {*surfacesplineonlinesloop 1 1 0 1} ee]
    set ns [new_surfs $m0]
    if {[llength $ns] > 0} {
        set tot 0
        foreach s $ns { set tot [expr {$tot + [surf_area $s]}] }
        log "    spline surf=[llength $ns] area_total=[format %.0f $tot]"
    } else {
        log "    spline FAIL r=$rr e=$ee (散线/未闭合成环)"
    }
}
close $rep
puts "__HW_DONE__"
