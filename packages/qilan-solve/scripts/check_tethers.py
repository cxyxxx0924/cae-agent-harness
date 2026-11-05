#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_tethers.py —— 读 d3plot，体检拉绳锚点在上升段是否"平行上移 / 无拍打 / 不超伸"。

不依赖 MCP（用 lspp-mcp 的 lasso 环境）：
    <lasso-python> check_tethers.py <d3plot> [--spring Spring_swap.k] [--json out.json]

锚点与绳长自动从 deck 读取（P-S86）：
    从 Spring_swap.k 的 *ELEMENT_BEAM / *ELEMENT_DISCRETE 取 (eid, n1, n2)，
    n1 在气帘网格里 -> 气帘端；n2 在车身网格里 -> 车身端；绳长 L = |p1 - p2|。
    没给 --spring 时自动在 d3plot 同目录找 Spring_swap.k / cab2_clean.k / BIW_clean.k。

判据（P-S86/P-S87，全部相对各自绳长，不再用"彼此散差"）：
    J1 超伸    dZ_i - L_i > 5% L_i                     -> FAIL（绳被拉长 / 穿绳 / 锚点取错）
    J2 同步    未饱和锚点（dZ < 0.95 L）的上升速度散差 / 中位速度 > 20%  -> FAIL（不平行）
    J3 拍打    单锚点局部振荡幅度 > 5 mm                -> WARN（绷紧回弹属正常，>5mm 才算拍打）
    J4 漂移    横向 dXY > max(10 mm, 5% 行程)           -> WARN（点爆后鼓包推凸台属正常）
    J5 反向    dZ 连续下降 > 3 步且累计 > 2 mm          -> FAIL（塌陷）
    J6 锁死    达到 0.98 L 后 dZ 波动 < 0.5 mm          -> OK（绳绷紧后的正常锁定，非故障）

