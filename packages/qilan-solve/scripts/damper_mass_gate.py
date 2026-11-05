#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
damper_mass_gate.py —— 离散阻尼器显式稳定门禁：C < 2m/dt（P-S50 / P-S51）
=========================================================================
用途：**跑之前**算出"锚点质量够不够养这个阻尼系数 C"，不够就给出补偿质量卡。
      把"跑完发现上拉段抖动"提前成"启动前就能算出来"。

原理：
  离散阻尼 F = C·v，显式中心差分的稳定极限  C < 2·m/dt。
  拉带锚点是纯网格节点，质量只有克级；参考 deck 的 C=0.2 在参考模型上稳定，
  搬到薄网格上就超临界 4~7 倍 → 每步过冲 → 数值注入能量 → 肉眼可见抖动（见 references/10）。

用法：
  # 自动从网格估算锚点质量（= 所属壳单元分摊 mass/4）
  python damper_mass_gate.py --deck Spring_swap.k --grid Spring_swap.k \
      --dt 4.95e-4 --c 0.2 --nodes 30112068,30112567,... --target 1.2e-4

  # 质量已知（推荐：从 d3plot 反算或已有实测），直接喂
  python damper_mass_gate.py --mass-csv anchors.csv --dt 4.95e-4 --c 0.2 --target 1.2e-4

  # 只出补偿卡，粘到 Spring_swap.k 末尾
  python damper_mass_gate.py ... --emit

单位：**tonne / mm / ms**（LS-DYNA 气帘标准单位制）。
      mass 输出双单位：tonne（写卡用）与 g（人看用，1 tonne = 1e6 g）。
      注意：1.2E-4 tonne = **120 g**，不是 120 mg —— 曾因这个换算差点把裕度算成 1000 倍。

