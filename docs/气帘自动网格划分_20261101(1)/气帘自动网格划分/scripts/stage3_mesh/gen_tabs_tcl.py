"""拉带建面 Tcl 生成器: tabs_polys.json → build_tabs_2026.tcl
每片: 顶点 createnode(Y=-1) -> 段间建线 -> spline 建面 -> automesh 5mm
凸台上下片(BOSS up/dn) 共享膝弦线 (同节点对只建一次线) 且放入同一次 automesh
  => HM 对共享拓扑边在一次 meshing 里保证共节点
导出: out/tabs_mesh_2026.txt (T <tag> <eid> <nodes...>)
"""
import json, math

polys = json.load(open("out/tabs_polys.json"))
P = "."
Y_TAB = -1.0
MESHSIZE = 5.0

tcl = []
tcl.append(f'''# build_tabs_2026.tcl - tabs mesh (Y={Y_TAB})
foreach _kv {{{{LsDyna Keyword971_R16.0}}}} {{
    catch {{eval hm_framework loaduserprofile $_kv}}
}}
if {{[info exists ::env(WORKDIR)]}} {{ set P $::env(WORKDIR) }} else {{ set P {P} }}
set fo [open "$P/out/tabs_mesh_2026.txt" w]
set rep [open "$P/out/tabs_2026_report.txt" w]
proc log {{m}} {{ upvar #0 rep rep; puts $rep $m; flush $rep }}
set allnodes {{}}
*readfile "$P/input/cab1.hm"
*elementorder 1
*setedgedensitylinkwithaspectratio -1
''')

node_id = [0]
coord_map = {}   # (x,z) -> node id  (同坐标复用节点 => 上下片共享端点)

def emit_node(x, z):
    node_id[0] += 1
    nid = node_id[0]
    tcl.append(f"*createnode {x:.4f} {Y_TAB} {z:.4f} 0 0 0")
    return nid

# --- 逐片: 环顶点 -> 节点 ---
# groups: BOSS 的 up+dn 同组 (一次 automesh); 其它单片
face_defs = []   # (tag, nids, group)
group_of = {}
for k, r in enumerate(polys):
    if "up" in r:
        pieces = [("up", r["up"]), ("dn", r["dn"])]
        grp = f"g{k}"
    else:
        pieces = [("main", r["outer"])]
        grp = f"g{k}"
    for sub, ring in pieces:
        tag = f"tab{k}_{sub}" if "up" in r else (f"tabc{k}" if r["kind"] == "CURVE" else f"tabh{k}")
        nids = []
        for x, z in ring:
            found = coord_map.get((round(x, 6), round(z, 6)))
            if found is None:
                found = emit_node(x, z)
                coord_map[(round(x, 6), round(z, 6))] = found
            nids.append(found)
        face_defs.append((tag, nids, grp))

# --- 建线 (去重: 同节点对一条线 => 上下片共享膝弦线) ---
tcl.append("# ===== create lines (shared segments built once) =====")
tcl.append("set line_map [dict create]")
for tag, nids, grp in face_defs:
    n = len(nids)
    for i in range(n):
        a, b = nids[i], nids[(i + 1) % n]
        key = (min(a, b), max(a, b))
        tcl.append(f'if {{![dict exists $line_map {key[0]}_{key[1]}]}} {{')
        tcl.append(f"  *createlist nodes 1 {key[0]} {key[1]}")
        tcl.append("  *linecreatefromnodes 1 0 150 5 179")
        tcl.append(f'  dict set line_map {key[0]}_{key[1]} [hm_entitymaxid lines]')
        tcl.append("}")

# --- 建面 (每片 spline, 记录 surf id 到变量) ---
tcl.append("# ===== create surfaces =====")
for tag, nids, grp in face_defs:
    n = len(nids)
    segs = []
    for i in range(n):
        a, b = nids[i], nids[(i + 1) % n]
        segs.append(f"[dict get $line_map {min(a,b)}_{max(a,b)}]")
    tcl.append(f'''# surface {tag}
set flines_{tag} [list {' '.join(segs)}]
set sid_{tag} 0
if {{[llength $flines_{tag}] >= 3}} {{
  *createmark lines 1 [lindex $flines_{tag} 0]
  foreach ln [lrange $flines_{tag} 1 end] {{ *appendmark lines 1 $ln }}
  set i0 [hm_entitymaxid surfaces]
  set r [catch {{*surfacesplineonlinesloop 1 1 0 1}} e]
  *createmark surfaces 1 all
  foreach s [hm_getmark surfaces 1] {{ if {{$s > $i0}} {{ set sid_{tag} $s }} }}
  if {{$sid_{tag} == 0}} {{ log "{tag}: SPLINE FAIL r=$r e=$e" }}
}} else {{ log "{tag}: too few lines" }}
''')

# --- 逐面 automesh (分组版在批处理下只网格化首个面, 故改逐面;
#     共享膝弦边的共节点由 1) 同线确定性离散 2) 组装端坐标去重 双保险) ---
tcl.append("# ===== mesh per surface =====")
for tag, nids, grp in face_defs:
    tcl.append(f'''
set s $sid_{tag}
if {{$s != 0}} {{
  *createmark surfaces 1 $s
  catch {{*interactiveremeshsurf 1 {MESHSIZE} 2 2 2 1 1}}
  catch {{*automesh 0 2 2}}
  catch {{*storemeshtodatabase 1}}
  *createmark elems 1 "by surface" $s
  set ne [llength [hm_getmark elems 1]]
  log "{tag}: surf=$s elems=$ne"
  *createmark elems 1 "by surface" $s
  foreach el [hm_getmark elems 1] {{
    set nds [hm_getentityarray elems $el nodes]
    puts $fo "T {tag} $el $nds"
    foreach nd $nds {{ lappend allnodes $nd }}
  }}
}} else {{ log "{tag}: no surface" }}
''')

tcl.append(f'''
# ===== export nodes =====
foreach nd [lsort -integer -unique $allnodes] {{
  set x [hm_nodevalue $nd x]; set y [hm_nodevalue $nd y]; set z [hm_nodevalue $nd z]
  puts $fo "N $nd $x $y $z"
}}
close $fo
log "TABS DONE"
close $rep
puts "__HW_DONE__"
''')

open("scripts/build_tabs_2026.tcl", "w", encoding="utf-8").write("\n".join(tcl))
print(f"生成 scripts/build_tabs_2026.tcl: {len(face_defs)} 片, {node_id[0]} 节点")
