# -*- coding: utf-8 -*-
"""
把工作文件的气帘 (cab1_60ms.k, 原始框架) 换装进参考模型 host:
  - 清算去年遗留的验证工装: 10x *BOUNDARY_SPC_SET (boss cap 全固定) + 10x *CONSTRAINED_NODAL_RIGID_BODY
  - 节点/单元重编号 +30M 防撞; 材料用参考 MAT.K (逐字一致, 丢弃 cab1 自带 MAT_FABRIC/曲线16-20)
  - cab1 自留曲线 10/12/13/14/15 重编号到 30M 段, AIRBAG 卡内曲线引用同步映射
  - 参考拉带 Spring_move.k 改接: 袋侧端点 -> 我们 9 个 boss cap 节点 (按坐标最近匹配)
  - 参考 03_Control_card.k 复制为 MOD: ENDTIM=2.0 (探针), D3PLOT=0.1
  - Vehicle.k 原样 (自带 袋-身 S2S: slave=SET_PART 2, 正好命中我们 set 2)
组装 main_swap.key = 03_Control_MOD + MAT.K + cab1_clean + Vehicle + Spring_swap
"""
import os, re, math

BASE = r'E:/work/AI_CAB'
REF  = BASE + '/Model_update_Move_Iter04/Model_update_Move_Iter04'
WK   = BASE + '/onekey'
OUT  = WK + '/run_swap'
NOFF = 30_000_000   # 节点重编号
EOFF = 30_000_000   # 单元重编号
KEEP_CURVES = (10, 12, 13, 14, 15)
CRV_MAP = {c: 30_000_000 + c for c in KEEP_CURVES}
DROP_EXACT = {'*KEYWORD', '*TITLE', '*END', '*PARAMETER', '*MAT_FABRIC',
              '*BOUNDARY_SPC_SET', '*CONSTRAINED_NODAL_RIGID_BODY'}
DROP_PREFIX = ('*CONTROL_', '*DATABASE_')

def is_int(t):
    try:
        int(t); return True
    except ValueError:
        return False

def is_nodeid(t):
    return is_int(t) and 1 <= int(t) <= 200_000

def kw_base(s):
    t = s.strip().split()
    if not t or not t[0].startswith('*'):
        return None
    return t[0].upper().split('_TITLE')[0]

