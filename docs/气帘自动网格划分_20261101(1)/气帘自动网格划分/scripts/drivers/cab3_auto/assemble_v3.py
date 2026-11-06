# assemble_v3.py — 组合 Step1(belt/seam/cav, v3 3mm 网格) + Step2(tether) 成 Y 分层 LS-DYNA K
# 坐标约定: K=(HM.x, thickness, HM.y)
#   PID2 belt Y=0 ; PID4 seam Y=0 ; PID3 cavity Y=+-0.5 双层 + washer 收口
#   PID5 tether Y=-1 ; 拉带附着边(贴近布带边界的节点) 焊接到布带边界节点(=>Y=0, 共节点)
# v3 新增: 充气口封口 —— 气腔自由边界中"不与布带/缝线共边且不属于 3 个小洞"的边
#          (凸舌尖端戳出布带的那段) 用捏合四边形把 cav_up/cav_low 缝起来, 属 PID3
import math, re, os
from collections import defaultdict, Counter
REFDIR = os.environ.get('REFDIR') or './ref'   # 参考模型目录: 需含 MAT.K + 03_Control_card.k
P = (os.environ.get('WORKDIR') or './cab3').rstrip('/') + '/'
S1 = P + 'cab3_step1_v3_mesh.txt'
TE = P + 'tether_mesh.txt'
OUT = P + 'cab3_full_v3.k'
SNAP_TOL = 12.0   # tether 边界节点 贴近布带边界 的吸附容差(mm)
HOLE_TOL = 0.6    # 判定自由边是否属于小洞的距离容差


def parse_mesh(path, want_tag=None):
    nodes = {}
    elems = []
    for ln in open(path, encoding='utf-8', errors='replace'):
        ln = ln.strip()
        if ln.startswith('N '):
            m = re.search(r'\{([^}]*)\}', ln)
            p = ln.split()
            nid = int(p[1])
            if m:
                c = m.group(1).split()
                nodes[nid] = (float(c[0]), float(c[1]), float(c[2]) if len(c) > 2 else 0.0)
            elif len(p) >= 4:
                nodes[nid] = (float(p[2]), float(p[3]), 0.0)
        elif ln.startswith('S '):
            p = ln.split()
            tag = p[1]; eid = int(p[2]); nds = [int(x) for x in p[3:]]
            if want_tag is None or tag == want_tag:
                elems.append((tag, eid, nds))
    return nodes, elems


s1_nodes, s1_elems = parse_mesh(S1)
t_nodes, t_elems = parse_mesh(TE)

# ---- 拓扑: 边 -> 所属 tag 集合 ----
edge = defaultdict(list)
for tag, eid, nds in s1_elems:
    k = len(nds)
    for i in range(k):
        a, b = nds[i], nds[(i + 1) % k]
        if a > b:
            a, b = b, a
        edge[(a, b)].append(tag)

cnt = defaultdict(Counter)
for (a, b), tags in edge.items():
    for t in tags:
        cnt[t][(a, b)] += 1
FREE = {t: set(e for e, c in cc.items() if c == 1) for t, cc in cnt.items()}
ALL = {t: set(cc) for t, cc in cnt.items()}

# ---- 布带边界 = 仅属于 belt 的边 ----
belt_bd = set()
for (a, b), tags in edge.items():
    if tags == ['belt']:
        belt_bd.add(a); belt_bd.add(b)
belt_bd_list = [n for n in belt_bd if n in s1_nodes]

# ---- tether 边界节点 ----
t_edge = Counter()
for tag, eid, nds in t_elems:
    k = len(nds)
    for i in range(k):
        a, b = nds[i], nds[(i + 1) % k]
        t_edge[(a, b) if a < b else (b, a)] += 1
t_bd = set()
for (a, b), c in t_edge.items():
    if c == 1:
        t_bd.add(a); t_bd.add(b)

# ---- Step1 -> K 节点映射(各 face 独立) ----
Y = {'belt': 0.0, 'seam': 0.0, 'cav_up': 0.5, 'cav_low': -0.5}
K = []
L = {}


