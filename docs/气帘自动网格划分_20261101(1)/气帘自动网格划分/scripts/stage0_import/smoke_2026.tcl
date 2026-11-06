# smoke_2026.tcl — HyperWorks 2026 hmbatch 通道冒烟测试
# 测的是【流水线真正用到的操作】, 不是花活:
#   ① 用户模板加载 (2026 铁律: 不加载全盘 data-name not valid)
#   ② *readfile 读 .hm + mark 计数 (无 hm_entitycount, 用 *createmark/hm_getmark)
#   ③ *surfacesplineonlinesloop spline 建面 (build_step1/build_tabs 主力)
#   ④ *automesh 网格化 + 元素计数
#   ⑤ 文件写通道 (报告/导出)
# 用法: hmbatch.exe -tcl smoke_2026.tcl -noconcurrent
#   可用环境变量: WORKDIR (工作目录) / MODEL (.hm 模型路径, 缺省用 $WORKDIR/input/cab1.hm)
# 合格标准: 报告 SMOKE_OK=1。
# 注意: *createentity elems 在 2026 hmbatch【不可用】(报 Invalid element config /
#   data-name not valid, 只能建 comps/nodes 且节点查不回) —— 建元素只能靠 automesh
#   或 GUI/MCP bridge (P33)。所以本冒烟不测 createentity。

if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }
if {[info exists ::env(MODEL)]} { set MODEL $::env(MODEL) } else { set MODEL "$P/input/cab1.hm" }
set OUT "$P/out/smoke_2026.txt"
set fp [open $OUT w]
proc log {m} { upvar #0 fp fp; puts $fp $m; flush $fp }

set ok 1

# ---- ① 用户模板 ----
foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {LsDyna} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}
log "template=[hm_info templatefilename]"
if {[string length [hm_info templatefilename]] == 0} {
    log "SMOKE_OK=0  (模板没加载: 2026 必须 hm_framework loaduserprofile LsDyna Keyword971_R16.0)"
    close $fp
    *answer yes
}

# ---- ② readfile + mark 计数 ----
if {![file exists $MODEL]} {
    log "SMOKE_OK=0  (模型不存在: $MODEL; 设 MODEL 环境变量或先跑 import_igs_2026.tcl)"
    close $fp
    *answer yes
}
if {[catch {*readfile $MODEL} e]} {
    log "readfile FAIL: $e  (K 文件不能 *readfile, 走 *feinput, P19)"
    log "SMOKE_OK=0"
    close $fp
    *answer yes
}
# automesh 全局设置 (2026 hmbatch 必须且必须在 readfile 之后: 否则 automesh 报
#   "Internal mesh error, try modifying element densities" 并静默出 0 元素)
*elementorder 1
*setedgedensitylinkwithaspectratio -1
proc mcount {t} { *createmark $t 1 "all"; return [llength [hm_getmark $t 1]] }
set nc [mcount comps]
set nl [mcount lines]
log "readfile OK: comps=$nc lines=$nl"
if {$nc < 1 || $nl < 1} { set ok 0; log "  !! 模型无 comp/线" }

# ---- ③ spline 建面 + ④ automesh (逐 comp 试, 成一个即可) ----
#   真实签名 (2020/2026 一致): *interactiveremeshsurf 1 <size> 2 2 2 1 1 ; *automesh 0 2 2
set meshed 0
*createmark comps 1 "all"
foreach cid [hm_getmark comps 1] {
    *createmark lines 1 "by collector" $cid
    set bn [llength [hm_getmark lines 1]]
    if {$bn < 3} { continue }
    set m0 [hm_entitymaxid surfaces]
    *createmark lines 1 "by collector" $cid
    if {[catch {*surfacesplineonlinesloop 1 1 0 1} e]} {
        log "  comp=$cid lines=$bn spline FAIL: $e"
        continue
    }
    *createmark surfaces 1 "all"
    set ns {}
    foreach s [hm_getmark surfaces 1] { if {$s > $m0} { lappend ns $s } }
    if {[llength $ns] == 0} { log "  comp=$cid lines=$bn spline 无新面"; continue }
    *createmark surfaces 1 $ns
    catch {*interactiveremeshsurf 1 8.0 2 2 2 1 1}
    catch {*automesh 0 2 2}
    catch {*storemeshtodatabase 1}
    *createmark elems 1 "all"
    set ne [llength [hm_getmark elems 1]]
    log "  comp=$cid lines=$bn spline OK surfaces=[llength $ns] elems_total=$ne"
    if {$ne >= 1} { set meshed 1; break }
}
if {!$meshed} { set ok 0; log "!! 没有任何 comp 能 spline+automesh 出元素" }

# ---- ⑤ 写通道 ----
set wf "$P/out/_smoke_write_test.txt"
if {[catch {set fw [open $wf w]; puts $fw "write-ok"; close $fw} e]} {
    log "write FAIL: $e"; set ok 0
} else {
    file delete $wf
    log "write OK"
}

log "SMOKE_OK=$ok"
close $fp
*answer yes
