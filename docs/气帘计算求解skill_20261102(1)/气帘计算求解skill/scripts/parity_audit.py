#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parity_audit.py —— 两份 LS-DYNA deck 的"逐卡逐字段"对齐审计（P-S49 / P-S54）
==========================================================================
用途：验证"我们的 deck 和参考模型完全一样"。逐关键字、逐块、逐字段对比，
      自动展开 *INCLUDE，把差异压到"哪张卡哪一块哪一字段，值 A vs B"。

为什么需要它：
  气帘项目里 90% 的"抄对了却不正常"都不是抄错，而是抄对了但模型条件不同（见 references/10）。
  要用这个结论，前提是"确实抄对了"——必须有一份可复核的字段级 diff，不能靠肉眼翻文件。

四项对齐处理（不这么做会全是假差异）：
  1. `*XXX_TITLE` 规范成 `*XXX`，丢弃紧随的标题行（参考常写 TITLE 变体）；
  2. 带 ID 的卡按 **ID 配对**（DEFINE_CURVE 用 LCID、MAT 用 MID、SECTION 用 SECID…），不按出现顺序；
  3. 自由文本字段（如接触卡第 2 字段被写成 `*CONTACT_...`）两边都是文本时只算 INFO；
  4. 数值按相对容差比，`1`/`1.0`/`1.000000` 视为同一。

用法：
  python parity_audit.py --ours main.key --ref <REF>/main.key --skip-bulk
  python parity_audit.py --ours main.key --ref <REF>/main.key --skip-bulk \
      --ack "CONTACT_AUTOMATIC_SINGLE_SURFACE_ID:1" \
      --ack "DATABASE_BINARY_D3DUMP:1" \
      --ack "CONSTRAINED_EXTRA_NODES_SET:*"

  --ack "KEYWORD:N"   声明该卡第 N 个字段（1 起）为已知等价差异 → 记 ACK 不计失败
  --ack "KEYWORD:*"   整卡登记（用于"我方有/参考无但物理无影响"的结构卡）
  --skip-bulk         跳过海量数据块（*NODE / *ELEMENT_* / *SET_* / RefGeom / *GROUP），推荐

