# render_final.py — 交付渲染: ①原始曲线 vs 网格自由边界叠加 ②Y 分层投影 ③充气口封口细节
import json, math, re
from collections import defaultdict, Counter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
plt.rcParams['font.family'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']

import os
P = (os.environ.get('WORKDIR') or './cab3').rstrip('/') + '/'
V3 = json.load(open(P + 'loops_v3.json'))
loops_old = json.load(open(P + 'cab3_loops.json'))

# ---------- 网格 ----------
nodes = {}
el = defaultdict(list)
for ln in open(P + 'cab3_step1_v3_mesh.txt', encoding='utf-8', errors='replace'):
    p = ln.split()
    if not p:
        continue
    if p[0] == 'S':
        el[p[1]].append((int(p[2]), [int(x) for x in p[3:]]))
    elif p[0] == 'N':
        m = re.search(r'\{([^}]*)\}', ln)
        if m:
            v = m.group(1).split()
            nodes[int(p[1])] = (float(v[0]), float(v[1]))
cnt = defaultdict(Counter)
for t, e in el.items():
    for eid, nds in e:
        k = len(nds)
        for i in range(k):
            a, b = nds[i], nds[(i + 1) % k]
            cnt[t][(min(a, b), max(a, b))] += 1
FREE = {t: set(e for e, c in cc.items() if c == 1) for t, cc in cnt.items()}

# ============ 图 1: 原始曲线 vs 网格自由边界 ============
fig, ax = plt.subplots(figsize=(19, 10))
for nm, col in [('belt', 'tab:blue'), ('cavity', 'tab:red')]:
    xs = [p[0] for p in V3[nm]['pts']]; ys = [p[1] for p in V3[nm]['pts']]
    ax.plot(xs, ys, color=col, lw=1.0, alpha=0.55, zorder=2)
for h in V3['holes']:
    xs = [p[0] for p in h['pts']]; ys = [p[1] for p in h['pts']]
    ax.plot(xs, ys, color='k', lw=0.9, alpha=0.7, zorder=3)
for t, col, lab in [('belt', 'navy', '布带网格自由边界'), ('cav', 'darkred', '气腔网格自由边界'),
                    ('seam0', 'darkgreen', '缝线网格自由边界'), ('seam1', 'darkgreen', None),
                    ('seam2', 'darkgreen', None)]:
    for a, b in FREE.get(t, []):
        ax.plot([nodes[a][0], nodes[b][0]], [nodes[a][1], nodes[b][1]],
                color=col, lw=1.8, alpha=0.95, zorder=5, label=lab if lab else None)
handles = [Line2D([], [], color='tab:blue', lw=1.0, alpha=0.55, label='布带原始曲线'),
           Line2D([], [], color='tab:red', lw=1.0, alpha=0.55, label='气腔原始曲线'),
           Line2D([], [], color='navy', lw=1.8, label='布带网格自由边界'),
           Line2D([], [], color='darkred', lw=1.8, label='气腔网格自由边界'),
           Line2D([], [], color='darkgreen', lw=1.8, label='缝线网格自由边界'),
           Line2D([], [], color='k', lw=0.9, alpha=0.7, label='3 个小洞原始曲线')]
ax.legend(handles=handles, loc='upper left', fontsize=9, ncol=2)
ax.set_aspect('equal'); ax.grid(alpha=0.2, lw=0.4)
ax.set_title('cab3 Step1 形状对比: 原始曲线(细) vs 网格自由边界(粗)\n'
             'shape_gate_v3 ALL PASS: belt C=0.297/Cr=0.748 | cavity C=0.289/Cr=0.977 | '
             'seams C<=0.235 | holes C=0.194', fontsize=12)
ax.set_xlabel('HM x (mm)'); ax.set_ylabel('HM y (mm)')
plt.tight_layout()
plt.savefig(P + 'v_final_shape.png', dpi=125)
plt.close()
print('wrote v_final_shape.png')

# ============ 图 2: 全模型 Y 分层投影 (XZ) ============
lines = open(P + 'cab3_full_v3.k', encoding='utf-8', errors='replace').read().splitlines()
kn = {}; ke = []; state = None
for ln in lines:
    if ln.startswith('*'):
        state = ln.split()[0].upper(); continue
    if state == '*NODE' and not ln.strip().startswith('$'):
        try:
            kn[int(ln[0:8])] = (float(ln[8:24]), float(ln[24:40]), float(ln[40:56]))
        except Exception:
            pass
    elif state == '*ELEMENT_SHELL' and not ln.strip().startswith('$'):
        try:
            ns = [int(ln[16 + 8 * k:24 + 8 * k]) for k in range(4)]
            ns = [n for n in ns if n]
            if len(ns) >= 3:
                ke.append((int(ln[8:16]), ns))
        except Exception:
            pass

fig, axes = plt.subplots(2, 2, figsize=(19, 12))
YCOL = {0.0: 'tab:blue', 0.5: 'tab:red', -0.5: 'tab:orange', -1.0: 'tab:green'}
for ax, (ymid, ttl) in zip(axes.ravel(),
                           [(-1.0, 'PID5 拉带  Y=-1'),
                            (-0.5, 'PID3 气腔下层  Y=-0.5'),
                            (0.0, 'PID2 布带 + PID4 缝线  Y=0'),
                            (0.5, 'PID3 气腔上层  Y=+0.5')]):
    sel = [ns for pid, ns in ke if all(abs(kn[n][1] - ymid) < 0.01 for n in ns)]
    for ns in sel:
        xs = [kn[n][0] for n in ns] + [kn[ns[0]][0]]
        zs = [kn[n][2] for n in ns] + [kn[ns[0]][2]]
        ax.plot(xs, zs, color=YCOL[ymid], lw=0.35, alpha=0.85)
    ax.set_aspect('equal'); ax.grid(alpha=0.2, lw=0.4)
    ax.set_title('%s  单元=%d' % (ttl, len(sel)), fontsize=10)
fig.suptitle('cab3_full_v3.k  Y 分层 X-Z 投影 (K 坐标: 面内 X-Z, 厚度 Y)\n'
             '节点=%d 单元=%d  PID3=%d (双层 2x5356 + washer %d + 充气口捏合 6)' % (
                 len(kn), len(ke), sum(1 for p, _ in ke if p == 3), 562 + 1048), fontsize=12)
plt.tight_layout()
plt.savefig(P + 'v_final_layers.png', dpi=115)
plt.close()
print('wrote v_final_layers.png')

# ============ 图 3: 充气口封口细节 ============
raw = {}
for ln in open(P + 'lines_pts_all.txt', encoding='utf-8', errors='replace'):
    if '|' not in ln:
        continue
    h, rest = ln.split('|', 1)
    p = h.split()
    if len(p) < 7:
        continue
    try:
        lid = int(p[1]); comp = p[0]
    except Exception:
        continue
    pts = []
    for s in rest.strip().split(';'):
        s = s.strip()
        if not s:
            continue
        a = s.split()
        if len(a) >= 2:
            try:
                pts.append((float(a[0]), float(a[1])))
            except Exception:
                pass
    if pts:
        raw[lid] = (comp, pts)

fig, ax = plt.subplots(figsize=(13, 11))
for lid, (c, pts) in raw.items():
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    if max(xs) < 400 or min(xs) > 480 or max(ys) < 165 or min(ys) > 210:
        continue
    ax.plot(xs, ys, color='0.75', lw=1.6, zorder=1)
for nm, col in [('belt', 'tab:blue'), ('cavity', 'tab:red')]:
    xs = [p[0] for p in V3[nm]['pts']]; ys = [p[1] for p in V3[nm]['pts']]
    ax.plot(xs, ys, color=col, lw=1.2, alpha=0.5, zorder=2)
for t, col in [('belt', 'navy'), ('cav', 'darkred')]:
    for a, b in FREE.get(t, []):
        if (nodes[a][1] + nodes[b][1]) / 2 < 176.0:
            continue
        ax.plot([nodes[a][0], nodes[b][0]], [nodes[a][1], nodes[b][1]],
                color=col, lw=1.6, alpha=0.9, zorder=4)
pinch = []
for pid, ns in ke:
    if pid != 3:
        continue
    ys = [kn[n][1] for n in ns]
    if max(ys) > 0.4 and min(ys) < -0.4:
        xs = [kn[n][0] for n in ns]; zs = [kn[n][2] for n in ns]
        pinch.append((xs, zs))
for xs, zs in pinch:
    ax.fill(xs + [xs[0]], zs + [zs[0]], color='magenta', alpha=0.55, zorder=6,
            edgecolor='k', lw=1.0)
ax.annotate('充气口捏合\n(%d 个 PID3 四边形)' % len(pinch), xy=(458, 196),
            fontsize=11, color='magenta', ha='center', fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.4', fc='white', ec='magenta', alpha=0.9))
ax.set_xlim(400, 480); ax.set_ylim(165, 210)
ax.set_aspect('equal'); ax.grid(alpha=0.25, lw=0.4)
ax.set_title('充气口区: 灰色=comp1 细节曲线 / 蓝=布带 / 红=气腔 / 品红=封口捏合单元', fontsize=11)
ax.set_xlabel('HM x'); ax.set_ylabel('HM y')
plt.tight_layout()
plt.savefig(P + 'v_final_port.png', dpi=130)
plt.close()
print('wrote v_final_port.png  (pinch quads=%d)' % len(pinch))
