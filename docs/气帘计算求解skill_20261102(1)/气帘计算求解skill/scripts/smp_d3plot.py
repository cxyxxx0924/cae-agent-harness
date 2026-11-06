#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smp_d3plot.py —— SMP 版 LS-DYNA 单文件 d3plot 逆向读取器（气帘/NEW_CAB 专用）
================================================================================
本机 LS-DYNA R10.1.0 (smp s, winx64) 写出的 d3plot 是【单文件】：
    几何段(节点坐标/连接/ID表) + 状态段(每帧: 140词头 + 坐标 + 速度 + 加速度)
与 MPP 不同，MPP 把几何与状态拆成 d3plot + d3plotNN 且几何仅含单 domain，
导致旧 d3plot_reader.py 越界。本脚本只针对 SMP 单文件，无需任何外部工具。

设计要点（规避脆弱的几何连接段解析）：
  * 节点数 N = ai[16]，单元数 NE = ai[31]（int32 控制块，本机实测）。
  * 初始坐标 g0 固定在 @word64，3*N 个 float32。
  * 状态0 就是 t=0 的初始几何，其坐标块 == g0（逐位相等）。
    因此用“扫描 g0 首次复现位置”定位状态0，避免解析连接段/目录/ID表尺寸。
  * 状态 stride 用标准公式 (140+9N) 向上取整到 4 词边界，并用状态1 坐标合理性校验，
    若失败自动尝试若干候选 stride。
  * 全程不依赖连接段，因此模型含 beam/solid 混合单元也不会崩。

shake 指标（无需质量，直接反映抖动）：
  vrms  = sqrt(mean(|v|^2))          节点速度 RMS (mm/ms)
  vmax  = max |v|                     峰值节点速度
  dmean/dmax = mean/max |cur-g0|      位移均值/峰值（部署进度+flutter）

用法:
  python smp_d3plot.py <d3plot> --list
  python smp_d3plot.py <d3plot> --state 5 --out out.npz
  python smp_d3plot.py <d3plot> --shake            # 打印每帧 shake 指标
  python smp_d3plot.py <d3plot> --shake-csv shake.csv
