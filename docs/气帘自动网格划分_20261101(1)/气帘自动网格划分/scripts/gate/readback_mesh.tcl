# Run in a fresh hmbatch process; export evidence without saving the input model.
set model $::env(MESH_HM)
set output [file join $::env(WORKDIR) out mesh_readback.txt]
hm_framework loaduserprofile LsDyna Keyword971_R16.0
*readfile $model
set fp [open $output w]
fconfigure $fp -encoding utf-8
puts $fp "HM_FILE $model"
*createmark nodes 1 all
foreach nid [hm_getmark nodes 1] {
    puts $fp "N $nid [hm_nodevalue $nid x] [hm_nodevalue $nid y] [hm_nodevalue $nid z]"
}
*createmark elems 1 all
foreach eid [hm_getmark elems 1] {
    set nodes [hm_getentityarray elems $eid nodes]
    if {[llength $nodes] < 3 || [llength $nodes] > 4} { close $fp; error "Expected shell element: $eid" }
    puts $fp "E $eid $nodes"
}
puts $fp "READBACK_DONE"
close $fp
puts "__HW_DONE__"
