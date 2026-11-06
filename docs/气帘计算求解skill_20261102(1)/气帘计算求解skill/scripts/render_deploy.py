#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_deploy.py —— 气帘充气部署过程 / 终态细节 渲染（X-Z 顶视 + Y-Z/X-Y 侧视 + 位移云图）
========================================================================================
依赖 d3plot_reader.py（同目录）。自动发现目录内 d3plotNN 状态文件，用速度RMS↔glstat KE
标定时刻，绘制：图1=部署过程（平铺→早期→中期→终态，X-Z 顶视，固定节点标注）；
图2=终态细节（X-Z 分区 / Y-Z 侧视 / X-Y 平铺面 / 位移模长云图）。

用法：
  python render_deploy.py --d3dir E:/work/lsdyna-agent/newcab_trial --deck newcab_calc.k \
                          --glstat glstat --out deploy
输出：<d3dir>/<out>_process.png 与 <d3dir>/<out>_t20_detail.png
"""
import os, sys, glob, argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
import matplotlib.font_manager as fm

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from d3plot_reader import load_geom, load_state, parse_fixed


def register_cjk():
    for p in [r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf',
              r'C:\Windows\Fonts\simsun.ttc']:
        if os.path.exists(p):
            try:
                fm.fontManager.addfont(p)
                return 'Microsoft YaHei'
            except Exception:
                pass
    return 'DejaVu Sans'


def quads(coords, n1, n2, n3, n4):
    return np.stack([coords[n1 - 1], coords[n2 - 1], coords[n3 - 1], coords[n4 - 1]], axis=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--d3dir', required=True, help='含 d3plot(几何) 与 d3plotNN(状态) 的目录')
    ap.add_argument('--deck', default='', help='deck .k（解析固定节点标注）')
    ap.add_argument('--glstat', default='glstat', help='glstat 文件名（用于时刻标定）')
    ap.add_argument('--out', default='render')
    ap.add_argument('--mass', type=float, default=0.70067)
    args = ap.parse_args()

    geom = os.path.join(args.d3dir, 'd3plot')
    N, NE, g0, (n1, n2, n3c, n4, pid) = load_geom(geom)
    fixed = parse_fixed(args.deck,
                       set([900001] + [900010 + i for i in range(14)])) if args.deck else set()
    font = register_cjk()
    plt.rcParams['font.sans-serif'] = [font]
    plt.rcParams['axes.unicode_minus'] = False

    PCOL = {1: '#2E5E8C', 2: '#7FB3D5', 3: '#DD8452', 4: '#55A868'}
    PNAME = {1: '布带', 2: '气腔', 3: '缝线', 4: '拉带'}

    # 发现状态文件并标定时刻
    states = sorted(glob.glob(os.path.join(args.d3dir, 'd3plot[0-9][0-9]')),
                    key=lambda p: int(os.path.basename(p)[6:]))
    if not states:
        print("未发现 d3plotNN 状态文件"); sys.exit(1)
    glstat_path = os.path.join(args.d3dir, args.glstat)
    ke_list = []  # (fileidx, t_est)
    if os.path.exists(glstat_path):
        # glstat kinetic energy 时序
        ke_ts = []
        t = None
        for L in open(glstat_path, errors='ignore'):
            m = __import__('re').search(r'time\s*\.+\s*([\d.E+-]+)', L)
            if m:
                try: t = float(m.group(1))
                except Exception: t = None
            if 'kinetic energy' in L and 'eroded' not in L:
                nums = __import__('re').findall(r'[\d.E+-]+', L)
                if nums:
                    ke_ts.append((t, float(nums[-1])))
    loaded = []
    for s in states:
        a = np.fromfile(s, dtype=np.float32, count=140 + 3 * 3 * N)
        cur = a[140:140 + 3 * N].reshape(N, 3)
        vel = a[140 + 3 * N:140 + 2 * 3 * N].reshape(N, 3)
        vrms = np.sqrt((vel ** 2).sum(1).mean())
        ke_est = 0.5 * args.mass * vrms ** 2
        t_est = None
        if ke_ts:
            t_est = min(ke_ts, key=lambda kv: abs(kv[1] - ke_est))[0]
        loaded.append((os.path.basename(s), cur, t_est, vrms))
    # 选 4 帧：首、末、及中间按时刻均匀取
    idx = [0, len(loaded) - 1]
    if len(loaded) >= 3:
        idx.insert(1, len(loaded) // 3)
        idx.insert(2, 2 * len(loaded) // 3)
    idx = sorted(set(idx))
    frames = [loaded[i] for i in idx]

    def panel_xz(ax, coords, title, fixnodes):
        for p in [2, 1, 4, 3]:
            m = np.where(pid == p)[0]
            ax.add_collection(PolyCollection(quads(coords, n1, n2, n3c, n4)[m][:, :, [0, 2]],
                                            facecolor=PCOL[p], edgecolor='none'))
        if fixnodes:
            fn = np.array(sorted(fixnodes)) - 1
            ax.plot(g0[fn, 0], g0[fn, 2], '.', color='k', ms=2.0, label='固定节点')
        ax.set_title(title, fontsize=10); ax.set_aspect('equal')
        ax.set_xlabel('X (mm)'); ax.set_ylabel('Z (mm)'); ax.grid(alpha=0.25, lw=0.4)

    # 图1 部署过程
    fig, axs = plt.subplots(2, 2, figsize=(15, 10.5))
    for ax, (nm, cur, t_est, vr) in zip(axs.ravel(), frames):
        tt = ("t≈%.1fms" % t_est) if t_est is not None else nm
        panel_xz(ax, cur, "%s  (%s)" % (nm, tt), fixed)
    for ax in axs.ravel():
        ax.set_xlim(-450, 1850); ax.set_ylim(-230, 560)
    h = [plt.Rectangle((0, 0), 1, 1, fc=PCOL[p]) for p in [1, 2, 3, 4]]
    axs[0, 0].legend(h, [PNAME[p] for p in [1, 2, 3, 4]], loc='upper left', fontsize=8, ncol=2)
    fig.suptitle('气帘充气部署过程（X-Z 顶视图：向右=+X，向上=+Z）', fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    p1 = os.path.join(args.d3dir, args.out + '_process.png')
    fig.savefig(p1, dpi=130); plt.close(fig)

    # 图2 终态细节
    _, cur, t_est, _ = frames[-1]
    fig, axs = plt.subplots(2, 2, figsize=(15, 10.5))
    panel_xz(axs[0, 0], cur, '终态 X-Z 顶视图（分区着色）', fixed)
    # Y-Z
    ax = axs[0, 1]
    for p in [2, 1, 4, 3]:
        m = np.where(pid == p)[0]
        ax.add_collection(PolyCollection(quads(cur, n1, n2, n3c, n4)[m][:, :, [1, 2]],
                                         facecolor=PCOL[p], edgecolor='none'))
    fn = np.array(sorted(fixed)) - 1
    ax.plot(g0[fn, 1], g0[fn, 2], '.', color='k', ms=2.0)
    ax.set_title('终态 Y-Z 侧视图（袋体沿厚度 Y 展开）', fontsize=10); ax.set_aspect('equal')
    ax.set_xlabel('Y (mm)'); ax.set_ylabel('Z (mm)'); ax.grid(alpha=0.25, lw=0.4)
    # X-Y
    ax = axs[1, 0]
    for p in [2, 1, 4, 3]:
        m = np.where(pid == p)[0]
        ax.add_collection(PolyCollection(quads(cur, n1, n2, n3c, n4)[m][:, :, [0, 1]],
                                         facecolor=PCOL[p], edgecolor='none'))
    ax.plot(g0[fn, 0], g0[fn, 1], '.', color='k', ms=2.0)
    ax.set_title('终态 X-Y 视图（原平铺面）', fontsize=10); ax.set_aspect('equal')
    ax.set_xlabel('X (mm)'); ax.set_ylabel('Y (mm)'); ax.grid(alpha=0.25, lw=0.4)
    # 位移云图
    ax = axs[1, 1]
    dm = np.linalg.norm(cur - g0, axis=1)
    edm = 0.25 * (dm[n1 - 1] + dm[n2 - 1] + dm[n3c - 1] + dm[n4 - 1])
    pc = PolyCollection(quads(cur, n1, n2, n3c, n4)[:, :, [0, 2]], array=edm, cmap='jet', edgecolor='none')
    ax.add_collection(pc); plt.colorbar(pc, ax=ax, label='位移模长 (mm)', shrink=0.85)
    ax.plot(g0[fn, 0], g0[fn, 2], '.', color='k', ms=1.2)
    ax.set_title('终态 位移模长分布', fontsize=10); ax.set_aspect('equal')
    ax.set_xlabel('X (mm)'); ax.set_ylabel('Z (mm)'); ax.grid(alpha=0.25, lw=0.4)
    for ax in [axs[0, 0], axs[1, 1]]:
        ax.set_xlim(-450, 1850); ax.set_ylim(-230, 560)
    tt = ("t≈%.1fms" % t_est) if t_est is not None else '终态'
    fig.suptitle('气帘 终态 %s 细节（abstat 见健康门禁报告）' % tt, fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    p2 = os.path.join(args.d3dir, args.out + '_t20_detail.png')
    fig.savefig(p2, dpi=130); plt.close(fig)
    print("已生成:\n  %s\n  %s" % (p1, p2))


if __name__ == '__main__':
    main()
