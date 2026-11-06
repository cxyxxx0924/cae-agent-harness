#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
d3plot_reader.py —— NEW_CAB / 气帘 LS-DYNA 计算结果的 d3plot 二进制逆向读取器
================================================================================
本机 d3plot 写盘约定（本机 LS-DYNA R10.1.0 rev123264，本项目写盘布局）已实测逆向，
numpy 直接可读，**不需要 LS-PrePost / HyperView / MCP**。

【主 d3plot（纯几何文件，无状态数据）布局】
  标题       : 64 词 = 10 词标题 + 54 词控制块
              控制块内：word16(0基)=NUMNOD, word31(0基)=NUMEL
  节点坐标   : @word64, 3 float32/节点, 共 3*NUMNOD 词 (节点 i -> word 64+3*(i-1))
  单元连接   : @word(64+3*NUMNOD) [=258328], **int32**, 每单元 5 词 = n1,n2,n3,n4,part索引
              ★ 必须按 int32 读！按 float32 读会得到 1e-41 级小数，误判为"全零"
  目录       : @(连接区尾) 16 词 int32（含 -1，按 float 读成 NaN）
  节点ID表   : NUMNOD 词;  单元ID表: NUMEL 词
  零填充     : 尾部

【状态文件 d3plotNN（状态数据）布局】
  头部       : 140 词
  坐标(当前) : @word140, 3 float32/节点, 节点序 = 节点ID序
  速度       : @word(140+3*NUMNOD) [=258404]
  加速度     : @word(140+2*3*NUMNOD) [=516668]
  ★ 固定节点判据：当前坐标与初始坐标逐位相等 (max|Δ|==0.0)；这是验证"某节点是否被固定"的硬判据

【时刻标定】
  状态文件头部不直接含可读时间。标定方法：速度RMS → KE_est=½·M·vRMS² → 与 glstat 的
  kinetic energy 序列匹配。本项目实测：d3plot03≈4.4ms / 05≈9.4ms / 08≈17ms / 09-10≈20ms。

用法：
  python d3plot_reader.py --geom d3plot --state d3plot09 --deck newcab_calc.k \
                          --out out_d3p09
  输出：打印固定节点校验 / 腔体体积 / 各 part 平均位移，并写 <out>.npz (coords/vel/accel/displ)。
