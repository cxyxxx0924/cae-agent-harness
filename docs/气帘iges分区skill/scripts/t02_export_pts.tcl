# t02_export_pts.tcl — 导出全部曲线采样点 (2026 hmbatch)
#   输入: $WORKDIR/curves.hm (IGS 导入后的全部线, 通常挤在 1 个 comp)
#   输出: $WORKDIR/out/lines_pts.txt (渲染底图用, 每条线 32 段采样)

set P $::env(WORKDIR)
set SRC "$P/curves.hm"
set OUT "$P/out/lines_pts.txt"
set NSEG 32

foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {LsDyna} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}

set fp [open $OUT w]
*readfile "$SRC"

# 采样: hm_getcoordinatesofpointsonline <line> <u>  u in [0,1]
proc sample_line {ln nseg} {
    set pts {}
    for {set i 0} {$i <= $nseg} {incr i} {
        set u [expr {$i / double($nseg)}]
        set r [catch {hm_getcoordinatesofpointsonline $ln $u} v]
        if {$r != 0} { continue }
        set vv $v
        while {[llength $vv] == 1 && [llength [lindex $vv 0]] >= 3} { set vv [lindex $vv 0] }
        if {[llength $vv] >= 3} {
            lappend pts "[format %.3f [lindex $vv 0]] [format %.3f [lindex $vv 1]] [format %.3f [lindex $vv 2]]"
        }
    }
    return $pts
}

*createmark lines 1 "all"
set lns [hm_getmark lines 1]
puts "total lines: [llength $lns]"
foreach ln $lns {
    set sp [hm_getlinestartpoint $ln]
    set ep [hm_getlineendpoint $ln]
    set L "-"
    catch {set L [hm_linelength $ln]}
    set pts [sample_line $ln $NSEG]
    if {[llength $pts] == 0} {
        lappend pts "[format %.3f [lindex $sp 0]] [format %.3f [lindex $sp 1]] [format %.3f [lindex $sp 2]]"
        lappend pts "[format %.3f [lindex $ep 0]] [format %.3f [lindex $ep 1]] [format %.3f [lindex $ep 2]]"
    }
    puts $fp "L $ln $L [format %.3f [lindex $sp 0]] [format %.3f [lindex $sp 1]] [format %.3f [lindex $sp 2]] [format %.3f [lindex $ep 0]] [format %.3f [lindex $ep 1]] [format %.3f [lindex $ep 2]] | [join $pts {;}]"
}
close $fp
puts "__HW_DONE__"
