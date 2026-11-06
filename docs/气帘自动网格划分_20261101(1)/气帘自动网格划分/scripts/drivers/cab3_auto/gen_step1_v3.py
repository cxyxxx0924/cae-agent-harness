# gen_step1_v3.py — Step1: 用正确闭合环(loops_v3.json)重建三环共形网格 (WORKDIR 参数化)
#   belt   : comp2 全 67 线(去266) + 桥线[773,815,814]  -> 含充气口凸舌
#   cavity : comp3 94 线(主环) + 3 小洞                  -> 含充气口凸舌
#   seam   : 3 环(同 v1)
# 拓扑: BLUE(布带外廓) 裁 L3(气腔) => SCAV + SBELT ; SCAV 再裁 3 缝环 + 3 小洞
import json, math
from collections import defaultdict

import os
_WD = (os.environ.get('WORKDIR') or './cab3').rstrip('/')
SRC = _WD + '/lines_pts_all.txt'
P = _WD
TOL = 0.8
EPS = 0.02


def key(pt):
    return (round(pt[0] / TOL), round(pt[1] / TOL))


raw = {}
for ln in open(SRC, encoding='utf-8', errors='replace'):
    if '|' not in ln:
        continue
    h, rest = ln.split('|', 1)
    p = h.split()
    if len(p) < 7:
        continue
    try:
        lid = int(p[1])
        sp = (float(p[3]), float(p[4])); ep = (float(p[5]), float(p[6]))
    except Exception:
        continue
    pts = []
    for s in rest.strip().split(';'):
        s = s.strip()
        if not s:
            continue
        a = s.split()
        if len(a) < 2:
            continue
        try:
            pts.append((float(a[0]), float(a[1])))
        except Exception:
            continue
    if pts:
        raw[lid] = (sp, ep, pts)

V3 = json.load(open(P + '/loops_v3.json'))
loops_old = json.load(open(P + '/cab3_loops.json'))


def orient_cyclic(order):
    seq = [(order[0], True)]
    prev_end = raw[order[0]][1]
    for lid in order[1:]:
        sp, ep, _ = raw[lid]
        d_sp = math.hypot(sp[0] - prev_end[0], sp[1] - prev_end[1])
        d_ep = math.hypot(ep[0] - prev_end[0], ep[1] - prev_end[1])
        if d_sp < 1e-6:
            fwd = True
        elif d_ep < 1e-6:
            fwd = False
        elif d_sp < TOL and d_ep < TOL:
            fwd = (d_sp <= d_ep)
        elif d_sp < TOL:
            fwd = True
        elif d_ep < TOL:
            fwd = False
        else:
            fwd = True
        seq.append((lid, fwd))
        prev_end = raw[lid][1] if fwd else raw[lid][0]
    return seq


def chain_from_seq(seq):
    chain = []
    for lid, fwd in seq:
        sp, ep, pts = raw[lid]
        for pt in (pts if fwd else pts[::-1]):
            if chain and math.hypot(pt[0] - chain[-1][0], pt[1] - chain[-1][1]) < EPS:
                continue
            chain.append(pt)
    return chain


