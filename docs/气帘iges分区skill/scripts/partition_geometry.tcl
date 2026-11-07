# Trial surfaces are confined to the independent readback process; never save them.
namespace eval partition_geometry {}

proc partition_geometry::quote {value} {
    return "\"[string map [list \\ \\\\ \" \\\" \n \\n \r \\r \t \\t] $value]\""
}

proc partition_geometry::new_surfaces {previous} {
    *createmark surfaces 1 all
    set result {}
    foreach sid [hm_getmark surfaces 1] { if {$sid > $previous} { lappend result $sid } }
    return $result
}

proc partition_geometry::area {sid} {
    set value [hm_getareaofsurface surfaces $sid]
    if {![string is double -strict $value] || !($value > 0) || $value == Inf} { error "Invalid surface area: $sid ($value)" }
    return $value
}

proc partition_geometry::endpoints {lines tolerance} {
    set points {}; set counts {}; set ids {}
    foreach lid $lines {
        foreach point [list [hm_getlinestartpoint $lid] [hm_getlineendpoint $lid]] {
            set found -1; set index 0
            foreach other $points {
                set distance 0.0
                foreach a $point b $other { set distance [expr {$distance + ($a-$b)*($a-$b)}] }
                if {$distance <= $tolerance*$tolerance} { set found $index; break }
                incr index
            }
            if {$found < 0} {
                lappend points $point; lappend counts 1; lappend ids [list $lid]
            } else {
                lset counts $found [expr {[lindex $counts $found] + 1}]
                lset ids $found [concat [lindex $ids $found] $lid]
            }
        }
    }
    set free {}; set closed [expr {[llength $lines] > 0}]
    for {set i 0} {$i < [llength $points]} {incr i} {
        if {[lindex $counts $i] % 2} { set closed 0 }
        if {[lindex $counts $i] == 1} {
            lappend free [format {{"line_ids":[%s],"point":[%s]}} [join [lindex $ids $i] ,] [join [lindex $points $i] ,]]
        }
    }
    return [list $closed "\[[join $free ,]\]"]
}

proc partition_geometry::edges {sid} {
    set previous [hm_entitymaxid lines]
    *createmark surfaces 1 $sid
    *linefromsurfedgecomp surfaces 1 1
    *createmark lines 1 all
    set lines {}
    foreach lid [hm_getmark lines 1] { if {$lid > $previous} { lappend lines $lid } }
    return $lines
}

proc partition_geometry::surface {lines role} {
    if {![llength $lines]} { error "Missing $role outline" }
    set previous [hm_entitymaxid surfaces]
    *createmark lines 1 "by id" {*}$lines
    *surfacesplineonlinesloop 1 1 0 1
    set surfaces [new_surfaces $previous]
    if {[llength $surfaces] != 1} { error "$role outline produced [llength $surfaces] surfaces; check open chains, seal lines and stray symbols" }
    return [lindex $surfaces 0]
}

proc partition_geometry::measure {belt_lines cavity_lines} {
    set cavity [surface $cavity_lines CAVITY]
    set cavity_area [area $cavity]
    set cavity_edges [edges $cavity]
    lassign [endpoints $cavity_edges 0.001] cavity_closed unused
    set outer [surface $belt_lines BELT]
    set outer_area [area $outer]
    lassign [endpoints [edges $outer] 0.001] outer_closed unused
    if {!$outer_closed || !$cavity_closed} { error "Trial surface boundary is not closed" }
    if {$outer_area <= $cavity_area} { error "CAVITY area must be smaller than the BELT outer area" }
    set pieces {}
    foreach edge $cavity_edges {
        set previous [hm_entitymaxid surfaces]
        *createmark surfaces 1 $outer
        *createmark lines 2 $edge
        if {[catch {*surfacemarksplitwithlines 1 2 0 13 0}]} { continue }
        set created [new_surfaces $previous]
        if {[llength $created]} { set pieces [concat $outer $created]; break }
    }
    if {[llength $pieces] != 2} { error "CAVITY did not split the BELT outer surface into two regions" }
    lassign $pieces first second
    set a [area $first]; set b [area $second]
    if {abs($a-$cavity_area) < abs($b-$cavity_area)} {
        set cut_cavity_area $a; set belt_area $b
    } else {
        set cut_cavity_area $b; set belt_area $a
    }
    set tolerance [expr {max(1.0, $outer_area*0.001)}]
    if {abs($a+$b-$outer_area) > $tolerance || abs($cut_cavity_area-$cavity_area) > $tolerance || abs($belt_area-($outer_area-$cavity_area)) > $tolerance} {
        error "Area conservation failed: outer=$outer_area cavity=$cavity_area belt=$belt_area cut_cavity=$cut_cavity_area; check seal-line ownership and overlapping regions"
    }
    foreach sid $pieces {
        lassign [endpoints [edges $sid] 0.001] closed unused
        if {!$closed} { error "Cut surface boundary is not closed: $sid" }
    }
    return [format {{"outer_area":%.9g,"cavity_area":%.9g,"belt_area":%.9g,"cut_cavity_area":%.9g,"belt_boundary_closed":true,"cavity_boundary_closed":true}} $outer_area $cavity_area $belt_area $cut_cavity_area]
}

proc partition_geometry::run {model output} {
    *createmark lines 1 "by collector name" BELT
    set belt [hm_getmark lines 1]
    *createmark lines 1 "by collector name" CAVITY
    set cavity [hm_getmark lines 1]
    set metrics "{}"; set failures {}; set diagnostics {}
    set failed [catch {
        foreach role {BELT CAVITY} lines [list $belt $cavity] {
            lassign [endpoints $lines 0.8] closed free
            lappend diagnostics "[quote $role]:$free"
        }
        measure $belt $cavity
    } result]
    if {$failed} { lappend failures [quote $result] } else { set metrics $result }
    set overall [expr {$failed ? "FAIL" : "PASS"}]
    set fp [open $output w]
    fconfigure $fp -encoding utf-8
    puts $fp [format {{"schema":"cae.partition-geometry.v1","source_model":%s,"overall":"%s","metrics":%s,"failures":[%s],"raw_free_endpoints":{%s}}} [quote [file normalize $model]] $overall $metrics [join $failures ,] [join $diagnostics ,]]
    close $fp
    return $failed
}
