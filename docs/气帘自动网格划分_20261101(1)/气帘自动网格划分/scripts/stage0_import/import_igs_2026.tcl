# import_igs_2026.tcl — IGS/CAD → HyperMesh 二进制 .hm (hmbatch 批处理, 2026/2020 通用)
#   用途: 流水线第 0 步。把客户 IGS 导成 .hm, 供后续 export/survey 脚本 *readfile 读入。
#   实测 (2026-10-20, hmbatch): *geomimport "iges_altair" <path> 可直接导入 338 条线;
#   但批处理导入把全部线放进【一个 comp】(名字=IGES 根组名), 不按 IGES 组自动建 component。
#   → 组件/分区结构由 Python 侧几何聚类恢复 (tabs_extract.py), 或先在 GUI 里整理好再存 .hm。
#
# 用法: 改下面 4 个路径变量, 然后
#   hmbatch.exe -tcl import_igs_2026.tcl -noconcurrent
# 输出: HMOUT(.hm 二进制) + 报告 out/import_igs_report.txt

# 工作目录 (必须全英文, 中文路径 -tcl 必挂, P6); 可用环境变量 WORKDIR 覆盖
if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }
set IGS   "$P/input/cab_hm1.iges"               ;# 输入 CAD (iges/step/x_t 皆可, 换 translator)
set TR    "iges_altair"                          ;# step_ct / iges_altair / parasolid_parasolid
set HMOUT "$P/input/cab1.hm"                     ;# 输出 .hm

# ---- 用户模板 (2026 铁律: 开头必须加载, 否则 data-name not valid) ----
foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {LsDyna} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}

set rep [open "$P/out/import_igs_report.txt" w]
proc log {m} { upvar #0 rep rep; puts $rep $m; flush $rep }
log "template=[hm_info templatefilename]"
log "igs=$IGS translator=$TR exists=[file exists $IGS]"

# ---- 导入 ----
set r [catch {*geomimport $TR $IGS} e]
log "geomimport -> r=$r e=$e"
if {$r} { close $rep; puts "__HW_FAIL__"; exit 1 }

# ---- 统计 ----
foreach t {comps lines surfaces points} {
    set rr [catch {*createmark $t 1 "all"; set n [llength [hm_getmark $t 1]]}]
    if {$rr} { set n ERR }
    log "$t=$n"
}
*createmark comps 1 "all"
foreach cid [hm_getmark comps 1] {
    set nm [hm_getvalue comps id=$cid dataname=name]
    *createmark lines 1 "by collector" $cid
    log "comp id=$cid name=$nm lines=[llength [hm_getmark lines 1]]"
}

# ---- 存 .hm (二进制) ----
set r2 [catch {*writefile $HMOUT 1} e2]
log "writefile $HMOUT -> r=$r2 e=$e2 exists=[file exists $HMOUT]"
close $rep
if {$r2} { puts "__HW_FAIL__" } else { puts "__HW_DONE__" }
