"""参考模型连接拓扑图: PID8(拉带) 与 PID2/PID6/PID7 的共节点位置"""
import os
import collections
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

path = os.environ.get('REF_K', './ref/5P-BAG_004.key')
nodes = {}
elems = collections.defaultdict(list)
sec = None
for line in open(path, encoding='utf-8', errors='ignore'):
    s = line.rstrip('\n')
    st = s.strip()
    if st.startswith('*'):
        sec = st.upper().split()[0]
        continue
    if not st or st.startswith('$'):
        continue
    if sec == '*NODE':
        if ',' in s:
            f = [q.strip() for q in s.split(',')]
            if len(f) >= 4 and f[0]:
                try:
                    nodes[int(f[0])] = (float(f[1]), float(f[2]), float(f[3]))
                except ValueError:
                    pass
        else:
            try:
                nodes[int(s[0:8])] = (float(s[8:24]), float(s[24:40]), float(s[40:56]))
            except ValueError:
                pass
    elif sec == '*ELEMENT_SHELL':
        f = [q.strip() for q in s.split(',')] if ',' in s else \
            [s[0:8], s[8:16], s[16:24], s[24:32], s[32:40], s[40:48]]
        try:
            elems[int(f[1])].append([int(x) for x in f[2:6] if x.strip()])
        except (ValueError, IndexError):
            pass

s8 = set(n for el in elems[8] for n in el if n in nodes)
s6 = set(n for el in elems[6] for n in el if n in nodes)
s7 = set(n for el in elems[7] for n in el if n in nodes)
s2 = set(n for el in elems[2] for n in el if n in nodes)
s68, s78, s28 = s8 & s6, s8 & s7, s8 & s2
print('PID8∩PID6=%d  PID8∩PID7=%d  PID8∩PID2=%d' % (len(s68), len(s78), len(s28)))

fig, ax = plt.subplots(figsize=(20, 9))
for el in elems[8]:
    xs = [nodes[n][0] for n in el if n in nodes]
    zs = [nodes[n][2] for n in el if n in nodes]
    if len(xs) == len(el):
        ax.fill(xs, zs, color='#ffcc66', alpha=.45)
for el in elems[6]:
    xs = [nodes[n][0] for n in el if n in nodes]
    zs = [nodes[n][2] for n in el if n in nodes]
    if len(xs) == len(el):
        ax.fill(xs, zs, color='#ffe0e0', alpha=.3)
ax.scatter([nodes[n][0] for n in s68], [nodes[n][2] for n in s68],
           s=20, color='red', marker='x', label='PID8-PID6 belt shared (%d)' % len(s68))
ax.scatter([nodes[n][0] for n in s78], [nodes[n][2] for n in s78],
           s=20, color='blue', marker='+', label='PID8-PID7 shared (%d)' % len(s78))
ax.scatter([nodes[n][0] for n in s28], [nodes[n][2] for n in s28],
           s=20, color='black', marker='2', label='PID8-PID2 boss caps (%d)' % len(s28))
ax.set_aspect('equal')
ax.legend(fontsize=10)
ax.set_title('ref 5P-BAG_004: PID8 tabs + shared-node locations')
plt.savefig('out/v_ref_conn_map.png', dpi=110)
print('saved')