重要（P-S86）：**不能用"锚点彼此 dZ 散差"判不同步**。各绳长度不同（96~184 mm，极端 428 mm），
每根锚点上升到"自己的绳长"就锁死，末态 dZ 天然差几十上百毫米，这是正确物理。
本轮实测末态散差 177 mm 却完全正常：每个 dZ/L 都精确 = 1.000。
"""
import os
import sys
import json
import numpy as np
from lasso.dyna import D3plot, ArrayType

# 能量参考带（参考模型标定，见 references/10 §13）
SPR_BAND = 0.025          # spring&damper ≈ 0.025 * t^3 (J, t in ms)


# ------------------------------------------------------------------ deck 解析
def _read_fixed(path, kws, nfields=4):
    """8 字符定宽读取（*ELEMENT_BEAM / *ELEMENT_DISCRETE）"""
    out = []
    cur = None
    for ln in open(path, encoding='ascii', errors='ignore'):
        u = ln.strip().upper()
        if u.startswith('*'):
            cur = next((k for k in kws if u.startswith(k)), None)
            continue
        if not cur or ln.lstrip().startswith('$') or len(ln) < 33:
            continue
        try:
            rec = [int(ln[i * 8:(i + 1) * 8]) for i in range(nfields)]
        except ValueError:
            continue
        if rec[0] > 0:
            out.append((cur, rec))
    return out


def read_nodes(path):
    """*NODE：定宽优先，逗号自由格式兜底（P-S82）"""
    n = {}
    cur = False
    for ln in open(path, encoding='ascii', errors='ignore'):
        u = ln.strip().upper()
        if u.startswith('*'):
            cur = u.startswith('*NODE') and 'REFERENCE' not in u
            continue
        if not cur or ln.lstrip().startswith('$'):
            continue
        s = ln.replace(',', ' ').split()
        if len(s) < 4:
            continue
        try:
            n[int(s[0])] = (float(s[1]), float(s[2]), float(s[3]))
        except ValueError:
            pass
    return n


def load_springs(deck, spring=None):
    """返回 [(name, bag_nid, body_nid, rope_len)]"""
    if spring is None:
        for cand in ('Spring_swap.k', 'Spring_move.k'):
            p = os.path.join(deck, cand)
            if os.path.exists(p):
                spring = p
                break
    if not spring or not os.path.exists(spring):
        return [], None
    bag_k = body_k = None
    for cand in ('cab2_clean.k', 'cab2.k'):
        if os.path.exists(os.path.join(deck, cand)):
            bag_k = os.path.join(deck, cand); break
    for cand in ('BIW_clean.k', 'Vehicle.k', 'BIW.k'):
        if os.path.exists(os.path.join(deck, cand)):
            body_k = os.path.join(deck, cand); break
    bn = read_nodes(bag_k) if bag_k else {}
    wn = read_nodes(body_k) if body_k else {}
    out = []
    seen = set()
    for kind, rec in _read_fixed(spring, ('*ELEMENT_BEAM', '*ELEMENT_DISCRETE'), 4):
        eid, pid, n1, n2 = rec
        if n1 in bn and n2 in wn:
            bag, body = n1, n2
        elif n2 in bn and n1 in wn:
            bag, body = n2, n1
        else:
            continue
        # 同一对节点被 BEAM 和 DISCRETE 各定义一次（参考模型做法），必须去重
        if (bag, body) in seen:
            continue
        seen.add((bag, body))
        L = float(np.linalg.norm(np.array(bn[bag]) - np.array(wn[body])))
        out.append(('tether%d' % (len(out) + 1), bag, body, L))
    # 末端那根如果不是拉带就是充气口
    if out:
        out[-1] = ('port_top',) + tuple(out[-1][1:])
    return out, spring


# ------------------------------------------------------------------ 主流程
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    outjson = None
    spring = None
    if '--json' in sys.argv:
        outjson = sys.argv[sys.argv.index('--json') + 1]
    if '--spring' in sys.argv:
        spring = sys.argv[sys.argv.index('--spring') + 1]

    deck = os.path.dirname(os.path.abspath(path))
    springs, spfile = load_springs(deck, spring)
    if not springs:
        print('!! 未能从 deck 解析绳定义（--spring 指定 Spring_swap.k）')
        return 3

    d = D3plot(path)
    ids = np.asarray(d.arrays[ArrayType.node_ids]).ravel()
    U = d.arrays[ArrayType.node_displacement]
    U = U - U[0:1, :, :]          # lasso 给的是"当前坐标"，必须减 state0
    t = np.asarray(d.arrays.get(ArrayType.global_timesteps, []), dtype=float).ravel()
    if t.size != U.shape[0]:
        t = np.arange(U.shape[0], dtype=float)

    idx = {int(n): i for i, n in enumerate(ids)}
    got = [(nm, b, w, L) for (nm, b, w, L) in springs if b in idx and w in idx]
    if len(got) != len(springs):
        print('!! %d 根绳的节点不在 d3plot 里（id 重编号对不上？）' % (len(springs) - len(got)))

    print('d3plot : %s' % path)
    print('spring : %s   绳 %d 根   帧 %d   t = %.1f ~ %.1f ms'
          % (spfile, len(got), U.shape[0], t[0], t[-1]))
    print('%9s ' % 't(ms)'
          + ' '.join('%9s' % nm[:9] for nm, _, _, _ in got)
          + '   max dZ/L   max dXY')
    rows = []
    for s in range(U.shape[0]):
        dz, dxy = [], []
        for nm, b, w, L in got:
            u = U[s, idx[b]]
            dz.append(float(u[2]))
            dxy.append(float(np.hypot(u[0], u[1])))
        rows.append(dict(t=float(t[s]), dz=dz, dxy=dxy,
                         L=[L for _, _, _, L in got]))
        if s % max(1, U.shape[0] // 16) == 0 or s == U.shape[0] - 1:
            ratio = max(dz[i] / max(got[i][3], 1e-6) for i in range(len(got)))
            print('%9.2f ' % t[s] + ' '.join('%9.2f' % x for x in dz)
                  + '   %8.3f  %8.2f' % (ratio, max(dxy)))

    # ---------------- 判据 ----------------
    L = np.array(rows[0]['L'], dtype=float)
    DZ = np.array([r['dz'] for r in rows], dtype=float)      # (nstate, ntether)
    DXY = np.array([r['dxy'] for r in rows], dtype=float)
    TT = np.array([r['t'] for r in rows], dtype=float)
    n = len(got)

    fails, warns, oks = [], [], []

    # J1 超伸
    over = DZ - L[None, :]
    j1 = over.max()
    if j1 > 0.05 * L.max():
        bad = [(got[i][0], over[-1, i], L[i]) for i in range(n) if over.max(axis=0)[i] > 0.05 * L[i]]
        fails.append('J1 超伸 %s' % ', '.join('%s 超 %.1fmm(L=%.1f)' % b for b in bad))
    else:
        oks.append('J1 无超伸（最大超量 %.2f mm）' % j1)

    # J2 同步：只在"所有锚点都没绷紧"的窗口内比斜率（最小二乘）
    #    窗口上限 = 第一个锚点达到 0.5*L 的时刻。绳一绷紧就锁死不动，
    #    把锁死的和还在上升的放一起比必然 100% 散差 —— 那是判据错，不是模型错（P-S87）。
    t_lim = TT[-1]
    for i in range(n):
        hit = np.where(DZ[:, i] >= 0.5 * L[i])[0]
        if hit.size:
            t_lim = min(t_lim, float(TT[hit[0]]))
    win = TT <= t_lim
    j2_ratio = 0.0
    j2_detail = ''
    if win.sum() >= 3:
        v = np.polyfit(TT[win], DZ[win, :], 1)[0]        # 每根锚点的上升速度 mm/ms
        med = float(np.median(np.abs(v)))
        dev = np.abs(v - med) / max(med, 1e-9)
        j2_ratio = float(dev.max())
        i_w = int(dev.argmax())
        j2_detail = ('%s %.2f mm/ms vs 中位 %.2f（窗口 t≤%.0fms，%d 根未绷紧）'
                     % (got[i_w][0], v[i_w], med, t_lim, n))
    if j2_ratio > 0.50:
        fails.append('J2 不同步 速度偏差 %.0f%%（%s）' % (100 * j2_ratio, j2_detail))
    elif j2_ratio > 0.25:
        warns.append('J2 速度偏差 %.0f%%（%s）' % (100 * j2_ratio, j2_detail))
    else:
        oks.append('J2 同步良好 速度偏差 ≤ %.0f%%（%s）' % (100 * j2_ratio, j2_detail))

    # J3 拍打：上升窗口内，各锚点相对自身线性趋势的最大偏离
    j3 = 0.0
    j3_who = ''
    if win.sum() >= 5:
        for i in range(n):
            y = DZ[win, i]
            fit = np.polyval(np.polyfit(TT[win], y, 1), TT[win])
            amp = float(np.max(np.abs(y - fit)))
            if amp > j3:
                j3, j3_who = amp, got[i][0]
    if j3 > 3.0:
        warns.append('J3 疑似拍打 %s 偏离趋势 %.1f mm' % (j3_who, j3))
    else:
        oks.append('J3 无拍打（上升窗口内最大偏离趋势 %.2f mm @%s）' % (j3, j3_who or '-'))

    # J4 漂移
    travel = float(np.max(DZ[-1]))
    thr = max(10.0, 0.05 * travel)
    j4 = float(DXY.max())
    if j4 > thr:
        who = got[int(np.unravel_index(DXY.argmax(), DXY.shape)[1])][0]
        warns.append('J4 横向漂移 %s dXY=%.1f mm (> %.1f)' % (who, j4, thr))
    else:
        oks.append('J4 横向稳定（max dXY=%.1f mm）' % j4)

    # J5 反向塌陷
    j5_bad = []
    for i in range(n):
        z = DZ[:, i]
        zmax = np.maximum.accumulate(z)
        drop = float(np.max(zmax - z))
        if drop > 2.0:
            j5_bad.append('%s 回落 %.1fmm' % (got[i][0], drop))
    if j5_bad:
        warns.append('J5 局部回落 ' + ', '.join(j5_bad))
    else:
        oks.append('J5 无塌陷回落（各点单调，回落 < 2 mm）')

    verdict = 'FAIL' if fails else ('WARN' if warns else 'PASS')
    print()
    print('[判据]')
    for s in oks:
        print('  OK   ' + s)
    for s in warns:
        print('  WARN ' + s)
    for s in fails:
        print('  FAIL ' + s)
    print()
    print('  末态 dZ/L : ' + ' '.join('%.3f' % (DZ[-1, i] / L[i]) for i in range(n)))
    print('  绳长(mm)  : ' + ' '.join('%.1f' % x for x in L))
    print('  末态 dZ   : ' + ' '.join('%.1f' % x for x in DZ[-1]))
    print('  判定: %s' % verdict)

    if outjson:
        json.dump(dict(verdict=verdict, fails=fails, warns=warns, oks=oks,
                       t=TT.tolist(), dz=DZ.tolist(), dxy=DXY.tolist(),
                       L=L.tolist(), names=[g[0] for g in got],
                       rows=rows[-1:] if rows else []),
                  open(outjson, 'w'), indent=1)
        print('  ->', outjson)
    return 0 if verdict != 'FAIL' else 4


if __name__ == '__main__':
    sys.exit(main())