# ============================================================
# 1) cab1 清洗 + 重编号
# ============================================================
our_nodes = {}          # native nid -> (x,y,z)
cap_sets = {}           # 900010..900018 -> [nid...]
lines = open(WK + '/cab1_60ms.k', errors='ignore').read().split('\n')
out, i, n = [], 0, len(lines)
stats = {'spc':0, 'cnrb':0, 'ctrl':0, 'curves_dropped':[], 'curves_kept':[]}
while i < n:
    s = lines[i]
    st = s.strip()
    if st.startswith('*'):
        kw = st.split()[0].upper()
        base = kw.split('_TITLE')[0]
        if kw in DROP_EXACT or any(kw.startswith(p) for p in DROP_PREFIX):
            # 整块丢弃: 关键字 + 数据行, 直到下一个关键字行
            if base == '*BOUNDARY_SPC_SET': stats['spc'] += 1
            if base == '*CONSTRAINED_NODAL_RIGID_BODY': stats['cnrb'] += 1
            if base.startswith('*CONTROL_') or base.startswith('*DATABASE_'): stats['ctrl'] += 1
            j = i + 1
            while j < n and not lines[j].strip().startswith('*'):
                j += 1
            i = j
            continue
        if base == '*NODE':
            out.append(s); i += 1
            while i < n and not lines[i].strip().startswith('*'):
                t = lines[i].strip()
                if t and not t.startswith('$'):
                    p = t.split(',')
                    try:
                        nid = int(p[0]); our_nodes[nid] = tuple(float(v) for v in p[1:4])
                        p[0] = str(nid + NOFF)
                        out.append(','.join(p))
                    except ValueError:
                        out.append(lines[i])
                i += 1
            continue
        if base == '*ELEMENT_SHELL':
            out.append(s); i += 1
            while i < n and not lines[i].strip().startswith('*'):
                t = lines[i].strip()
                if t and not t.startswith('$'):
                    p = t.split(',')
                    if p and is_int(p[0].strip()):
                        p[0] = str(int(p[0].strip()) + EOFF)
                        for k in range(2, len(p)):        # 跳过 field1=PID
                            tk = p[k].strip()
                            if is_nodeid(tk):
                                p[k] = str(int(tk) + NOFF)
                        out.append(','.join(p))
                    else:
                        out.append(lines[i])
                i += 1
            continue
        if base == '*SET_NODE_LIST':
            out.append(s); i += 1
            sid = None
            while i < n and not lines[i].strip().startswith('*'):
                t = lines[i].strip()
                if t and not t.startswith('$'):
                    p = t.split(',')
                    if any('.' in x for x in p[1:5]) and sid is None:
                        sid = int(p[0].strip().split('.')[0])
                        out.append(lines[i])              # 头卡: SID,0.,0.,0.,0.
                    else:
                        q = [str(int(x) + NOFF) if is_nodeid(x.strip()) else x for x in p]
                        out.append(','.join(q))
                        if sid is not None:
                            cap_sets.setdefault(sid, []).extend(int(x) for x in p if is_nodeid(x.strip()))
                i += 1
            continue
        if base == '*DEFINE_CURVE':
            blk = [s]; j = i + 1
            while j < n and not lines[j].strip().startswith('*'):
                blk.append(lines[j]); j += 1
            hdr = None
            for b in blk[1:]:
                bt = b.strip()
                if bt and not bt.startswith('$'):
                    hdr = bt; break
            sid = int(hdr.split(',')[0]) if hdr and is_int(hdr.split(',')[0].strip()) else None
            if sid in KEEP_CURVES:
                h2 = hdr.replace('&TTF', '')
                p = h2.split(',')
                p[0] = str(CRV_MAP[sid])
                out.append(blk[0])
                done_hdr = False
                for b in blk[1:]:
                    if not done_hdr and b.strip() == hdr:
                        out.append(','.join(p)); done_hdr = True
                    else:
                        out.append(b)
                stats['curves_kept'].append(sid)
            else:
                stats['curves_dropped'].append(sid)
            i = j
            continue
        # 其它保留卡: PART/SECTION/AIRBAG/CONTACT/SET_PART 原样 (AIRBAG 曲线引用映射)
        if base == '*AIRBAG_HYBRID_ID':
            out.append(s); i += 1
            while i < n and not lines[i].strip().startswith('*'):
                t = lines[i]
                if ',' not in t and len(t) >= 10:
                    # 定宽 10 字符字段, 原位替换曲线引用 (±10/12/13/14/15 -> ±30M+)
                    flds, r = [], t
                    for k in range(0, len(t), 10):
                        flds.append(t[k:k+10])
                    new = []
                    for f in flds:
                        ft = f.strip()
                        if is_int(ft):
                            v = int(ft)
                            if v in CRV_MAP:
                                new.append('%10d' % CRV_MAP[v]); continue
                            if -v in CRV_MAP:
                                new.append('%10d' % -CRV_MAP[-v]); continue
                        new.append(f)
                    out.append(''.join(new))
                else:
                    out.append(t)
                i += 1
            continue
        out.append(s); i += 1
        continue
    out.append(s); i += 1

cab_clean = '\n'.join(out) + '\n'
os.makedirs(OUT, exist_ok=True)
open(OUT + '/cab1_clean.k', 'w').write(cab_clean)
print('[cab1_clean] 节点 %d (重编号 +%d), SPC删%d, CNRB删%d, CONTROL/DATABASE删%d' %
      (len(our_nodes), NOFF, stats['spc'], stats['cnrb'], stats['ctrl']))
print('  曲线保留:', sorted(stats['curves_kept']), '-> 映射',
      {k: CRV_MAP[k] for k in sorted(stats['curves_kept'])})
print('  曲线丢弃:', sorted(x for x in stats['curves_dropped'] if x is not None), '(MAT.K 提供)')

# ============================================================
# 2) 参考节点表 (Vehicle / 5P-BAG) + Spring 改接
# ============================================================
def parse_nodes_robust(fn):
    d = {}; cur = False
    for ln in open(fn, errors='ignore'):
        s = ln.rstrip('\n')
        if s.startswith('*'):
            cur = s.strip().upper().startswith('*NODE'); continue
        if not cur: continue
        t = s.strip()
        if not t or t.startswith('$'): continue
        try:
            if ',' in t:
                p = t.split(',')
                d[int(p[0])] = tuple(float(v) for v in p[1:4])
            elif len(s) >= 56 and is_int(s[0:8].strip()):
                d[int(s[0:8])] = (float(s[8:24]), float(s[24:40]), float(s[40:56]))
            else:
                p = t.split()
                d[int(p[0])] = tuple(float(v) for v in p[1:4])
        except (ValueError, IndexError):
            pass
    return d