"""
import numpy as np
import sys, os, re, argparse, json


def load_geom(geom_path):
    """读主 d3plot，返回 (N, NE, g0[N,3], E[NE,5]=int32, pid分布)"""
    g = np.fromfile(geom_path, dtype=np.float32)
    gi = np.fromfile(geom_path, dtype=np.int32)
    # 控制块：word16=NUMNOD, word31=NUMEL (0基)。整数头字段必须用 int32 视图取！
    # （float32 视图下这些位模式会错位成 0.0，曾导致 N=0 解析失败）
    N = int(gi[16]); NE = int(gi[31])
    assert N > 0 and NE > 0, "控制块 NUMNOD/NUMEL 解析失败: N=%d NE=%d" % (N, NE)
    g0 = g[64:64 + 3 * N].reshape(N, 3)
    conn = gi[64 + 3 * N: 64 + 3 * N + 5 * NE].reshape(-1, 5)
    n1, n2, n3, n4, pid = conn[:, 0], conn[:, 1], conn[:, 2], conn[:, 3], conn[:, 4]
    return N, NE, g0, (n1, n2, n3, n4, pid)


def load_state(state_path, N):
    """读状态文件，返回 (cur[N,3], vel[N,3], acc[N,3])。头部140词。"""
    a = np.fromfile(state_path, dtype=np.float32)
    H = 140
    n3 = 3 * N
    cur = a[H:H + n3].reshape(N, 3)
    vel = a[H + n3:H + 2 * n3].reshape(N, 3)
    acc = a[H + 2 * n3:H + 3 * n3].reshape(N, 3)
    return cur, vel, acc


def parse_fixed(deck_path, sids):
    """从 deck 的 *SET_NODE_LIST 解析固定节点 id 集合（自动跳过 sid 行，避免误读 sid 号当节点）。"""
    if not deck_path:
        return set()
    txt = open(deck_path, 'r', errors='ignore').read()
    lines = txt.splitlines()
    fixed = set()
    i = 0
    while i < len(lines):
        L = lines[i].strip()
        if L.upper().startswith('*SET_NODE_LIST'):
            sid = None
            if ',' in L:
                try:
                    sid = int(float(L.split(',')[1]))
                except Exception:
                    sid = None
            i += 1
            if sid is None:
                try:
                    sid = int(float(lines[i].split(',')[0])); i += 1
                except Exception:
                    sid = None
            buf = []
            while i < len(lines) and not lines[i].strip().startswith('*'):
                for tok in lines[i].split(','):
                    tok = tok.strip()
                    if tok:
                        try:
                            v = float(tok)
                            if v == int(v) and int(v) > 0:
                                buf.append(int(v))
                        except Exception:
                            pass
                i += 1
            if sid in sids:
                fixed.update(buf)
            continue
        i += 1
    return fixed


def poly_volume(coords, n1, n2, n3, n4):
    """4 节点壳单元包络体积的散度定理估算（用于气腔充气体积）。"""
    p1, p2, p3, p4 = coords[n1 - 1], coords[n2 - 1], coords[n3 - 1], coords[n4 - 1]
    v = (np.einsum('ij,ij->i', p1, np.cross(p2, p3))
         + np.einsum('ij,ij->i', p1, np.cross(p3, p4))
         + np.einsum('ij,ij->i', p1, np.cross(p4, p2)))
    return abs(v.sum()) / 6.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--geom', required=True, help='主 d3plot（几何）')
    ap.add_argument('--state', required=True, help='状态文件 d3plotNN')
    ap.add_argument('--deck', default='', help='deck .k（解析 *SET_NODE_LIST 固定节点）')
    ap.add_argument('--sids', default='900001,900010-900023',
                    help='固定节点 set 的 sid 列表，逗号或 a-b 区间')
    ap.add_argument('--mass', type=float, default=0.70067, help='织物总质量(kg)，用于速度RMS↔KE标定')
    ap.add_argument('--out', default='', help='输出 .npz 前缀（不填则不写）')
    args = ap.parse_args()

    sids = set()
    for tok in args.sids.split(','):
        tok = tok.strip()
        if '-' in tok:
            a, b = tok.split('-')
            sids.update(range(int(a), int(b) + 1))
        elif tok:
            sids.add(int(tok))

    N, NE, g0, (n1, n2, n3c, n4, pid) = load_geom(args.geom)
    cur, vel, acc = load_state(args.state, N)
    print("节点数 N=%d, 单元数 NE=%d" % (N, NE))
    print("part索引分布:", {int(k): int(v) for k, v in
          __import__('collections').Counter(pid.tolist()).items()})

    # 固定节点校验
    fixed = parse_fixed(args.deck, sids)
    if fixed:
        F = np.array(sorted(fixed)) - 1
        d = np.abs(cur[F] - g0[F])
        print("固定节点数=%d  当前坐标 vs 初始 max|Δ|=%.3e (应=0.0 才证明完全固定)" %
              (len(fixed), d.max()))
        # 自由节点位移
        free = np.setdiff1d(np.arange(N), F)
        Df = cur[free] - g0[free]
        dn = np.linalg.norm(Df, axis=1)
        print("自由节点位移: mean=%.2f med=%.2f p99=%.2f max=%.2f mm" %
              (dn.mean(), np.median(dn), np.percentile(dn, 99), dn.max()))

    # 各 part 平均位移 + 腔体体积
    names = {1: '布带BELT', 2: '气腔CAVITY', 3: '缝线SEAM', 4: '拉带TETHER'}
    for p in sorted(set(pid.tolist())):
        m = pid == p
        nodes = np.unique(np.concatenate([n1[m], n2[m], n3c[m], n4[m]])) - 1
        dd = cur[nodes] - g0[nodes]
        dn = np.linalg.norm(dd, axis=1)
        print("%-12s 单元%6d 节点%6d  平均位移(%+.2f,%+.2f,%+.2f) |d|mean=%.2f max=%.2f"
              % (names.get(int(p), 'part%d' % p), m.sum(), len(nodes),
                 dd[:, 0].mean(), dd[:, 1].mean(), dd[:, 2].mean(), dn.mean(), dn.max()))
        if m.sum() > NE * 0.3:  # 最大 part 视为气腔
            vol0 = poly_volume(g0, n1[m], n2[m], n3c[m], n4[m]) / 1e6
            vol1 = poly_volume(cur, n1[m], n2[m], n3c[m], n4[m]) / 1e6
            print("   -> 包络体积 %.3f -> %.2f L" % (vol0, vol1))

    # 速度 RMS ↔ KE
    vrms = np.sqrt((vel ** 2).sum(1).mean())
    ke = 0.5 * args.mass * vrms ** 2
    print("速度 RMS=%.4f mm/ms  -> KE_est=%.3f J (对照 glstat kinetic energy)" % (vrms, ke))

    if args.out:
        np.savez(args.out, coords=cur, velocity=vel, accel=acc,
                 initial=g0, partid=pid)
        print("已写 %s.npz" % args.out)


if __name__ == '__main__':
    main()