退出码：0 = 无未声明差异；1 = 有差异（先修 deck，再谈"模型条件不同"）。
"""
import os, sys, re, argparse

BULK = {   # 海量数据 / 集合定义，不参与物理参数比对
    'NODE', 'ELEMENT_SHELL', 'ELEMENT_SOLID', 'ELEMENT_BEAM', 'ELEMENT_DISCRETE',
    'SET_NODE_LIST', 'SET_SHELL_LIST', 'SET_SOLID_LIST', 'SET_PART_LIST',
    'GROUP', 'SUBSET', 'PART', 'DEFORMABLE_TO_RIGID_AUTOMATIC',
    'AIRBAG_REFERENCE_GEOMETRY', 'INITIAL_FOAM_REFERENCE_GEOMETRY',
    'CONSTRAINED_EXTRA_NODES_NODE',
}
SKIP_KW = {'INCLUDE', 'INCLUDE_PATH_RELATIVE', 'INCLUDE_TRANSFORM', 'KEYWORD',
           'TITLE', 'END', 'PARAMETER', 'PARAMETER_EXPRESSION', 'PARAMETER_LOCAL'}
# 按"第一行的第一个字段"配对（ID 类卡）
KEYED = ('DEFINE_CURVE', 'MAT_', 'SECTION_', 'SET_', 'INTEGRATION_SHELL',
         'CONTACT_', 'SENSOR_', 'DATABASE_')


def split_fields(line, hint=None):
    """按 LS-DYNA 真实格式切字段；绝不全局去逗号（P-S17 教训）。

    hint：优先宽度候选。**曲线数据行是 20 字符定宽**（A1/E16 双精度），
          按 10 切会把 2 个值切成 4 段全错位（实测踩过）。
    `&` 续行标记（LSTC 写卡产物，如 `1.0&TTF`）单独成段时丢弃。
    """
    s = line.rstrip('\r\n')
    if ',' in s:
        parts = [f.strip() for f in s.split(',')]
        return [p for p in parts if not p.startswith('&')]
    body = s.rstrip()
    if not body:
        return []
    cands = hint or [10, 8]
    try:
        cands = [int(h) for h in (cands if isinstance(cands, (list, tuple)) else [cands])]
    except (TypeError, ValueError):
        cands = [10]
    for w in cands:
        if len(body) % w == 0 or w == cands[-1]:
            raw = [body[i:i + w].strip() for i in range(0, len(body), w)]
            break
    else:
        raw = [body[i:i + 10].strip() for i in range(0, len(body), 10)]
    out = []
    for p in raw:
        if p.startswith('&'):        # 续行标记，不是字段
            continue
        if '&' in p:                 # '1.0&TTF' → 1.0
            p = p.split('&')[0].strip()
        out.append(p)
    return out


def width_hint(kw):
    """按关键字给宽度候选（顺序=优先级）。"""
    if kw.startswith('DEFINE_CURVE'):
        return [20, 10, 8]
    if kw in ('NODE',):
        return [8, 10]
    return [10, 8]


def isnum(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def eq(a, b, tol):
    """返回 'ok' / 'soft'（文本或 0-空 等价差异）/ 'hard'。"""
    if a == '' and b == '':
        return 'ok'
    if isnum(a) and isnum(b):
        return 'ok' if abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)), abs(float(b))) else 'hard'
    if a.strip().upper() == b.strip().upper():
        return 'ok'
    # 一边空 / 0，另一边文本或数值 → 视为默认值等价
    if a == '' or b == '':
        other = b if a == '' else a
        return 'soft' if (not isnum(other) or float(other) == 0.0) else 'hard'
    if not isnum(a) and not isnum(b):
        return 'soft'      # 标题/注释字段
    return 'hard'          # 一数值一文本


def read_deck(path, depth=0, seen=None):
    """递归展开 *INCLUDE，返回 [(keyword, [dataline...])]（保持文件顺序）。"""
    seen = seen or set()
    ap = os.path.abspath(path)
    if depth > 8 or ap in seen:
        return []
    seen.add(ap)
    if not os.path.exists(ap):
        print('  !! 文件不存在: %s' % ap, file=sys.stderr)
        return []
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
        st = line.lstrip()
        if st.startswith('*'):
            kw = st[1:].strip().upper()
            kw = kw.split()[0] if kw else ''
            if kw in ('INCLUDE', 'INCLUDE_PATH_RELATIVE'):
                cur, inc = None, True
                continue
            if kw in SKIP_KW:
                cur = None
                continue
            if kw.endswith('_TITLE'):      # 规范化：标记丢首行标题，见 normalize()
                cur = ('@@TITLE@@' + kw[:-6], [])
                blocks.append(cur)
                continue
            cur = (kw, [])
            blocks.append(cur)
            continue
        if cur is not None and line.strip():
            cur[1].append(line)
    return blocks


def normalize(blocks):
    """把 '@@TITLE@@XXX' 还原成 'XXX' 并去掉首行标题；非 TITLE 块保持原样。"""
    out = []
    for kw, data in blocks:
        if kw.startswith('@@TITLE@@'):
            real = kw[9:]
            out.append((real, data[1:] if data else []))
        else:
            out.append((kw, data))
    return out


def block_key(kw, data, idmap=None):
    """ID 类卡取首行首字段作配对 key；命中 idmap 时按偏移换算（跨模型重编号 P-S19）。"""
    if any(kw.startswith(p) for p in KEYED) and data:
        f = split_fields(data[0], width_hint(kw))
        for v in f[:3]:
            if isnum(v):
                n = int(float(v))
                if idmap:
                    for pre, off in idmap.items():
                        if kw.startswith(pre) and n - off > 0:   # 只对"确实加过偏移"的段生效
                            n -= off
                            break
                return 'id:%d' % n
    return None


def build_index(blocks, skip_bulk, idmap=None):
    idx = {}
    for kw, data in blocks:
        if skip_bulk and kw in BULK:
            continue
        d = idx.setdefault(kw, {})
        k = block_key(kw, data, idmap)
        if k is None or k in d:
            k = 'seq%d' % len(d)
        d[k] = data
    return idx


def pair_keys(od, rd):
    """先按 key 配交集；剩余块**数量相等**时才按顺序补对（ID 整体偏移场景）。
    数量不等说明真有多/缺块，宁可报出来也不硬配（硬配会造出几十条假字段差异）。"""
    common = [k for k in rd if k in od]
    ro = [k for k in od if k not in rd]
    rr = [k for k in rd if k not in od]
    pairs = [(k, k) for k in common]
    if len(ro) == len(rr):
        pairs += list(zip(ro, rr))
    else:
        pairs += [(k, None) for k in ro] + [(None, k) for k in rr]
    return pairs


def is_blank_row(f):
    """全 0 / 全空的补白行（接触卡第 4 行 A3 卡之类）→ 物理无意义，差异算 soft。"""
    return all((x == '' or (isnum(x) and float(x) == 0.0)) for x in f)


def cmp_block(ours, ref, tol, kw=''):
    """返回 (硬差异[], 软差异[])。软差异=文本字段/0-空/补白行 这类物理等价差异。"""
    hard, soft = [], []
    hint = width_hint(kw)
    n = max(len(ours), len(ref))
    for li in range(n):
        h = [10, 8] if (kw.startswith('DEFINE_CURVE') and li == 0) else hint
        lo = split_fields(ours[li], h) if li < len(ours) else None
        lr = split_fields(ref[li], h) if li < len(ref) else None
        if lo is None:
            if is_blank_row(lr):
                soft.append('line%d: 参考有补白行（全 0），我方未写' % (li + 1))
                continue
            hard.append('line%d: 我方缺该行（参考=%s）' % (li + 1, '|'.join(lr)[:70]))
            continue
        if lr is None:
            if is_blank_row(lo):
                soft.append('line%d: 我方有补白行（全 0），参考未写（P-S17 允许）' % (li + 1))
                continue
            hard.append('line%d: 我方多该行（我方=%s）' % (li + 1, '|'.join(lo)[:70]))
            continue
        for fi in range(max(len(lo), len(lr))):
            a = lo[fi] if fi < len(lo) else ''
            b = lr[fi] if fi < len(lr) else ''
            r = eq(a, b, tol)
            if r == 'ok':
                continue
            msg = 'line%d field%d: 我方=%r 参考=%r' % (li + 1, fi + 1, a, b)
            (soft if r == 'soft' else hard).append(msg)
    return hard, soft


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ours', required=True)
    ap.add_argument('--ref', required=True)
    ap.add_argument('--ack', action='append', default=[], help='"KEYWORD:N" 或 "KEYWORD:*"')
    ap.add_argument('--id-map', action='append', default=[],
                    help='"DEFINE_CURVE:+30000000"：我方该卡 ID 整体加了偏移，配对时先减回（P-S19）')
    ap.add_argument('--ignore', default='',
                    help='逗号分隔：不参与比对的关键字/前缀（如车身自带的 SECTION_SHELL,MAT_RIGID）')
    ap.add_argument('--skip-bulk', action='store_true')
    ap.add_argument('--tol', type=float, default=1e-9)
    ap.add_argument('--ack-ours-extra', action='store_true',
                    help='把我方多出的块/整卡记为 ACK（"多"通常无害；"缺"仍算失败）')
    ap.add_argument('--diff-only', action='store_true')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    ack = {}
    for item in args.ack:
        kw, _, n = item.partition(':')      # 第一个冒号切分（值里可能还有 ':'，如 key=id:2）
        if not kw:
            kw, n = item, '*'
        ack.setdefault(kw.strip().upper(), set()).add(n.strip())

    def acked(kw, msg):
        """--ack 支持三级：'*' 整卡 / 'field=N' 或 'N' 字段 / 'key=K' 单块。"""
        s = ack.get(kw)
        if not s:
            return False
        if '*' in s:
            return True
        mk = msg.split(' ')[0] if msg.startswith('key=') else ''
        if mk and mk.endswith(':'):
            mk = mk[:-1]
        if mk and ('key=' + mk[4:]) in s:
            return True
        mf = re.search(r'field(\d+)', msg)
        if mf and (mf.group(1) in s or 'field=' + mf.group(1) in s):
            return True
        return False

    idmap = {}
    for item in args.id_map:
        kw, _, off = item.rpartition(':')
        try:
            idmap[kw.strip().upper()] = int(off)
        except ValueError:
            sys.exit('--id-map 格式："KEYWORD:+30000000"')

    print('=' * 80)
    print('deck 对齐审计')
    print('  ours = %s' % os.path.abspath(args.ours))
    print('  ref  = %s' % os.path.abspath(args.ref))
    if idmap:
        print('  id-map = %s' % idmap)
    print('=' * 80)

    O = build_index(normalize(read_deck(args.ours)), args.skip_bulk, idmap)
    R = build_index(normalize(read_deck(args.ref)), args.skip_bulk)

    n_match = n_ack = n_info = n_diff = n_miss = 0
    rows = []
    ignore = tuple(x.strip().upper() for x in args.ignore.split(',') if x.strip())
    order = [k for k in (list(R.keys()) + [k for k in O.keys() if k not in R])
             if not (ignore and k.startswith(ignore))]

    for kw in order:
        od, rd = O.get(kw), R.get(kw)
        if od is None or rd is None:
            side = ('我方缺整卡' if od is None else '我方多整卡') + \
                   ('（参考 %d 块）' % len(rd) if od is None else '（我方 %d 块）' % len(od))
            if acked(kw, '') or (od is not None and args.ack_ours_extra):
                n_ack += 1
                rows.append(('ACK', kw, side, []))
            else:
                n_miss += 1
                rows.append(('MISS', kw, side, []))
            continue
        keys = pair_keys(od, rd)
        hard_all, soft_all, ack_all = [], [], []
        for ko, kr in keys:
            if ko is None or kr is None:
                msg = 'key=%s: %s' % (kr if ko is None else ko,
                                      '我方缺该块' if ko is None else '我方多该块')
                if acked(kw, msg) or (ko is not None and args.ack_ours_extra):
                    ack_all.append(msg)
                else:
                    hard_all.append(msg)
                continue
            hard, soft = cmp_block(od[ko], rd[kr], args.tol, kw)
            for m in hard:
                msg = 'key=%s %s' % (kr, m)
                (ack_all if acked(kw, msg) else hard_all).append(msg)
            soft_all.extend('key=%s %s' % (kr, m) for m in soft)
        if hard_all:
            n_diff += 1
            rows.append(('DIFF', kw, '%d 处字段差异' % len(hard_all), hard_all + soft_all))
        elif ack_all:
            n_ack += 1
            rows.append(('ACK', kw, '%d 处已登记差异' % len(ack_all), ack_all + soft_all))
        elif soft_all:
            n_info += 1
            rows.append(('INFO', kw, '%d 处文本字段不同（物理等价）' % len(soft_all), soft_all))
        else:
            n_match += 1
            rows.append(('MATCH', kw, '%d 块一致' % len(rd), []))

    for tag, kw, note, det in rows:
        if args.diff_only and tag in ('MATCH', 'INFO'):
            continue
        print('[%-5s] %-50s %s' % (tag, kw, note))
        show = det if (tag in ('DIFF', 'MISS') or args.verbose) else []
        for d in show[:8]:
            print('          └ %s' % d)
        if len(show) > 8:
            print('          └ ... 共 %d 处' % len(show))

    print('-' * 80)
    print('MATCH=%d  ACK=%d  INFO=%d  DIFF=%d  MISS=%d   共 %d 个关键字'
          % (n_match, n_ack, n_info, n_diff, n_miss, len(order)))
    if n_diff or n_miss:
        print('结论：FAIL —— 有未声明差异。先修 deck，再用 --ack 登记"物理等价"的偏离（并写清理由）。')
        sys.exit(1)
    print('结论：PASS —— 设置类卡片与参考一致（差异均已登记为等价）')


if __name__ == '__main__':
    main()
