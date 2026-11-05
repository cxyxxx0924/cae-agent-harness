#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_fixed.py —— 把 SMP 单文件 d3plot 渲染成“气帘上拉过程”可视化，用于确认三处修复
（拉绳 Z 向自由/XY 锁死、垂直投影取上方节点、参考几何抑制抖动）是否消除了“乱飞舞/抖动”。

产出:
  1) 每帧侧视图 (X–Z, 沿 Y 看): 气帘节点按 |位移| 着色，直观看是否剧烈 flail。
     前 27ms (t<=tmax) 每帧一张 PNG，再拼一张多格总览图。
  2) 速度 RMS / 峰值速度 时间历程 (mm/ms): 量化“抖动”水平，配合 smp_d3plot --shake 对比。

依赖: numpy, matplotlib。用法:
  python render_fixed.py <d3plot> --outdir out_frames --tmax 27 --dt 2.5
"""
import numpy as np
import os, sys, argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import smp_d3plot as D


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('d3plot')
    ap.add_argument('--outdir', default='out_frames')
    ap.add_argument('--tmax', type=float, default=27.0, help='只渲染 t<=tmax ms (默认27)')
    ap.add_argument('--dt', type=float, default=2.5, help='d3plot 输出间隔 ms')
    ap.add_argument('--dpi', type=int, default=110)
    ap.add_argument('--sample', type=int, default=1, help='节点抽样步长(加速); 1=全画')
    args = ap.parse_args()

    G = D.load(args.d3plot)
    N = G['N']; g0 = G['g0']
    z = g0[:, 2]
    active_zmin = float(np.percentile(z, 70))   # 气帘带: 初始 Z 上 70%
    print("N=%d n_states=%d  active_zmin(Z)=%.1f" % (N, G['n_states'], active_zmin))

    os.makedirs(args.outdir, exist_ok=True)
    idx = np.arange(0, N, args.sample)

    frames = []
    for i in range(G['n_states']):
        t = i * args.dt
        if t > args.tmax + 1e-6:
            break
        cur, vel, _ = D.read_state(G, i)
        disp = np.linalg.norm(cur - g0, axis=1)
        spd = np.linalg.norm(vel, axis=1)
        frames.append(dict(i=i, t=t, cur=cur, disp=disp, spd=spd))

    if not frames:
        print("无可用帧 (t<=%.1fms)" % args.tmax); return

    # 统一坐标范围
    xmin, xmax = g0[:, 0].min(), g0[:, 0].max()
    zmin, zmax = g0[:, 2].min(), g0[:, 2].max()
    dmax = max(f['disp'].max() for f in frames)
    dmax = max(dmax, 1.0)
    smax = max(f['spd'].max() for f in frames)
    smax = max(smax, 1e-3)

    pngs = []
    for f in frames:
        fig, ax = plt.subplots(figsize=(7.2, 5.4))
        sc = ax.scatter(f['cur'][idx, 0], f['cur'][idx, 2], c=np.log10(f['disp'][idx] + 1e-3),
                        cmap='jet', s=1.2, vmin=-3, vmax=np.log10(dmax + 1e-3))
        ax.set_xlim(xmin, xmax); ax.set_ylim(zmin, zmax)
        ax.set_xlabel('X (mm)'); ax.set_ylabel('Z (mm)')
        ax.set_title('气帘上拉 t=%.1f ms  |disp| (log)  vmax=%.2f mm/ms' % (f['t'], f['spd'].max()))
        fig.colorbar(sc, ax=ax, label='log10(|disp| mm)')
        p = os.path.join(args.outdir, 'frame_%02d_t%05.1f.png' % (f['i'], f['t']))
        fig.savefig(p, dpi=args.dpi); plt.close(fig)
        pngs.append(p)
    print("已写 %d 帧 PNG -> %s" % (len(pngs), args.outdir))

    # 多格总览
    n = len(frames); ncol = min(3, n); nrow = (n + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(4.6 * ncol, 3.6 * nrow))
    axes = np.atleast_1d(axes).ravel()
    for k, f in enumerate(frames):
        ax = axes[k]
        ax.scatter(f['cur'][idx, 0], f['cur'][idx, 2], c=np.log10(f['disp'][idx] + 1e-3),
                   cmap='jet', s=0.8, vmin=-3, vmax=np.log10(dmax + 1e-3))
        ax.set_xlim(xmin, xmax); ax.set_ylim(zmin, zmax)
        ax.set_title('t=%.1fms' % f['t'], fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
    for k in range(n, len(axes)):
        axes[k].axis('off')
    fig.suptitle('气帘上拉过程 (X–Z 侧视, 颜色=log|位移|)', fontsize=11)
    fig.tight_layout()
    ov = os.path.join(args.outdir, 'overview.png')
    fig.savefig(ov, dpi=args.dpi); plt.close(fig)
    print("总览图 ->", ov)

    # 速度 RMS / 峰值 时间历程
    rows = D.shake_metrics(G, dt_ms=args.dt, active_zmin=active_zmin)
    ts = [r['t_ms'] for r in rows]
    vrms_a = [r['vrms_air'] for r in rows]
    vmax_a = [r['vmax_air'] for r in rows]
    dmax_a = [r['dmax_air'] for r in rows]
    fig2, ax1 = plt.subplots(figsize=(8, 4.5))
    ax1.plot(ts, vrms_a, 'b-o', label='气帘带 速度RMS (mm/ms)')
    ax1.plot(ts, vmax_a, 'r--s', label='气帘带 峰值速度 (mm/ms)')
    ax1.set_xlabel('时间 (ms)'); ax1.set_ylabel('速度 (mm/ms)')
    ax2 = ax1.twinx()
    ax2.plot(ts, dmax_a, 'g-^', label='气帘带 最大位移 (mm)')
    ax2.set_ylabel('最大位移 (mm)')
    ax1.set_title('上拉过程速度/位移时间历程 (抖动量化)')
    l1, lb1 = ax1.get_legend_handles_labels(); l2, lb2 = ax2.get_legend_handles_labels()
    ax1.legend(l1 + l2, lb1 + lb2, loc='upper left', fontsize=8)
    fig2.tight_layout()
    sh = os.path.join(args.outdir, 'shake_ts.png')
    fig2.savefig(sh, dpi=args.dpi); plt.close(fig2)
    print("抖动时间历程 ->", sh)
    print("前27ms 速度RMS 序列(mm/ms):", " ".join('%.3f' % v for v in vrms_a[:int(args.tmax / args.dt) + 1]))


if __name__ == '__main__':
    main()
