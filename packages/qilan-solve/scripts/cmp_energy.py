#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cmp_energy.py —— 本模型 vs 参考算例的 glstat 同刻对照（判断"能量异常是真故障还是固有特征"）。

用法
    python cmp_energy.py <this_deck_dir> <ref_deck_dir> [out.png]

原理
    单看绝对量级毫无意义。必须把参考 deck 自己跑一遍（见 ref_bench.sh），
    在同一时刻逐项比对 KE / IE / SPR / dt，偏差 < 10% 就是同源。
    本轮实测：t=0.8 ms 时 SPR 差 2.4% → 证明 t³ 增长是构造固有特征（references/11 §6）。

输出
    out.png  三联图（SPR 对数 / KE 对数 / dt 线性）
    终端    同刻插值对照表 + 偏差百分比
"""
import os
import re
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

KEYS = ('kinetic energy', 'internal energy', 'spring and damper energy',
        'time step', 'global z velocity', 'added mass', 'hourglass energy')


def parse_glstat(path):
    """glstat 是"标签 + 右对齐数值"，按 ' dt of cycle' 切块、从右往左切最后一个数"""
    if not os.path.exists(path):
        return None
    txt = open(path, encoding='ascii', errors='ignore').read()
    rows = []
    for blk in txt.split(' dt of cycle')[1:]:
        d = {}
        for line in blk.split('\n'):
            p = line.rsplit(None, 1)
            if len(p) != 2:
                continue
            k = re.sub(r'[.\s]+$', '', p[0]).strip().lower()
            try:
                d[k] = float(p[1])
            except ValueError:
                pass
        if 'time' in d:
            rows.append(d)
    if not rows:
        return None
    out = {'t': np.array([r['time'] for r in rows])}
    for k in KEYS:
        out[k] = np.array([r.get(k, 0.0) for r in rows])
    return out


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    a = parse_glstat(os.path.join(sys.argv[1], 'glstat'))
    b = parse_glstat(os.path.join(sys.argv[2], 'glstat'))
    out = sys.argv[3] if len(sys.argv) > 3 else 'energy_parity.png'
    if a is None or b is None:
        print('!! 缺少 glstat：%s 或 %s' % (sys.argv[1], sys.argv[2]))
        return 3

    print('%s : %d 帧  t=%.3f..%.3f ms' % (sys.argv[1], len(a['t']), a['t'][0], a['t'][-1]))
    print('%s : %d 帧  t=%.3f..%.3f ms' % (sys.argv[2], len(b['t']), b['t'][0], b['t'][-1]))

    fig, axs = plt.subplots(1, 3, figsize=(19, 5))
    for ax, (k, label, logy) in zip(axs, [('spring and damper energy', 'SPR energy (J)', True),
                                          ('kinetic energy', 'KE (J)', True),
                                          ('time step', 'dt (ms)', False)]):
        ax.plot(a['t'], a[k], '-o', ms=3, color='#2b7de9', label='this model')
        ax.plot(b['t'], b[k], '-s', ms=4, color='#e8442a', label='reference')
        ax.set_xlabel('time (ms)'); ax.set_ylabel(label)
        ax.set_title(label); ax.grid(alpha=.3); ax.legend(fontsize=8)
        if logy:
            ax.set_yscale('log')
    plt.suptitle('energy parity: this model vs reference at the same simulation time')
    plt.tight_layout(); plt.savefig(out, dpi=110)
    print('saved', out)

    # 同刻插值对照
    tend = min(a['t'][-1], b['t'][-1])
    grid = [x for x in (0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 4.0) if x <= tend]
    if not grid:
        return 0
    print('\n%8s %13s %13s %9s' % ('t(ms)', 'SPR_this', 'SPR_ref', 'dev%'))
    for tt in grid:
        va = float(np.interp(tt, a['t'], a['spring and damper energy']))
        vb = float(np.interp(tt, b['t'], b['spring and damper energy']))
        dev = 100 * (va - vb) / max(abs(vb), 1e-30)
        flag = '' if abs(dev) < 10 else '   <-- 偏离 >10%，查构造是否一致'
        print('%8.2f %13.4E %13.4E %8.2f%s' % (tt, va, vb, dev, flag))
    print('\n判定：各行 |dev%| < 10% => 同源，SPR 增长是构造固有特征，不是数值失稳。')
    print('      > 10% 时先 grep INCLUDE 确认参考算例是否包含同一套绳/车身（references/11 §6）。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