def kid(m, h):
    key = (m, h)
    if key in L:
        return L[key]
    x, y, z = s1_nodes[h]
    nid = len(K) + 1
    K.append((x, Y[m], y))
    L[key] = nid
    return nid


Ke = []
for tag, eid, nds in s1_elems:
    if tag == 'belt':
        Ke.append((2, [kid('belt', n) for n in nds]))
    elif tag.startswith('seam'):
        Ke.append((4, [kid('seam', n) for n in nds]))
    elif tag == 'cav':
        Ke.append((3, [kid('cav_up', n) for n in nds]))
        Ke.append((3, [kid('cav_low', n) for n in nds]))

# ---- washer (cav<->seam / cav<->belt 收口过渡) ----
def washers(faceA, tagA, tagB='cav'):
    n = 0
    for (a, b), tags in edge.items():
        if tagA in tags and tagB in tags:
            ka = kid(faceA, a); kb = kid(faceA, b)
            ua = kid('cav_up', a); ub = kid('cav_up', b)
            la = kid('cav_low', a); lb = kid('cav_low', b)
            Ke.append((3, [ka, kb, ub, ua]))
            Ke.append((3, [la, lb, kb, ka]))
            n += 2
    return n


w_seam = washers('seam', 'seam0') + washers('seam', 'seam1') + washers('seam', 'seam2')
w_belt = washers('belt', 'belt')

# ---- 充气口封口: 气腔自由边界中未共边、且不属于小洞的边 -> 捏合四边形 ----
import json
V3 = json.load(open(P + 'loops_v3.json'))
hole_polys = [[tuple(q) for q in h['pts']] for h in V3['holes']]


