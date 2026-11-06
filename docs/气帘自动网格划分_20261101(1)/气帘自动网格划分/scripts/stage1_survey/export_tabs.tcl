# 导出 comp4 (拉带) 全部线的采样点与端点
foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}
if {[info exists ::env(WORKDIR)]} { set P $::env(WORKDIR) } else { set P "." }
set fo [open "$P/out/tabs_lines_pts.txt" w]
*readfile "$P/input/cab1.hm"
*createmark comps 1 "all"
foreach cid [hm_getmark comps 1] {
    puts $fo "COMP $cid [hm_getvalue comps id=$cid dataname=name]"
}
*createmark lines 1 "by collector" 5
set lns [hm_getmark lines 1]
puts $fo "COMP5_TABS lines=[llength $lns]"
foreach ln $lns {
    set L [hm_linelength $ln]
    set sp [hm_getlinestartpoint $ln]
    set ep [hm_getlineendpoint $ln]
    set tp [hm_getlinetype $ln]
    set pts {}
    for {set i 0} {$i <= 20} {incr i} {
        set r [catch {hm_getcoordinatesofpointsonline $ln [expr {$i/20.0}]} v]
        if {$r == 0} {
            set vv $v
            while {[llength $vv] == 1 && [llength [lindex $vv 0]] >= 3} { set vv [lindex $vv 0] }
            lappend pts "[format %.3f [lindex $vv 0]] [format %.3f [lindex $vv 2]]"
        }
    }
    puts $fo "L $ln len=[format %.2f $L] type=$tp sp=[format {%.2f %.2f} [lindex $sp 0] [lindex $sp 2]] ep=[format {%.2f %.2f} [lindex $ep 0] [lindex $ep 2]] | [join $pts {;}]"
}
close $fo
puts "__HW_DONE__"
