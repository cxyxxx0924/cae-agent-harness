# make_comps.tcl v2 — NEW_CAB 四分区落地
#   read newcab.hm (828 lines in comp lines0) -> 新建 4 comp (BELT/CAVITY/SEAM/TETHER)
#   -> 按 newcab_class_lists.tcl 用 *movemark lines 1 <comp名> 搬线
#   -> 逐 comp id 集合校验 + write newcab_partitioned.hm
# 2026 hmbatch 铁律: 中文路径 -tcl 必挂; *movemark 第三参是 comp 名称不是 id;
#   *renamecollectorbyid 行为不可靠(实测改名失败且名字变 "11"), 不用重命名, 直接新建 comp.
if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }
hm_framework loaduserprofile LsDyna Keyword971_R16.0
*readfile $P/newcab.hm

set out [open "$P/out/make_comps_report.txt" w]
proc log {m} { upvar #0 out out; puts $out $m; flush $out }

source $P/out/newcab_class_lists.tcl

log "=== before ==="
*createmark comps 1 "all"
log "comps: [hm_getmark comps 1]"
*createmark lines 1 "all"
log "lines total: [llength [hm_getmark lines 1]]"

# ---- 1. 建 4 个 comp ----
foreach nm {BELT CAVITY SEAM TETHER} {
    set rr [catch {*createentity comps name=$nm} ee]
    log "createentity comps name=$nm -> r=$rr e=$ee"
}
*createmark comps 1 "all"
log "comps now: [hm_getmark comps 1]"

# ---- 2. 搬线（每 100 个 id 一块）----
proc moveids {nm idlist} {
    upvar #0 out out
    set n [llength $idlist]
    for {set i 0} {$i < $n} {incr i 100} {
        set chunk [lrange $idlist $i [expr {$i + 99}]]
        set r [catch {*createmark lines 1 "by id" {*}$chunk; *movemark lines 1 $nm} e]
        if {$r} { log "  MOVE FAIL $nm chunk@$i : $e"; return -1 }
    }
    return $n
}

log "=== moving ==="
log "BELT   moved=[moveids BELT   $BELT_IDS]   (expect $BELT_N)"
log "CAVITY moved=[moveids CAVITY $CAVITY_IDS]   (expect $CAVITY_N)"
log "SEAM   moved=[moveids SEAM   $SEAM_IDS]   (expect $SEAM_N)"
log "TETHER moved=[moveids TETHER $TETHER_IDS]   (expect $TETHER_N)"

# ---- 3. 逐 comp id 集合校验 ----
log "=== verify (id-set equality) ==="
set allok 1
proc vset {nm exp allokVar} {
    upvar #0 out out
    upvar 1 $allokVar allok
    *createmark lines 1 "by collector name" $nm
    set got [hm_getmark lines 1]
    set gs [lsort -integer $got]
    set es [lsort -integer $exp]
    if {$gs eq $es} {
        log "OK   $nm: [llength $got] lines, id-set identical to json"
    } else {
        set allok 0
        # 找差异
        set onlyg {}; set onlye {}
        foreach g $gs { if {[lsearch -exact $es $g] < 0} { lappend onlyg $g } }
        foreach e $es { if {[lsearch -exact $gs $e] < 0} { lappend onlye $e } }
        log "FAIL $nm: got=[llength $got] exp=[llength $es] onlyInHM={$onlyg} onlyInJson={$onlye}"
    }
}
vset BELT   $BELT_IDS   allok
vset CAVITY $CAVITY_IDS allok
vset SEAM   $SEAM_IDS   allok
vset TETHER $TETHER_IDS allok

# 原 comp 应为空
*createmark lines 1 "by collector name" lines0
log "lines0 leftover: [llength [hm_getmark lines 1]] (expect 0)"

log "ALL_OK=$allok"

# ---- 4. 存 .hm（先删旧文件, 否则 hmbatch 弹 Overwrite? 交互= FatalError）----
file delete -force $P/newcab_partitioned.hm
set rw [catch {*writefile $P/newcab_partitioned.hm 1} ew]
log "writefile newcab_partitioned.hm -> r=$rw e=$ew exists=[file exists $P/newcab_partitioned.hm]"
close $out
if {$rw || !$allok} { puts "__HW_FAIL__" } else { puts "__HW_DONE__" }
