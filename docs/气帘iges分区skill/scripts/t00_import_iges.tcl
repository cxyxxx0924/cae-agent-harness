# t00_import_iges.tcl — 原始 CAD (IGES/IGS/DXF) 导入 -> curves.hm  (HyperWorks 2026 hmbatch)
#
# 输入: 环境变量 IGES   = 原始图纸绝对路径 (.iges / .igs / .dxf / .step 等 HM 支持的格式)
#      环境变量 WORKDIR = 工作区绝对路径 (英文, 无中文! P40/P41)
#      环境变量 HM_IN   = 输出 hm 文件名, 默认 curves.hm
# 输出: $WORKDIR/$HM_IN  (全部曲线通常挤在 1 个 comp —— 正是本技能的适用场景)
#
# 2026 批处理铁律 (见 SKILL.md §9):
#   1) 必须先 hm_framework loaduserprofile LsDyna Keyword971_R16.0, 否则
#      "No user profile or template file loaded" / data-name "pid" is not valid
#   2) *writefile 前必须 file delete -force 目标文件, 否则 Overwrite? 弹窗
#      = 不可 catch 的 FatalError, 批处理直接挂死 (P35)
#   3) 批处理导入后只有 1 个 comp; 组件结构靠后续 Python 聚类恢复 (本技能的核心价值)

set P    $::env(WORKDIR)
set IGES $::env(IGES)
set HMIN [expr {[info exists ::env(HM_IN)] ? $::env(HM_IN) : "curves.hm"}]
set OUT  "$P/$HMIN"

# --- 0) 读文件: 优先 iges_altair, 失败退回通用 import ---
foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {LsDyna} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}
if {[string length [hm_info templatefilename]] == 0} {
    puts "FATAL: no user profile loaded"
    exit 1
}

set ok 0
if {![catch {*geomimport "iges_altair" "$IGES"} e1]} { set ok 1 }
if {!$ok} {
    if {[catch {*import "$IGES"} e2]} {
        puts "FATAL: import failed: $IGES"
        exit 1
    }
}

# --- 1) 统计 ---
*createmark lines 1 "all"
set n [llength [hm_getmark lines 1]]
*createmark components 1 "all"
set nc [llength [hm_getmark components 1]]
puts "IMPORT lines=$n comps=$nc"

# --- 2) 写盘 (先删旧文件, P35) ---
file delete -force "$OUT"
*writefile "$OUT" 1

set rp [open "$P/out/t00_import_report.txt" w]
puts $rp "SRC      $IGES"
puts $rp "OUT      $OUT"
puts $rp "lines    $n"
puts $rp "comps    $nc"
close $rp
puts "WROTE $OUT  (report: out/t00_import_report.txt)"