veh = parse_nodes_robust(REF + '/Vehicle.k')
bag5 = parse_nodes_robust(REF + '/5P-BAG_005.key')
print('[nodes] Vehicle %d, 5P-BAG %d' % (len(veh), len(bag5)))

# 参考 tether 袋侧/锚侧
spring_lines = open(REF + '/Spring_move.k', errors='ignore').read().split('\n')
beams, discs, cur_mode = [], [], None
for s in spring_lines:
    st = s.strip()
    if st.startswith('*'):
        cur_mode = st.split('_TITLE')[0].upper()
        continue
    if cur_mode == '*ELEMENT_BEAM' and st and not st.startswith('$') and len(s) >= 32:
        beams.append((int(s[0:8]), int(s[8:16]), int(s[16:24]), int(s[24:32])))
    if cur_mode == '*ELEMENT_DISCRETE' and st and not st.startswith('$') and len(s) >= 32:
        discs.append((int(s[0:8]), int(s[8:16]), int(s[16:24]), int(s[24:32])))
print('[Spring] beams %d, discretes %d' % (len(beams), len(discs)))

# 我们 9 个 cap (900010..900018; 900001 是已删除的工装散点集, 不参与)
cap_center = {}
for sid, nds in cap_sets.items():
    if not (900010 <= sid <= 900018): continue
    cs = [our_nodes[x] for x in nds if x in our_nodes]
    cap_center[sid] = (tuple(sum(c[k] for c in cs) / len(cs) for k in range(3)), nds)
print('[caps] %d 个: %s' % (len(cap_center), sorted(cap_center)))

ref_bag_nodes = sorted({b[2] for b in beams if b[2] in bag5} | {b[3] for b in beams if b[3] in bag5})
print('[Spring 袋侧节点] %s' % ref_bag_nodes)

# 贪心匹配(最近优先): 每个参考袋侧节点 -> 最近 cap, 不允许重复; 9 cap < 10 参考点, 落选者删元素
cand = []
for rb in ref_bag_nodes:
    rp = bag5[rb]
    dmin = min(sum((cap_center[c][0][k] - rp[k])**2 for k in range(3)) for c in cap_center)
    cand.append((dmin, rb))
cand.sort()
pairs = []   # (ref_bag_nid, anchor_nid, cap_sid, attach_nid_renumbered, beam_eid)
used, unmatched = set(), []
for dmin, rb in cand:
    rp = bag5[rb]
    order = sorted(cap_center, key=lambda c: sum((cap_center[c][0][k] - rp[k])**2 for k in range(3)))
    free = [c for c in order if c not in used]
    if not free:
        unmatched.append(rb); continue
    cap = free[0]; used.add(cap)
    attach = min(cap_center[cap][1], key=lambda x: sum((our_nodes[x][k] - rp[k])**2 for k in range(3)))
    anch = None
    for eid, pid, n1, n2 in beams:
        if n1 == rb and n2 in veh: anch = n2; break
        if n2 == rb and n1 in veh: anch = n1; break
    pairs.append((rb, anch, cap, attach + NOFF, eid))
for rb, anch, cap, att, eid in pairs:
    L = math.dist(veh[anch], our_nodes[att - NOFF]) if anch in veh else -1
    print('  tether: 参考袋节点%-9d -> cap%-7d 附件#%-9d 锚#%-9d L=%6.1f' % (rb, cap, att, anch, L))
print('  落选(将删除其 beam/discrete):', unmatched)

matched_refs = {p[0] for p in pairs}
def rewire_line(s):
    n1, n2 = int(s[16:24]), int(s[24:32])
    ch = False
    if n1 in matched_refs:
        n1 = next(p[3] for p in pairs if p[0] == n1); ch = True
    if n2 in matched_refs:
        n2 = next(p[3] for p in pairs if p[0] == n2); ch = True
    if not ch:
        return None   # 未匹配 (如 PORT 第10条) -> 删除
    return s[:16] + '%8d%8d' % (n1, n2) + s[32:]