"""
import numpy as np
import sys, os, argparse


def roundup4(w):
    return (w + 3) & ~3


def load(path):
    ai = np.fromfile(path, dtype=np.int32)
    a = ai.view(np.float32)
    N = int(ai[16]); NE = int(ai[31])
    assert N > 0 and NE > 0, "控制块 NUMNOD/NUMEL 解析失败 N=%d NE=%d" % (N, NE)
    g0 = a[64:64 + 3 * N].reshape(N, 3).copy()

    # ---- 定位状态0：它的坐标块 == g0 ----
    g0f = g0.reshape(-1)
    ref0 = g0f[0]
    search = a[64 + 3 * N:]
    cands = np.where(search == ref0)[0] + (64 + 3 * N)
    c0 = None
    for c in cands[:200]:
        if c + 3 * N <= len(a) and np.array_equal(a[c:c + 3 * N], g0f):
            c0 = int(c); break
    assert c0 is not None, "未找到状态0(初始几何复现)，d3plot 格式假设可能不成立"
    geom_end = c0 - 140                      # 状态0 头起点 = 几何段尾
    assert geom_end >= 64 + 3 * N, "geom_end 异常=%d" % geom_end

    # ---- 自动探测 stride（状态1 坐标合理性校验）----
    bb = np.array([g0.min(0), g0.max(0)])    # 初始包围盒
    span = np.maximum((bb[1] - bb[0]), 1.0)
    lo = bb[0] - 3 * span
    hi = bb[1] + 3 * span

    def sane(coords):
        if not np.all(np.isfinite(coords)): return False
        if coords.min() < lo.min() or coords.max() > hi.max(): return False
        if coords.max() - coords.min() < 1e-6: return False
        return True

    stride = None
    for cand in (roundup4(140 + 9 * N), roundup4(140 + 6 * N),
                 140 + 9 * N, 140 + 6 * N, roundup4(140 + 3 * N)):
        off = geom_end + cand
        if off + 140 + 3 * N > len(a): continue
        c1 = a[off + 140: off + 140 + 3 * N].reshape(N, 3)
        if sane(c1):
            stride = cand; break
    assert stride is not None, "无法探测状态 stride（状态1 坐标均不合理）"

    total = len(a)
    n_states = (total - geom_end) // stride
    return dict(N=N, NE=NE, g0=g0, a=a, geom_end=geom_end, stride=stride,
                n_states=n_states, path=path)


def read_state(G, i):
    N = G['N']; off = G['geom_end'] + i * G['stride']
    a = G['a']
    cur = a[off + 140: off + 140 + 3 * N].reshape(N, 3).copy()
    vel = a[off + 140 + 3 * N: off + 140 + 6 * N].reshape(N, 3).copy()
    acc = a[off + 140 + 6 * N: off + 140 + 9 * N].reshape(N, 3).copy()
    return cur, vel, acc


def shake_metrics(G, dt_ms=2.5, active_zmin=None):
    """返回每帧 shake 指标列表（dict）。active_zmin: 仅统计初始 Z>=该值的节点(气帘)。"""
    N = G['N']; g0 = G['g0']
    z = g0[:, 2]
    if active_zmin is None:
        # 取 Z 分布上 70% 分位以上作为“气帘带”，避免整车刚体稀释信号
        active_zmin = np.percentile(z, 70)
    active = z >= active_zmin
    rows = []
    for i in range(G['n_states']):
        cur, vel, _ = read_state(G, i)
        disp = np.linalg.norm(cur - g0, axis=1)
        spd = np.linalg.norm(vel, axis=1)
        rows.append(dict(
            i=i, t_ms=i * dt_ms,
            vrms_all=float(np.sqrt((spd ** 2).mean())),
            vmax_all=float(spd.max()),
            dmean_all=float(disp.mean()), dmax_all=float(disp.max()),
            vrms_air=float(np.sqrt((spd[active] ** 2).mean())),
            vmax_air=float(spd[active].max()),
            dmean_air=float(disp[active].mean()), dmax_air=float(disp[active].max()),
            n_active=int(active.sum()),
        ))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('d3plot')
    ap.add_argument('--list', action='store_true', help='打印 N/NE/n_states')
    ap.add_argument('--state', type=int, help='导出某帧为 npz')
    ap.add_argument('--out', default='')
    ap.add_argument('--shake', action='store_true', help='打印每帧 shake 指标')
    ap.add_argument('--shake-csv', default='')
    ap.add_argument('--dt', type=float, default=2.5, help='d3plot 输出间隔 ms')
    ap.add_argument('--active-zmin', type=float, default=None,
                    help='仅统计初始 Z>=该值的节点作为气帘带(None=自动按70分位)')
    args = ap.parse_args()

    G = load(args.d3plot)
    if args.list:
        print("N=%d NE=%d n_states=%d geom_end=%d stride=%d" %
              (G['N'], G['NE'], G['n_states'], G['geom_end'], G['stride']))
    if args.state is not None:
        cur, vel, acc = read_state(G, args.state)
        if args.out:
            np.savez(args.out, coords=cur, velocity=vel, accel=acc, initial=G['g0'])
            print("已写 %s.npz" % args.out)
        else:
            print("state %d: |disp| mean=%.2f max=%.2f  |v| mean=%.3f max=%.3f"
                  % (args.state, np.linalg.norm(cur - G['g0'], axis=1).mean(),
                     np.linalg.norm(cur - G['g0'], axis=1).max(),
                     np.linalg.norm(vel, axis=1).mean(),
                     np.linalg.norm(vel, axis=1).max()))
    if args.shake or args.shake_csv:
        rows = shake_metrics(G, dt_ms=args.dt, active_zmin=args.active_zmin)
        hdr = "i  t_ms  vrms_all vmax_all dmax_all | vrms_air vmax_air dmax_air"
        print(hdr)
        for r in rows:
            print("%3d %6.1f  %8.4f %8.3f %8.2f | %8.4f %8.3f %8.2f" %
                  (r['i'], r['t_ms'], r['vrms_all'], r['vmax_all'], r['dmax_all'],
                   r['vrms_air'], r['vmax_air'], r['dmax_air']))
        if args.shake_csv:
            import csv
            with open(args.shake_csv, 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
            print("已写 %s" % args.shake_csv)


if __name__ == '__main__':
    main()