def dist_pt_seg(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-18:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def poly_segs(poly):
    return [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]


HOLE_SEGS = []
for h in hole_polys:
    HOLE_SEGS.extend(poly_segs(h))


def on_hole(p):
    for a, b in HOLE_SEGS:
        if dist_pt_seg(p, a, b) <= HOLE_TOL:
            return True
    return False


shared = ALL['cav'] & (ALL['belt'] | ALL['seam0'] | ALL['seam1'] | ALL['seam2'])
port_edges = []
for (a, b) in FREE['cav']:
    if (a, b) in shared:
        continue
    mx = (s1_nodes[a][0] + s1_nodes[b][0]) / 2.0
    my = (s1_nodes[a][1] + s1_nodes[b][1]) / 2.0
    if on_hole((mx, my)):
        continue
    port_edges.append((a, b))
port_len = sum(math.hypot(s1_nodes[b][0] - s1_nodes[a][0],
                          s1_nodes[b][1] - s1_nodes[a][1]) for a, b in port_edges)
n_pinch = 0
for a, b in port_edges:
    ua = kid('cav_up', a); ub = kid('cav_up', b)
    la = kid('cav_low', a); lb = kid('cav_low', b)
    Ke.append((3, [ua, ub, lb, la]))
    n_pinch += 1

# ---- tether 节点映射 + 吸附到布带边界 ----
beltbd_k = {}
beltbd_xy = []
for n in belt_bd_list:
    k = kid('belt', n)
    beltbd_k[n] = k
    beltbd_xy.append((s1_nodes[n][0], s1_nodes[n][1], n, k))


def nearest_beltbd(x, y):
    best = None; bd = 1e18
    for bx, by, bn, bk in beltbd_xy:
        d = math.hypot(x - bx, y - by)
        if d < bd:
            bd = d; best = (bn, bk)
    return best, bd


tK = {}
taken_belt = set()
snapped = 0
for tn in sorted(t_nodes):
    x, y, z = t_nodes[tn]
    if tn in t_bd:
        (bn, bk), d = nearest_beltbd(x, y)
        if d <= SNAP_TOL and bn not in taken_belt:
            tK[tn] = bk; taken_belt.add(bn); snapped += 1
            continue
    nid = len(K) + 1
    K.append((x, -1.0, y))
    tK[tn] = nid

for tag, eid, nds in t_elems:
    Ke.append((5, [tK[n] for n in nds]))

# ---- 写 K ----
H = lambda s: "$# " + s
lines = []
lines.append('*KEYWORD')
lines.append('$ cab3 full deck v3: Step1(belt/seam/cav, 3mm) + Step2(tether)  Y-layered')
lines.append('$ coord: K=(HM.x, thickness, HM.y); PID2=belt Y0, PID3=cav Y+-0.5, PID4=seam Y0, PID5=tether Y-1')
lines.append('$ 充气口封口: %d 条捏合边(%.1fmm) -> %d 个 PID3 捏合四边形' % (len(port_edges), port_len, n_pinch))
lines.append('*NODE')
lines.append(H('  nid               x               y               z      tc      rc'))
for i, (x, y, z) in enumerate(K, 1):
    lines.append('%8d%16.6f%16.6f%16.6f%8.1f%8.1f' % (i, x, y, z, 0, 0))
lines.append('*ELEMENT_SHELL')
lines.append(H('  eid     pid      n1      n2      n3      n4      n5      n6      n7      n8'))
for i, (pid, nds) in enumerate(Ke, 1):
    n4 = nds[:4] + [0] * (4 - len(nds[:4]))
    lines.append('%8d%8d%8d%8d%8d%8d%8d%8d%8d%8d' % (i, pid, n4[0], n4[1], n4[2], n4[3], 0, 0, 0, 0))
parts = [(2, 'belt_PID2'), (3, 'cavity_PID3'), (4, 'seam_PID4'), (5, 'tether_PID5')]
lines.append('*PART')
lines.append(H('   pid     secid      mid     eosid      hgid      grav    adpopt      tmid'))
MATID = 84450005
for pid, name in parts:
    lines.append('$ %s' % name)
    lines.append('%10d%10d%10d%10d%10d%10d%10d%10d' % (pid, pid, MATID, 0, 0, 0, 0, 0))
for pid, name in parts:
    lines.append('*SECTION_SHELL_TITLE')
    lines.append(name)
    lines.append('*SECTION_SHELL')
    lines.append(H('   secid    elform      shrf      nip     propt    qririd     icrq      opt'))
    lines.append('%10d%10d%10.5f%10d%10d%10d%10d%10d' % (pid, 9, 0.83333, 1, 1, 0, 1, 0))
    lines.append(H('       t1        t2        t3        t4      nloc'))
    lines.append('%10.4f%10.4f%10.4f%10.4f%10d' % (0.3, 0.3, 0.3, 0.3, 0))
    lines.append(H('     beta1     beta2'))
    lines.append('%10.1f%10.1f' % (0.0, 90.0))
mat = open(os.path.join(REFDIR, 'MAT.K'), encoding='utf-8', errors='replace').read().splitlines()
want = False
for ln in mat:
    if ln.startswith('*MAT_FABRIC') or ln.startswith('*DEFINE_CURVE'):
        want = True
    elif ln.startswith('*END') or ln.startswith('*MAT_RIGID'):
        want = False
    if want:
        lines.append(ln)
ctl = open(os.path.join(REFDIR, '03_Control_card.k'), encoding='utf-8', errors='replace').read().splitlines()
started = False
for ln in ctl:
    if ln.startswith('*CONTROL_ACCURACY'):
        started = True
    elif ln.startswith('*END'):
        break
    if started:
        lines.append(ln)
lines.append('*END')
open(OUT, 'w').write('\n'.join(lines) + '\n')
print("wrote", OUT)
print("K nodes=", len(K), " K elems=", len(Ke))
print("washer quads: seam=%d belt=%d" % (w_seam, w_belt))
print("充气口封口: port_edges=%d len=%.1fmm pinch_quads=%d" % (len(port_edges), port_len, n_pinch))
print("tether elems=%d nodes=%d snapped=%d" % (len(t_elems), len(t_nodes), snapped))
print("elems by PID:", dict(Counter(p for p, _ in Ke)))