退出码：0 = 全部锚点裕度足够；1 = 有超临界（需补质量或降 C——但降 C 属改参考参数，须用户批准）。
"""
import os, sys, re, argparse, math

SKIP_US = 0.5          # 建议 C/C_crit ≤ 0.5（即 2 倍以上裕度）


def split_any(line, width=None):
    """字段切分：逗号优先；否则按 width（缺省 10）切。"""
    s = line.rstrip('\r\n')
    if ',' in s:
        return [f.strip() for f in s.split(',')]
    body = s.rstrip()
    if not body:
        return []
    w = width or (8 if (len(body) % 10 != 0 and len(body) % 8 == 0) else 10)
    return [body[i:i + w].strip() for i in range(0, len(body), w)]


def fnum(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def read_deck(path, depth=0, seen=None):
    seen = seen or set()
    ap = os.path.abspath(path)
    if depth > 8 or ap in seen or not os.path.exists(ap):
        return []
    seen.add(ap)
    blocks, cur, inc = [], None, False
    base = os.path.dirname(ap)
    for raw in open(ap, errors='ignore'):
        line = raw.rstrip('\r\n')
        if inc:
            inc = False
            p = line.strip()
            if p and not p.startswith('$'):
                cand = p if os.path.isabs(p) else os.path.join(base, p)
                if not os.path.exists(cand):
                    cand = os.path.join(os.getcwd(), p)
                blocks.extend(read_deck(cand, depth + 1, seen))
            continue
        if line.startswith('$'):
            continue
        if line.lstrip().startswith('*'):
            kw = line.lstrip()[1:].strip().upper().split()[0] if line.lstrip()[1:].strip() else ''
            if kw in ('INCLUDE', 'INCLUDE_PATH_RELATIVE'):
                cur, inc = None, True
                continue
            cur = (kw, [])
            blocks.append(cur)
            continue
        if cur is not None and line.strip():
            cur[1].append(line)
    return blocks


def parse_model(paths):
    nodes, elems, parts, secs, mats = {}, {}, {}, {}, {}
    for p in paths:
        for kw, data in read_deck(p):
            if kw.endswith('_TITLE'):        # 参考/部分写卡器用 *_TITLE 变体，首行是标题文本
                kw, data = kw[:-6], data[1:]
            if kw == 'NODE':
                for l in data:
                    if ',' in l:
                        f = split_any(l)
                        if len(f) >= 4:
                            nodes[int(f[0])] = (fnum(f[1]), fnum(f[2]), fnum(f[3]))
                    else:
                        s = l.rstrip()
                        # 定宽 NODE: nid(8) + 3×16  或  4×8 / 4×10
                        if len(s) >= 56:
                            nodes[int(s[0:8])] = (fnum(s[8:24]), fnum(s[24:40]), fnum(s[40:56]))
                        else:
                            f = split_any(l)
                            if len(f) >= 4:
                                nodes[int(f[0])] = (fnum(f[1]), fnum(f[2]), fnum(f[3]))
            elif kw == 'ELEMENT_SHELL':
                for l in data:
                    f = split_any(l, 8 if ',' not in l and len(l.rstrip()) % 8 == 0 else 10)
                    if len(f) >= 4:
                        try:
                            elems[int(f[0])] = (int(f[1]), [int(x) for x in f[2:6] if x and x.lstrip('-').isdigit()])
                        except ValueError:
                            pass
            elif kw == 'PART':
                for l in data:
                    f = split_any(l)
                    if len(f) >= 3:
                        try:
                            parts[int(f[0])] = (int(f[1]), int(f[2]))
                        except ValueError:
                            pass
            elif kw == 'SECTION_SHELL':
                # 第一行 SECID, ELFORM, SHRF, NIP, PROPT, ...；厚度常在第二行 T1
                flat = []
                for l in data:
                    flat.extend(split_any(l))
                if flat:
                    sid = int(fnum(flat[0], -1))
                    t = 0.0
                    for i in (4, 5, 9, 10):
                        if i < len(flat) and fnum(flat[i]) > 0:
                            t = fnum(flat[i])
                            break
                    if sid >= 0:
                        secs[sid] = t
            elif kw.startswith('MAT_'):
                for l in data:
                    f = split_any(l)
                    if len(f) >= 12:          # PART 卡被误入保护（不会发生）
                        pass
                    if f:
                        mid = int(fnum(f[0], -1))
                        rho = None
                        for i in (1, 0):      # 绝大多数 MAT_* 的 RO 在 field1
                            if i < len(f) and fnum(f[i]) > 0:
                                rho = fnum(f[i])
                                break
                        if mid >= 0 and rho:
                            mats.setdefault(mid, rho)
    return nodes, elems, parts, secs, mats


def elem_area(coords):
    """四边形面积（对角线拆两三角形）；退化按三角形处理。"""
    if len(coords) < 3:
        return 0.0
    def tri(a, b, c):
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
    if len(coords) == 3:
        return tri(coords[0], coords[1], coords[2])
    return tri(coords[0], coords[1], coords[2]) + tri(coords[0], coords[2], coords[3])


def node_mass(nid, nodes, elems, parts, secs, mats):
    """节点质量估算 = Σ(所属壳单元 mass / 该单元节点数)。"""
    m = 0.0
    for _eid, (pid, nl) in elems.items():
        if nid not in nl:
            continue
        secid, mid = parts.get(pid, (0, 0))
        t = secs.get(secid, 0.0)
        rho = mats.get(mid, 0.0)
        cs = [nodes[x] for x in nl if x in nodes]
        if t <= 0 or rho <= 0 or len(cs) < 3:
            continue
        m += elem_area(cs) * t * rho / float(len(nl))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--deck', help='含 SPC/单元质量的 deck（可为任一 include）')
    ap.add_argument('--grid', action='append', default=[],
                    help='网格来源 K（可多次；缺省用 --deck）')
    ap.add_argument('--nodes', help='锚点节点，逗号/空格分隔')
    ap.add_argument('--mass-csv', help='nid,mass(tonne) 每行一条，覆盖网格估算')
    ap.add_argument('--dt', type=float, required=True, help='稳定时间步（ms，如 4.95e-4）')
    ap.add_argument('--c', type=float, default=0.2, help='MAT_DAMPER_VISCOUS 的 C（默认 0.2）')
    ap.add_argument('--target', type=float, default=1.2e-4,
                    help='锚点目标质量（tonne，默认 1.2e-4 = 120 g）')
    ap.add_argument('--emit', action='store_true', help='输出可粘贴的 *ELEMENT_MASS 卡')
    args = ap.parse_args()

    grid = args.grid or ([args.deck] if args.deck else [])
    mass = {}
    if args.mass_csv:
        for l in open(args.mass_csv, errors='ignore'):
            f = split_any(l)
            if len(f) >= 2:
                try:
                    mass[int(f[0])] = float(f[1])
                except ValueError:
                    pass
    nodes = [int(x) for x in re.split(r'[,\s]+', args.nodes or '') if x.strip().isdigit()]

    if not mass:
        if not grid:
            sys.exit('需要 --mass-csv 或 --deck/--grid')
        N, E, P, S, M = parse_model(grid)
        if not (N and E and P):
            sys.exit('网格解析失败（NODE/ELEMENT_SHELL/PART 不全）。请改用 --mass-csv 显式给质量。')
        if not nodes:
            sys.exit('请用 --nodes 指定锚点，或用 --mass-csv')
        for nid in nodes:
            mass[nid] = node_mass(nid, N, E, P, S, M)
        if all(v <= 0 for v in mass.values()):
            sys.exit('质量估算为 0（SECTION 厚度或 MAT 密度没解析到）。请用 --mass-csv。')

    print('=' * 84)
    print('离散阻尼显式稳定门禁   C=%.4g   dt=%.3e ms   C_crit = 2m/dt   建议 C/C_crit ≤ %.2f'
          % (args.c, args.dt, SKIP_US))
    print('=' * 84)
    print('  %-12s %12s %12s %10s %-8s %14s' % ('anchor nid', 'm (g)', 'C_crit', 'C/C_crit', '判定', '需补 (tonne)'))
    print('-' * 84)

    bad, adds = 0, []
    for nid in sorted(mass):
        m = mass[nid]
        if m <= 0:
            print('  %-12d %12s %12s %10s %-8s %14s' % (nid, '?', '?', '?', 'SKIP', '—'))
            continue
        ccrit = 2.0 * m / args.dt
        ratio = args.c / ccrit if ccrit > 0 else float('inf')
        need = max(args.target - m, 0.0)
        ok = ratio <= SKIP_US
        if not ok:
            bad += 1
        print('  %-12d %12.3f %12.5f %10.2f %-8s %14.5E'
              % (nid, m * 1e6, ccrit, ratio, 'PASS' if ok else 'FAIL', need))
        if need > 0:
            adds.append((nid, need))

    print('-' * 84)
    if bad:
        print('结论：FAIL —— %d/%d 个锚点的 C 超临界（C=%.4g 需要 m ≥ %.4g tonne = %.1f g 才满足 C<2m/dt）。'
              % (bad, len(mass), args.c, args.c * args.dt / 2.0, args.c * args.dt / 2.0 * 1e6))
        print('      推荐：保持 C 不变，用 *ELEMENT_MASS 补到 %.4g tonne（%.0f g），裕度 %.1f 倍。'
              % (args.target, args.target * 1e6, args.target / max(args.c * args.dt / 2.0, 1e-30)))
        print('      **不要**改 C 去适配薄网格 —— 那会破坏"与参考完全一致"（P-S49）。')
        if args.emit:
            print()
            print('*ELEMENT_MASS')
            print('$#   eid       nid                 mass')
            for k, (nid, need) in enumerate(adds):
                print('%d,%d,%.5E' % (25000001 + k, nid, need))
    else:
        print('结论：PASS —— 全部锚点 C/C_crit ≤ %.2f，阻尼器在显式积分下稳定。' % SKIP_US)
    print('=' * 84)
    sys.exit(0 if bad == 0 else 1)


if __name__ == '__main__':
    main()
