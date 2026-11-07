# verify_partitioned.tcl — 独立回读校验 partitioned.hm
#   不复用写入脚本的任何假设: 重新 readfile, 逐 comp 数线 + 从线端点算 bbox
#   + 抽样比对线长/端点与分类前导出的 geom_features.txt
set P $::env(WORKDIR)
# 待校验 hm 文件名可用 env 覆盖, 默认 partitioned.hm
set HMF [expr {[info exists ::env(HM_OUT)] ? $::env(HM_OUT) : "partitioned.hm"}]
hm_framework loaduserprofile LsDyna Keyword971_R16.0
*readfile $P/$HMF

set out [open "$P/out/verify_partitioned.txt" w]
proc log {m} { upvar #0 out out; puts $out $m; flush $out }

# 期望值来自 p06 导出的 class_lists.tcl（分类真值的另一形态，不写死条数）
source $P/out/class_lists.tcl
array set EXP [list BELT $BELT_N CAVITY $CAVITY_N SEAM $SEAM_N TETHER $TETHER_N]
set EXPECT_TOTAL [expr {$BELT_N + $CAVITY_N + $SEAM_N + $TETHER_N}]

log "=== comps ==="
*createmark comps 1 "all"
set cs [hm_getmark comps 1]
log "comp ids: $cs"

set total 0
set fail 0
# v9: 90 条刻意不参与分区的线留在 lines0/DROPPED, 不计入分区总数
set UNASSIGNED {"lines0" "DROPPED" "dropped"}
foreach cid $cs {
    set nm [hm_getvalue comps id=$cid dataname=name]
    *createmark lines 1 "by collector" $cid
    set ids [hm_getmark lines 1]
    set n [llength $ids]
    log "--- comp id=$cid name=$nm lines=$n"
    if {$n == 0} { log "    (empty comp)" ; continue }
    if {[lsearch -exact $UNASSIGNED $nm] >= 0} {
        log "    (unassigned comp, excluded from partition total)"
        continue
    }
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
log "TOTAL lines = $total (expect $EXPECT_TOTAL)"
if {$total != $EXPECT_TOTAL} { set fail 1 }

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

source [file join [file dirname [info script]] partition_geometry.tcl]
if {[partition_geometry::run "$P/$HMF" "$P/out/partition_geometry.json"]} {
    log "GEOMETRY FAIL: see out/partition_geometry.json (open chains, seal lines, area overlap)"
    set fail 1
} else {
    log "GEOMETRY PASS: closed trial surfaces and BELT = outer - CAVITY"
}
log "VERIFY_FAIL=$fail"
close $out
if {$fail} { puts "__HW_FAIL__" } else { puts "__HW_DONE__" }
