#!/bin/sh
# ============================================================================
# ref_bench.sh —— 把参考 deck 造一份"5 ms 基准算例"，用来给判据标定阈值
#
# 用法:
#     ./ref_bench.sh <ref_deck_src> <ref_bench_dir> [endtim] [d3plot_dt]
#
# 为什么必须做这件事
#   本轮有 3 次把"正常现象"判成故障（SPR 按 t³ 涨、拉带末端超调、车身不动），
#   全靠同刻对照推翻。只比绝对量级毫无意义 —— 必须有个同源基准。
#
# 改动只有两处（其余卡片一个数不动，才叫"参考"）:
#   *CONTROL_TERMINATION    ENDTIM   200 -> 5.0
#   *DATABASE_BINARY_D3PLOT DT       2.5 -> 0.25   （细帧，便于看上升初期）
#
# 产出
#   <ref_bench_dir>/glstat  -> 交给 scripts/cmp_energy.py 做同刻比对
#   <ref_bench_dir>/d3plot* -> 交给 scripts/check_tethers.py 看参考的拉带行为
# ============================================================================
set -u

SRC="${1:?用法: ./ref_bench.sh <ref_deck_src> <ref_bench_dir> [endtim] [d3plot_dt]}"
DST="${2:?缺少目标目录}"
ENDTIM="${3:-5.0}"
D3DT="${4:-0.25}"

mkdir -p "$DST" || exit 1
cp -f "$SRC"/*.k "$SRC"/*.key "$DST"/ 2>/dev/null
echo "[ref_bench] 已拷 deck: $(ls "$DST" | tr '\n' ' ')"

python - "$DST" "$ENDTIM" "$D3DT" <<'PY'
import os, sys, glob
dst, endtim, d3dt = sys.argv[1], sys.argv[2], sys.argv[3]

def patch(path, kw, value, ndata_lines=1):
    """把 *KW 卡片后第一条数据行的第一字段替换成 value（定宽或逗号均可）"""
    lines = open(path, encoding='ascii', errors='ignore').read().split('\n')
    hit = 0
    for i, ln in enumerate(lines):
        if ln.strip().upper().startswith(kw):
            for j in range(i + 1, min(i + 1 + ndata_lines + 4, len(lines))):
                s = lines[j]
                if not s.strip() or s.lstrip().startswith('$'):
                    continue
                if ',' in s:
                    f = s.split(',')
                    f[0] = '%10s' % value
                    lines[j] = ','.join(f)
                else:
                    lines[j] = '%10s' % value + s[10:]
                hit += 1
                break
            break
    if hit:
        open(path, 'w', encoding='ascii').write('\n'.join(lines))
    return hit

n1 = n2 = 0
for f in glob.glob(os.path.join(dst, '*')):
    if not f.lower().endswith(('.k', '.key')):
        continue
    n1 += patch(f, '*CONTROL_TERMINATION', endtim)
    n2 += patch(f, '*DATABASE_BINARY_D3PLOT', d3dt)
print('[ref_bench] ENDTIM -> %s (%d 处)，D3PLOT dt -> %s (%d 处)' % (endtim, n1, d3dt, n2))
if not n1:
    print('[ref_bench] !! 没找到 CONTROL_TERMINATION，检查 main.key 的 INCLUDE 是否指向本目录')
PY

echo "[ref_bench] 下一步:"
echo "    cd $DST && ../run_deck.sh . 2 main.log"
echo "    然后: python ../cmp_energy.py <本模型目录> $DST"