sw, mode = [], None
drop_cnt = 0
for s in spring_lines:
    st = s.strip()
    if st.startswith('*'):
        mode = st.split('_TITLE')[0].upper()
        sw.append(s); continue
    if mode in ('*ELEMENT_BEAM', '*ELEMENT_DISCRETE') and st and not st.startswith('$') and len(s) >= 32:
        r = rewire_line(s)
        if r is None:
            drop_cnt += 1; continue
        sw.append(r)
    else:
        sw.append(s)
open(OUT + '/Spring_swap.k', 'w').write('\n'.join(sw) + '\n')
print('[Spring_swap] 改接完成, 删除未匹配元素 %d (PORT 第10条)' % drop_cnt)

# ============================================================
# 3) 03_Control MOD (ENDTIM=2.0 探针, D3PLOT=0.1)
# ============================================================
c = open(REF + '/03_Control_card.k', errors='ignore').read()
a = c.replace('     200.0         0       0.0       0.0       0.0',
              '       2.0         0       0.0       0.0       0.0')
b = a.replace('       2.5         0         0         0',
              '       0.1         0         0         0')
assert a != c and b != a, '03_Control 替换未命中!'
open(OUT + '/03_Control_card_MOD.k', 'w').write(b)
print('[03_Control_MOD] ENDTIM 200->2.0, D3PLOT 2.5->0.1')

# ============================================================
# 4) main_swap.key
# ============================================================
inc = ['03_Control_card_MOD.k', 'MAT.K', 'cab1_clean.k', 'Vehicle.k', 'Spring_swap.k']
mk = ['*KEYWORD', '$ 参考host + 工作文件气帘(cab1, 工装已清算) 换装试验 deck']
for f in inc:
    mk += ['*INCLUDE', f]
mk.append('*END')
open(OUT + '/main_swap.key', 'w').write('\n'.join(mk) + '\n')
import shutil
shutil.copy(REF + '/MAT.K', OUT + '/MAT.K')
shutil.copy(REF + '/Vehicle.k', OUT + '/Vehicle.k')
print('[main_swap] 生成: ' + ', '.join(inc))

# ============================================================
# 5) ID 冲突审计
# ============================================================
def audit(fn):
    nodes, parts, secs, mats, crvs, nsets, psets = set(), set(), set(), set(), set(), set(), set()
    mode = None
    def first_field(s):
        # 逗号行取逗号前, 定宽行取前10列
        return (s.split(',')[0] if ',' in s else s[:10]).strip()
    for ln in open(fn, errors='ignore'):
        s = ln.strip()
        if s.startswith('*'):
            mode = kw_base(s); continue
        if not s or s.startswith('$'): continue
        f0 = first_field(s)
        try:
            if mode == '*NODE':
                nodes.add(int(f0.split()[0]) if ' ' in f0 else int(f0))
            elif mode == '*PART' and is_int(f0):
                parts.add(int(f0))
            elif mode == '*SECTION_SHELL' and is_int(f0.split()[0] if ' ' in f0 else f0):
                secs.add(int(f0.split()[0] if ' ' in f0 else f0))
            elif mode and mode.startswith('*MAT_') and is_int(f0.split()[0] if ' ' in f0 else f0):
                mats.add(int(f0.split()[0] if ' ' in f0 else f0))
            elif mode == '*DEFINE_CURVE' and is_int(f0.split()[0] if ' ' in f0 else f0):
                crvs.add(int(f0.split()[0] if ' ' in f0 else f0))
            elif mode == '*SET_NODE_LIST' and is_int(f0.split('.')[0].split()[0] if ' ' in f0 else f0.split('.')[0]):
                nsets.add(int(float(f0)))
            elif mode == '*SET_PART_LIST' and is_int(f0.split('.')[0].split()[0] if ' ' in f0 else f0.split('.')[0]):
                psets.add(int(float(f0)))
        except (ValueError, IndexError):
            pass
    return nodes, parts, secs, mats, crvs, nsets, psets

A = {f: audit(OUT + '/' + f) for f in ['cab1_clean.k', 'MAT.K', 'Vehicle.k', 'Spring_swap.k']}
names = list(A)
for cat, idx in [('nodes', 0), ('parts', 1), ('sections', 2), ('mats', 3), ('curves', 4), ('node-sets', 5), ('part-sets', 6)]:
    inter = set()
    for a in range(len(names)):
        for b in range(a+1, len(names)):
            inter |= (A[names[a]][idx] & A[names[b]][idx])
    print('[audit] %-10s: %s' % (cat, '冲突=' + str(sorted(inter)[:8]) if inter else 'OK (无跨文件冲突)'))
