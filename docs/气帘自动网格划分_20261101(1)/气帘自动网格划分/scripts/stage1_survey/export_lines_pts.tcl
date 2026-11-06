# export_lines_pts.tcl — 把各 component 的线按参数均匀采样导出为点云（2026）
# 用途: 给 Python 侧渲染底图 / 做环几何基准 / 判断线是否为往返退化线 / 查缺口
# 用法: 改顶部 P(工作目录) / SRC(模型文件) / COMPS(comp_id 标签 列表) / NSEG(每段采样数)
#
# 输出格式 (每行一条线):
#   <TAG> <line_id> <length> <sp_x> <sp_y> <sp_z> <ep_x> <ep_y> <ep_z> | "x y z";"x y z";...
# 注意: 输出完整 3D 坐标(cab3 几何在 X-Y 平面, cab1 在 X-Z 平面), 由 Python 侧投影

if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }
set HM_IN "cab1.hm"
if {[info exists ::env(HM_IN)] && $::env(HM_IN) ne ""} { set HM_IN $::env(HM_IN) }
set SRC "$P/input/$HM_IN"
set OUT "$P/out/lines_pts.txt"
set COMPS  { {4 SEAM} {3 CAV} {2 BELT} }
# 环境变量用扁平 "cid tag cid tag ..." 形式传入(避免嵌套花括号被 Tcl 列表解析打散)
if {[info exists ::env(COMPS)] && $::env(COMPS) ne ""} {
    set COMPS {}
    foreach {cid tag} $::env(COMPS) { lappend COMPS [list $cid $tag] }
}
set NSEG 24

foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}
set fp [open $OUT w]
*readfile "$SRC"

# 采样: hm_getcoordinatesofpointsonline <line> <u>  u in [0,1]
# ★ 返回嵌套列表，必须循环解包；直接 lindex 会取到整个子列表
proc sample_line {ln nseg} {
    set pts {}
    for {set i 0} {$i <= $nseg} {incr i} {
        set u [expr {$i / double($nseg)}]
        set r [catch {hm_getcoordinatesofpointsonline $ln $u} v]
        if {$r != 0} { continue }
        set vv $v
        while {[llength $vv] == 1 && [llength [lindex $vv 0]] >= 3} { set vv [lindex $vv 0] }
        if {[llength $vv] >= 3} {
            lappend pts "[format %.4f [lindex $vv 0]] [format %.4f [lindex $vv 1]] [format %.4f [lindex $vv 2]]"
        }
    }
    return $pts
}

foreach cs $COMPS {
    set cid [lindex $cs 0]
    set tag [lindex $cs 1]
    *createmark lines 1 "by collector" $cid
    foreach ln [hm_getmark lines 1] {
        set sp [hm_getlinestartpoint $ln]
        set ep [hm_getlineendpoint $ln]
        set L "-"
        catch {set L [hm_linelength $ln]}
        set pts [sample_line $ln $NSEG]
        if {[llength $pts] == 0} {
            lappend pts "[format %.4f [lindex $sp 0]] [format %.4f [lindex $sp 1]] [format %.4f [lindex $sp 2]]"
            lappend pts "[format %.4f [lindex $ep 0]] [format %.4f [lindex $ep 1]] [format %.4f [lindex $ep 2]]"
        }
        puts $fp "$tag $ln $L [format %.4f [lindex $sp 0]] [format %.4f [lindex $sp 1]] [format %.4f [lindex $sp 2]] [format %.4f [lindex $ep 0]] [format %.4f [lindex $ep 1]] [format %.4f [lindex $ep 2]] | [join $pts {;}]"
    }
}
close $fp
puts "__HW_DONE__"
