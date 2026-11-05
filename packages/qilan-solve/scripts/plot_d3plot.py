#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
plot_d3plot.py —— 不用 LS-PrePost，直接出气帘形态图（判断"帘子是不是被拉歪/扭转"）。

用法:
    python plot_d3plot.py <d3plot> <outdir> [--pid 2,3,4,5] [--views xz,xy] [--every 4]

输出 outdir/view_<xz|xy>_s<state>.png，一个子图一行状态，颜色 = Z 向位移。
"""
import os
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from lasso.dyna import D3plot, ArrayType


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    path, outdir = sys.argv[1], sys.argv[2]
    pids = [2, 3, 4, 5]
    views = ['xz', 'xy']
    every = 99
    for a in sys.argv[3:]:
        if a.startswith('--pid'):
            v = a.split('=')[1] if '=' in a else None
            if v:
                pids = [int(x) for x in v.split(',')]
        if a.startswith('--views='):
            views = a.split('=')[1].split(',')
        if a.startswith('--every='):
            every = int(a.split('=')[1])
    os.makedirs(outdir, exist_ok=True)

    d = D3plot(path)
    ids = d.arrays[ArrayType.node_ids]
    XYZ = d.arrays[ArrayType.node_coordinates]
    U = d.arrays[ArrayType.node_displacement]
    U = U - U[0:1]
    t = np.asarray(d.arrays.get(ArrayType.global_timesteps, []), dtype=float)
    if t.size != U.shape[0]:
        t = np.arange(U.shape[0], dtype=float)

    es = d.arrays[ArrayType.element_shell_node_indexes]
    ep = d.arrays[ArrayType.element_shell_part_indexes]
    pid_list = np.asarray(d.arrays.get(ArrayType.part_ids, []))
    # 本 deck 的 PID 就是 2/3/4/5，part_index 与 pid 不一定相等，做个映射
    want = set(pids)
    if pid_list.size and max(pid_list) >= max(pid_list.max(), 5):
        keep = np.array([pid_list[p] in want if p < len(pid_list) else False for p in ep])
    else:
        keep = np.array([p + 2 in want for p in ep])
    if keep.sum() == 0:                       # 兜底：只要壳单元全画
        keep = np.ones(len(es), dtype=bool)
    es = es[keep]

    states = list(range(0, U.shape[0], every))
    if states[-1] != U.shape[0] - 1:
        states.append(U.shape[0] - 1)
    states = states[1:] if len(states) > 1 else states

    print('states to plot:', states, ' shells:', len(es))

    pick = {0: (0, 2), 1: (0, 1)}             # xz: (x,z)  xy: (x,y)
    for view in views:
        ax0, ax1 = pick[1 if view == 'xy' else 0]
        fig, axes = plt.subplots(len(states), 1, figsize=(13, 2.6 * len(states)), squeeze=False)
        for row, s in enumerate(states):
            ax = axes[row][0]
            P = XYZ + U[s]
            pts = P[:, [ax0, ax1]]
            dz = U[s][:, 2]
            verts = [pts[e] for e in es]
            cols = [dz[e].mean() for e in es]
            pc = PolyCollection(verts, array=np.array(cols), cmap='jet',
                                edgecolors='none', linewidths=0)
            ax.add_collection(pc)
            ax.autoscale()
            ax.set_aspect('equal')
            ax.set_title('t = %.2f ms   %s view   colour = dZ (mm)' % (t[s], view.upper()),
                         fontsize=9, loc='left')
            ax.tick_params(labelsize=7)
            fig.colorbar(pc, ax=ax, fraction=0.02, pad=0.01).ax.tick_params(labelsize=7)
        fig.tight_layout()
        out = os.path.join(outdir, 'view_%s.png' % view)
        fig.savefig(out, dpi=130)
        plt.close(fig)
        print('  ->', out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