def douglas_peucker(pts, eps):
    """pts: 闭合环(无重复首末点). 返回简化后的闭合环."""
    n = len(pts)
    if n < 3:
        return pts
    ext = list(pts) + [pts[0]]          # 闭合环按开链 DP: 首尾同点
    m = len(ext)
    keep = [False] * m
    keep[0] = True
    keep[m - 1] = True

    def d2(p, a, b):
        ax, ay = a; bx, by = b; px, py = p
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        if L < 1e-18:
            return (px - ax) ** 2 + (py - ay) ** 2
        t = ((px - ax) * dx + (py - ay) * dy) / L
        t = max(0.0, min(1.0, t))
        cx, cy = ax + t * dx, ay + t * dy
        return (px - cx) ** 2 + (py - cy) ** 2

    stack = [(0, m - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        a, b = ext[i], ext[j]
        dmax = -1.0; idx = -1
        for k in range(i + 1, j):
            d = d2(ext[k], a, b)
            if d > dmax:
                dmax = d; idx = k
        if dmax > eps * eps:
            keep[idx] = True
            stack.append((i, idx)); stack.append((idx, j))
    out = [ext[i] for i in range(m) if keep[i]]
    if len(out) > 1 and out[0] == out[-1]:
        out = out[:-1]
    return out


DP_EPS = 0.2


def simp(chain):
    c = douglas_peucker(chain, DP_EPS)
    return c


def closed_loop(order):
    ch = chain_from_seq(orient_cyclic(order))
    if math.hypot(ch[-1][0] - ch[0][0], ch[-1][1] - ch[0][1]) < 1e-3:
        ch = ch[:-1]
    return ch


belt_chain = simp(list(V3['belt']['pts']))
cav_chain = simp(list(V3['cavity']['pts']))
hole_chains = [simp(list(h['pts'])) for h in V3['holes']]
seam_chains = [simp(closed_loop(s)) for s in loops_old['seam']]

print('belt   npts=%d closed_gap=%.3f' % (len(belt_chain),
      math.hypot(belt_chain[0][0] - belt_chain[-1][0], belt_chain[0][1] - belt_chain[-1][1])))
print('cavity npts=%d' % len(cav_chain))
for i, h in enumerate(hole_chains):
    print('hole%d  npts=%d' % (i, len(h)))
for i, ch in enumerate(seam_chains):
    print('seam%d  npts=%d' % (i, len(ch)))

# =================== Tcl ===================


def pts_tcl(chain):
    return " ".join("{%.6f %.6f}" % (x, y) for (x, y) in chain)


PROC = r'''
proc surf_area {sid} { set a 0; catch {set a [hm_getareaofsurface surfaces $sid]}; return $a }
proc new_surfs {m0} {
  *createmark surfaces 1 all
  set ns {}
  foreach s [hm_getmark surfaces 1] { if {$s > $m0} { lappend ns $s } }
  return $ns
}
proc biggest {ids} {
  set b -1; set ba -1
  foreach s $ids { set a [surf_area $s]; if {$a > $ba} { set ba $a; set b $s } }
  return $b
}
proc build_loop {ptsVar lineListVar} {
  upvar $ptsVar pts
  upvar $lineListVar LL
  set nids {}
  foreach pt $pts {
    lassign $pt x y
    *createnode $x $y 0 0 0
    lappend nids [hm_entitymaxid nodes]
  }
  set M [llength $nids]
  for {set i 0} {$i < $M} {incr i} {
    set a [lindex $nids $i]
    if {$i < [expr {$M-1}]} { set b [lindex $nids [expr {$i+1}]] } else { set b [lindex $nids 0] }
    *createlist nodes 1 $a $b
    set r [catch {*linecreatefromnodes 1 0 150 5 179} e]
    if {$r==0} { lappend LL [hm_entitymaxid lines] }
  }
}
proc make_ring_surf {lnsVar tag} {
  upvar $lnsVar lns
  set i0 [hm_entitymaxid surfaces]
  eval "*createmark lines 1 $lns"
  set r [catch {*surfacesplineonlinesloop 1 1 0 1} e]
  set ns [new_surfs $i0]
  if {[llength $ns] == 0} { log "RING $tag SPLINE FAIL r=$r e=$e"; return [list -1 {}] }
  set s [lindex $ns 0]
  set l0 [hm_entitymaxid lines]
  *createmark surfaces 1 $s
  catch {*linefromsurfedgecomp surfaces 1 1}
  set es {}
  *createmark lines 1 all
  foreach ln [hm_getmark lines 1] { if {$ln > $l0} { lappend es $ln } }
  log "RING $tag surf=$s area=[format %.1f [surf_area $s]] edges=[llength $es]"
  return [list $s $es]
}
proc trim_by {surf lnsVar tag junkvar} {
  upvar $lnsVar lns
  upvar 1 $junkvar junk
  set m0 [hm_entitymaxid surfaces]
  *createmark surfaces 1 $surf
  eval "*createmark lines 2 $lns"
  set r [catch {*surfacemarksplitwithlines 1 2 0 13 0} e]
  set ns [new_surfs $m0]
  if {[llength $ns] == 0} { log "TRIM $tag FAIL r=$r e=$e"; return [list $surf -1] }
  set hole [biggest $ns]
  set body [biggest [concat [list $surf] $ns]]
  foreach s $ns { if {$s != $hole && $s != $body} { lappend junk $s } }
  log "TRIM $tag hole=$hole area=[format %.1f [surf_area $hole]] body=$body area=[format %.1f [surf_area $body]]"
  return [list $body $hole]
}
proc try_mesh {tag sid sz} {
  *createmark surfaces 1 $sid
  *elementorder 1
  *setedgedensitylinkwithaspectratio -1
  set e1 "-"; set r1 [catch {*interactiveremeshsurf 1 $sz 2 2 2 1 1} e1]
  set e2 "-"; set r2 [catch {*automesh 0 2 2} e2]
  catch {*storemeshtodatabase 1}
  *createmark elems 1 "by surface" $sid
  set es [hm_getmark elems 1]
  set nq 0; set nt 0
  foreach el $es {
    set nds [hm_getentityarray elems $el nodes]
    if {[llength $nds] == 4} { incr nq } elseif {[llength $nds] == 3} { incr nt }
  }
  log "MESH $tag surf=$sid sz=$sz elems=[llength $es] quad=$nq tria=$nt"
  return [llength $es]
}
'''

tcl = []
tcl.append('set P "%s"' % P)
tcl.append('foreach _kv {LsDyna Keyword971_R16.0} { if {![catch {eval hm_framework loaduserprofile $_kv}]} { break } }')
tcl.append('*readfile "%s/cab3.hm"' % P)
tcl.append('set rep [open "%s/cab3_step1_v3_report.txt" w]' % P)
tcl.append('proc log {m} { upvar #0 rep rep; puts $rep $m; flush $rep }')
tcl.append(PROC)
tcl.append('set MESHSIZE 5.0')
tcl.append('set SEAMSIZE 2.5')   # 缝线环为 1.8-2.3mm 窄带, 需细网格才能面积自洽
tcl.append('set EQTOL 0.05')
tcl.append('set junk {}')

# 3 缝环
tcl.append('set seam_pts [list %s]' % ' '.join('{%s}' % pts_tcl(ch) for ch in seam_chains))
tcl.append('set seam_ids {}; set seam_edges {}')
tcl.append('for {set i 0} {$i < [llength $seam_pts]} {incr i} {')
tcl.append('  set sp [lindex $seam_pts $i]')
tcl.append('  set L {}; build_loop sp L')
tcl.append('  lassign [make_ring_surf L "seam$i"] sid es')
tcl.append('  if {$sid > 0} { lappend seam_ids $sid; lappend seam_edges $es }')
tcl.append('}')
tcl.append('log "seam_ids=$seam_ids"')

# 气腔主环
tcl.append('set cav_pts {%s}' % pts_tcl(cav_chain))
tcl.append('set cavL {}; build_loop cav_pts cavL')
tcl.append('lassign [make_ring_surf cavL "L3"] SL3 l3edges')
tcl.append('if {$SL3 <= 0} { log "SL3 FAIL"; close $rep; puts "__HW_FAIL__"; exit 1 }')

# 布带外廓
tcl.append('set belt_pts {%s}' % pts_tcl(belt_chain))
tcl.append('set beltL {}; build_loop belt_pts beltL')
tcl.append('lassign [make_ring_surf beltL "BLUE"] SBLUE bedges')
tcl.append('if {$SBLUE <= 0} { log "SBLUE FAIL"; close $rep; puts "__HW_FAIL__"; exit 1 }')

# BLUE 裁 L3 => SCAV + SBELT
tcl.append('lassign [trim_by $SBLUE l3edges "L3" junk] SCAV dummy')
tcl.append('set SBELT -1; set ba -1')
tcl.append('*createmark surfaces 1 all')
tcl.append('foreach s [hm_getmark surfaces 1] {')
tcl.append('  if {$s == $SCAV || $s == $SL3} { continue }')
tcl.append('  if {[lsearch $seam_ids $s] >= 0} { continue }')
tcl.append('  set a [surf_area $s]')
tcl.append('  if {$a > $ba} { set ba $a; set SBELT $s }')
tcl.append('}')
tcl.append('log "SCAV=$SCAV area=[format %.1f [surf_area $SCAV]] SBELT=$SBELT area=[format %.1f [surf_area $SBELT]]"')

# SCAV 裁 3 缝环(缝环面保留并网格化)
tcl.append('set seam_hole_ids {}')
tcl.append('for {set i 0} {$i < [llength $seam_ids]} {incr i} {')
tcl.append('  set sid [lindex $seam_ids $i]; set es [lindex $seam_edges $i]')
tcl.append('  if {$sid <= 0} { continue }')
tcl.append('  lassign [trim_by $SCAV es "SEAM_$i" junk] SCAV hole')
tcl.append('  lappend seam_hole_ids $hole')
tcl.append('}')

# SCAV 裁 3 小洞(直接删除)
tcl.append('set hole_pts [list %s]' % ' '.join('{%s}' % pts_tcl(h) for h in hole_chains))
tcl.append('for {set i 0} {$i < [llength $hole_pts]} {incr i} {')
tcl.append('  set sp [lindex $hole_pts $i]')
tcl.append('  set L {}; build_loop sp L')
tcl.append('  lassign [trim_by $SCAV L "SMALLHOLE_$i" junk] SCAV hh')
tcl.append('  lappend junk $hh')
tcl.append('}')
tcl.append('log "FINAL SCAV=$SCAV area=[format %.1f [surf_area $SCAV]] seam_holes=$seam_hole_ids"')

# 删多余面
tcl.append('lappend junk $SL3')
tcl.append('foreach s $seam_ids { lappend junk $s }')
tcl.append('if {[llength $junk] > 0} {')
tcl.append('  *createmark surfaces 1 [lindex $junk 0]')
tcl.append('  foreach s [lrange $junk 1 end] { *appendmark surfaces 1 $s }')
tcl.append('  if {[hm_marklength surfaces 1] > 0} { catch {*deletemark surfaces 1} }')
tcl.append('}')
tcl.append('*createmark surfaces 1 all')
tcl.append('set keep {}')
tcl.append('foreach s [hm_getmark surfaces 1] { lappend keep [format "%s(%.0f)" $s [surf_area $s]] }')
tcl.append('log "KEEP: $keep"')

# 网格 — cav/belt 用交互式重网格(保共形), 尺寸由 MESHSIZE 控制
# 缝线环窄带(1.8-2.3mm)必须细网格(SEAMSIZE=2.5)才能面积自洽
MESHSIZE = float(__import__('sys').argv[1]) if len(__import__('sys').argv) > 1 else 3.0
tcl.append('set si 0')
tcl.append('foreach s $seam_hole_ids { set n [try_mesh "seam$si" $s $SEAMSIZE]; if {$n == 0} { try_mesh "seam$si-3mm" $s 3.0 }; incr si }')
tcl.append('try_mesh cav $SCAV %s' % MESHSIZE)
tcl.append('try_mesh belt $SBELT $MESHSIZE')

# 共节点
tcl.append('*createmark nodes 1 all')
tcl.append('set nn0 [hm_marklength nodes 1]')
tcl.append('set e "-"; set r [catch {*equivalence2 $EQTOL} e]')
tcl.append('*createmark nodes 1 all')
tcl.append('set nn1 [hm_marklength nodes 1]')
tcl.append('log "equivalence2 $EQTOL: r=$r nodes $nn0 -> $nn1"')

# 导出
tcl.append('set fo [open "$P/cab3_step1_v3_mesh.txt" w]')
tcl.append('set allnodes {}')
tcl.append('set si 0')
tcl.append('foreach s $seam_hole_ids {')
tcl.append('  *createmark elems 1 "by surface" $s')
tcl.append('  foreach el [hm_getmark elems 1] { set nds [hm_getentityarray elems $el nodes]; puts $fo "S seam$si $el $nds"; foreach nd $nds { lappend allnodes $nd } }')
tcl.append('  incr si')
tcl.append('}')
tcl.append('*createmark elems 1 "by surface" $SCAV')
tcl.append('foreach el [hm_getmark elems 1] { set nds [hm_getentityarray elems $el nodes]; puts $fo "S cav $el $nds"; foreach nd $nds { lappend allnodes $nd } }')
tcl.append('*createmark elems 1 "by surface" $SBELT')
tcl.append('foreach el [hm_getmark elems 1] { set nds [hm_getentityarray elems $el nodes]; puts $fo "S belt $el $nds"; foreach nd $nds { lappend allnodes $nd } }')
tcl.append('set uniq [lsort -integer -unique $allnodes]')
tcl.append('foreach nd $uniq { puts $fo "N $nd [hm_nodevalue $nd x]" }')
tcl.append('close $fo')
tcl.append('log "EXPORT nodes=[llength $uniq]"')
tcl.append('close $rep')
tcl.append('puts "__HW_DONE__"')

open(P + '/cab3_step1_v3.tcl', 'w').write("\n".join(tcl))
print('wrote cab3_step1_v3.tcl (MESHSIZE=%s)' % MESHSIZE)
