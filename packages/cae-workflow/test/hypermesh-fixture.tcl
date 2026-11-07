set ::mode [lindex $argv 1]
set ::env(WORKDIR) [lindex $argv 2]
set ::env(HM_OUT) partitioned.hm
set ::marks [dict create]
set ::surfaces [dict create]
set ::points [dict create 1 {{0 0 0} {100 0 0}} 2 {{100 0 0} {100 100 0}} 3 {{100 100 0} {0 100 0}} 4 {{0 100 0} {0 0 0}} 5 {{10 10 0} {90 10 0}} 6 {{90 10 0} {90 90 0}} 7 {{90 90 0} {10 90 0}} 8 {{10 90 0} {10 10 0}}]
if {$::mode eq "open"} { dict set ::points 8 {{10 90 0} {15 10 0}} }
proc hm_framework {args} {}
proc hm_info {args} { return "LsDyna fixture" }
proc *readfile {args} {}
proc hm_getvalue {args} { return [lindex {BELT CAVITY SEAM TETHER} [expr {[string range [lindex $args 1] 3 end]-1}]] }
proc *createmark {kind index args} {
    set method [lindex $args 0]
    if {$kind eq "comps"} { set ids {1 2 3 4}
    } elseif {$kind eq "surfaces" && $method eq "all"} { set ids [dict keys $::surfaces]
    } elseif {$kind eq "lines" && $method eq "all"} { set ids [dict keys $::points]
    } elseif {$kind eq "lines" && $method in {"by collector" "by collector name"}} {
        set collector [lindex $args 1]
        if {$collector in {1 BELT}} { set ids {1 2 3 4}
        } elseif {$collector in {2 CAVITY}} { set ids {5 6 7 8}
        } else { set ids {} }
    } elseif {$method eq "by id"} { set ids [lrange $args 1 end]
    } else { set ids $args }
    dict set ::marks $kind $index $ids
}
proc hm_getmark {kind index} { return [dict get $::marks $kind $index] }
proc hm_getlinestartpoint {lid} {
    if {$::mode eq "query_error" && $lid > 8} { error "Cannot read surface-edge endpoints" }
    return [lindex [dict get $::points $lid] 0]
}
proc hm_getlineendpoint {lid} { return [lindex [dict get $::points $lid] 1] }
proc hm_linelength {lid} {
    set distance 0
    foreach a [hm_getlinestartpoint $lid] b [hm_getlineendpoint $lid] { set distance [expr {$distance+($a-$b)*($a-$b)}] }
    return [expr {sqrt($distance)}]
}
proc hm_entitymaxid {kind} {
    set ids [expr {$kind eq "surfaces" ? [dict keys $::surfaces] : [dict keys $::points]}]
    return [expr {[llength $ids] ? [lindex [lsort -integer $ids] end] : 0}]
}
proc *surfacesplineonlinesloop {args} {
    if {$::mode eq "open"} { error "CAVITY open chain at L8: cannot construct a surface" }
    set lines [hm_getmark lines 1]
    set sid [expr {[hm_entitymaxid surfaces]+1}]
    dict set ::surfaces $sid [dict create area [expr {[lindex $lines 0] == 5 ? 6400 : 10000}] edges $lines]
}
proc hm_getareaofsurface {kind sid} { return [dict get $::surfaces $sid area] }
proc *linefromsurfedgecomp {args} {
    set sid [lindex [hm_getmark surfaces 1] 0]
    foreach lid [dict get $::surfaces $sid edges] {
        dict set ::points [expr {[hm_entitymaxid lines]+1}] [dict get $::points $lid]
    }
}
proc *surfacemarksplitwithlines {args} {
    if {$::mode eq "no_cut"} { return }
    set sid [lindex [hm_getmark surfaces 1] 0]
    if {$::mode ne "overlap"} { dict set ::surfaces $sid area [expr {$::mode eq "reversed_cut" ? 6400 : 3600}] }
    dict set ::surfaces [expr {[hm_entitymaxid surfaces]+1}] [dict create area [expr {$::mode eq "reversed_cut" ? 3600 : 6400}] edges {5 6 7 8}]
}
source [lindex $argv 0]
