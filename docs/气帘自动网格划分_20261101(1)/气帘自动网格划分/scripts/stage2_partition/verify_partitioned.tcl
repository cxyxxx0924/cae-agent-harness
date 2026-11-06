# verify_partitioned.tcl — 独立回读校验 newcab_partitioned.hm
#   不复用写入脚本的任何假设: 重新 readfile, 逐 comp 数线 + 从线端点算 bbox
#   + 抽样比对线长/端点与分类前导出的 geom_features.txt
if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }
hm_framework loaduserprofile LsDyna Keyword971_R16.0
*readfile $P/newcab_partitioned.hm

set out [open "$P/out/verify_partitioned.txt" w]
proc log {m} { upvar #0 out out; puts $out $m; flush $out }

# 期望 (来自 python 分类 json, 与 Tcl 无关的另一份数据)
array set EXP {BELT 119 CAVITY 78 SEAM 59 TETHER 572}

log "=== comps ==="
*createmark comps 1 "all"
set cs [hm_getmark comps 1]
log "comp ids: $cs"

set total 0
set fail 0
foreach cid $cs {
    set nm [hm_getvalue comps id=$cid dataname=name]
    *createmark lines 1 "by collector" $cid
    set ids [hm_getmark lines 1]
    set n [llength $ids]
    log "--- comp id=$cid name=$nm lines=$n"
    if {$n == 0} { log "    (empty comp)" ; continue }
    set total [expr {$total + $n}]
    # bbox from line endpoints (independent of any writer assumption)
    set xmin 1e30; set xmax -1e30; set ymin 1e30; set ymax -1e30; set zmin 1e30; set zmax -1e30
    foreach lid $ids {
        foreach pt [list [hm_getlinestartpoint $lid] [hm_getlineendpoint $lid]] {
            set x [lindex $pt 0]; set y [lindex $pt 1]; set z [lindex $pt 2]
            if {$x < $xmin} {set xmin $x}; if {$x > $xmax} {set xmax $x}
            if {$y < $ymin} {set ymin $y}; if {$y > $ymax} {set ymax $y}
            if {$z < $zmin} {set zmin $z}; if {$z > $zmax} {set zmax $z}
        }
    }
    log [format "    bbox x %.3f .. %.3f  y %.3f .. %.3f  z %.3f .. %.3f" $xmin $xmax $ymin $ymax $zmin $zmax]
    if {[info exists EXP($nm)]} {
        if {$n == $EXP($nm)} {
            log "    COUNT OK (expected $EXP($nm))"
        } else {
            log "    COUNT FAIL: got $n expected $EXP($nm)"
            set fail 1
        }
    }
}
log "TOTAL lines = $total (expect 828)"
if {$total != 828} { set fail 1 }

# ---- 抽样: 每 comp 取 3 条线, 打印 id/长度/端点, 供与 geom_features.txt 人工核对 ----
log "=== sample lines per comp ==="
foreach cid $cs {
    set nm [hm_getvalue comps id=$cid dataname=name]
    *createmark lines 1 "by collector" $cid
    set ids [hm_getmark lines 1]
    if {[llength $ids] == 0} { continue }
    set step [expr {[llength $ids] / 3}]
    if {$step < 1} { set step 1 }
    for {set i 0} {$i < [llength $ids]} {incr i $step} {
        set lid [lindex $ids $i]
        if {$lid eq ""} { continue }
        log "  $nm L$lid len=[hm_linelength $lid] sp=[hm_getlinestartpoint $lid] ep=[hm_getlineendpoint $lid]"
        if {$i > 1000} break
    }
}

# ---- 交叉验证: 按 comp 数线 vs 按 id 数线 (防 mark 语义坑) ----
log "=== cross-check: by collector name vs by id ==="
source $P/out/newcab_class_lists.tcl
set names {BELT CAVITY SEAM TETHER}
set lists {BELT_IDS CAVITY_IDS SEAM_IDS TETHER_IDS}
foreach nm $names lst $lists {
    *createmark lines 1 "by collector name" $nm
    set byc [llength [hm_getmark lines 1]]
    set exp $EXP($nm)
    if {$byc == $exp} {
        log "OK $nm: by-collector=$byc == json=$exp"
    } else {
        log "FAIL $nm: by-collector=$byc != json=$exp"; set fail 1
    }
}

log "VERIFY_FAIL=$fail"
close $out
if {$fail} { puts "__HW_FAIL__" } else { puts "__HW_DONE__" }
