# t07_make_comps.tcl — 四分区落地 (BELT/CAVITY/SEAM/TETHER)
#   read $WORKDIR/curves.hm (IGS 导入后的全部线, 通常挤在 1 个 comp lines0)
#   -> 新建 4 comp, 按 out/class_lists.tcl 用 *movemark lines 1 <comp名> 搬线
#   -> 逐 comp id 集合校验 + write $WORKDIR/partitioned.hm
# 2026 hmbatch 铁律: 中文路径 -tcl 必挂; *movemark 第三参是 comp 名称不是 id;
#   *renamecollectorbyid 行为不可靠(实测改名失败且名字变 "11"), 不用重命名, 直接新建 comp.
set P $::env(WORKDIR)
# 输入/输出 hm 文件名可用 env 覆盖, 默认 curves.hm / partitioned.hm
set HMIN  [expr {[info exists ::env(HM_IN)]  ? $::env(HM_IN)  : "curves.hm"}]
set HMOUT [expr {[info exists ::env(HM_OUT)] ? $::env(HM_OUT) : "partitioned.hm"}]
hm_framework loaduserprofile LsDyna Keyword971_R16.0
*readfile $P/$HMIN

set out [open "$P/out/make_comps_report.txt" w]
proc log {m} { upvar #0 out out; puts $out $m; flush $out }

source $P/out/class_lists.tcl

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

# ---- 5. 未分配线统一收入 lines0 (供 t08 排除, 避免 VERIFY_FAIL) ----
catch {*createentity comps name=lines0}
*createmark lines 1 "all"
set keep {}
foreach nm {BELT CAVITY SEAM TETHER} {
    *createmark lines 1 "by collector name" $nm
    lappend keep {*}[hm_getmark lines 1]
}
*createmark lines 1 "all"
set allids [hm_getmark lines 1]
set leftover {}
foreach l $allids {
    if {[lsearch -exact $keep $l] < 0} { lappend leftover $l }
}
set nleft [llength $leftover]
for {set i 0} {$i < $nleft} {incr i 100} {
    set chunk [lrange $leftover $i [expr {$i + 99}]]
    *createmark lines 1 "by id" {*}$chunk
    *movemark lines 1 lines0
}
log "lines0 (unassigned) moved: $nleft"

log "ALL_OK=$allok"

# ---- 4. 存 .hm（先删旧文件, 否则 hmbatch 弹 Overwrite? 交互= FatalError）----
file delete -force $P/partitioned.hm
set rw [catch {*writefile $P/$HMOUT 1} ew]
log "writefile $HMOUT -> r=$rw e=$ew exists=[file exists $P/$HMOUT]"
close $out
if {$rw || !$allok} { puts "__HW_FAIL__" } else { puts "__HW_DONE__" }
