# t09_dump_comps.tcl — 导出「组件 -> 线 id 列表」为 JSON（金标准解构 / 结果回读通用）
#   输入: $WORKDIR/curves.hm   （也可以是任意已分区的 .hm）
#   输出: $WORKDIR/out/comp_lines.json
#   用法: WORKDIR=<dir> hmbatch -tcl t09_dump_comps.tcl
# 说明: 与 t02_export_pts.tcl 使用同一 line id 空间，故 comp 标签可直接与 lines_pts.txt 对齐。

set P $::env(WORKDIR)
set SRC "$P/curves.hm"
set OUT "$P/out/comp_lines.json"

foreach _kv {{LsDyna Keyword971_R16.0} {LsDyna Keyword971_R15.0} {LsDyna} {OptiStruct} {HyperMesh}} {
    if {![catch {eval hm_framework loaduserprofile $_kv}]} {
        if {[string length [hm_info templatefilename]] > 0} { break }
    }
}

*readfile "$SRC"

set fp [open $OUT w]
puts $fp "{"
*createmark comps 1 "all"
set cs [hm_getmark comps 1]
set first 1
foreach c $cs {
    set nm [hm_getcollectorname comps $c]
    *createmark lines 1 "by collector" $c
    set lns [hm_getmark lines 1]
    if {!$first} { puts $fp "," }
    set first 0
    puts -nonewline $fp "  \"$nm\": \["
    puts -nonewline $fp [join $lns ", "]
    puts $fp "\]"
}
puts $fp "}"
close $fp

puts "comps: [llength $cs]"
puts "comp_lines.json written: $OUT"
puts "__HW_DONE__"
