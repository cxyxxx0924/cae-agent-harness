# geom_query.tcl — HM2026 原生 line 几何特征导出(辅助四分区判断)
# 对每条线: 长度/起点/终点/起终切线; 对每个端点重合的结点: hm_getlinelineangle 夹角;
# 对采样三点: hm_findcirclefromthreepoints 圆拟合(半径/圆心)
set WORKDIR $::env(WORKDIR)
set HMIN [expr {[info exists ::env(HM_IN)] ? $::env(HM_IN) : "curves.hm"}]
hm_framework loaduserprofile LsDyna Keyword971_R16.0
*readfile $WORKDIR/$HMIN

set out [open $WORKDIR/out/geom_features.txt w]
set nline 0
*createmark lines 1 all
set ids [hm_getmark lines 1]
puts $out "NLINES [llength $ids]"

foreach id $ids {
    set L [hm_linelength $id]
    set sp [hm_getlinestartpoint $id]
    set ep [hm_getlineendpoint $id]
    set ts [hm_getlinetgstartpoint $id]
    set te [hm_getlinetgendpoint $id]
    puts $out "LINE $id $L | $sp | $ep | $ts | $te"
    incr nline
}

# ---- 端点匹配找结点 ----
array set SP {}
array set EP {}
foreach id $ids {
    set SP($id) [hm_getlinestartpoint $id]
    set EP($id) [hm_getlineendpoint $id]
}
proc dist3 {a b} {
    set d 0
    foreach i {0 1 2} {
        set dd [expr {[lindex $a $i] - [lindex $b $i]}]
        set d [expr {$d + $dd*$dd}]
    }
    return [expr {sqrt($d)}]
}
set jn 0
set seen {}
foreach id $ids {
    foreach end {SP EP} {
        set p [set $end($id)]
        # 找其他线的任一端点与 p 距离 < 1.5 的
        foreach id2 $ids {
            if {$id2 == $id} { continue }
            if {[dist3 $p [set SP($id2)]] < 1.5 || [dist3 $p [set EP($id2)]] < 1.5} {
                set key "$id-$id2"
                set key2 "$id2-$id"
                if {[info exists seen($key)] || [info exists seen($key2)]} { continue }
                set seen($key) 1
                # 取两线端点均值作为交点
                set px [expr {([lindex $p 0] + [lindex [set SP($id2)] 0]) / 2.0}]
                if {[catch {hm_getlinelineangle $id $id2 $px [lindex $p 1] [lindex $p 2]} ang]} {
                    set ang -1
                }
                puts $out "JUNC $id $id2 $ang"
                incr jn
            }
        }
    }
}
puts $out "NJUNC $jn"

# ---- 三点圆拟合(采样起/中/终) ----
set nc 0
foreach id $ids {
    # 用起点、参数 0.5 处的切点坐标近似中点: hm_getlinetangentatcoordinate 给的是点+切线
    set p0 [hm_getlinestartpoint $id]
    set p1 [hm_getlineendpoint $id]
    if {[catch {hm_getlinetangentatcoordinate $id 0.5 0 0} mid]} {
        set mid [list [expr {([lindex $p0 0]+[lindex $p1 0])/2.0}] [expr {([lindex $p0 1]+[lindex $p1 1])/2.0}] 0]
    }
    set mx [lindex $mid 0]; set my [lindex $mid 1]
    if {[catch {hm_findcirclefromthreepoints [lindex $p0 0] [lindex $p0 1] $mx $my [lindex $p1 0] [lindex $p1 1]} circ]} {
        set circ "ERR"
    }
    puts $out "CIRC $id | $p0 | $mx $my | $p1 | $circ"
    incr nc
}
puts $out "NCIRC $nc"

close $out
puts "GEOMQUERY_DONE lines=$nline junc=$jn circ=$nc"
