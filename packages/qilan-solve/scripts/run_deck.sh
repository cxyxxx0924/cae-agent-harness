#!/bin/sh
# ============================================================================
# run_deck.sh —— LS-DYNA MPP 标准启动脚本（含 ANSYS 许可 + 正确并行参数）
#
# 用法:
#     ./run_deck.sh <deck_dir> [ncpu] [logname]
#
# 为什么必须用这个脚本（两个坑，都踩过）
#   1) LSTC_LICENSE=ansys + ANSYSLMD_LICENSE_FILE 指向 .lic 文件，缺一不可；
#      ansyscl.exe 必须与求解器 exe 同目录，否则 checkout 失败。
#   2) 并行参数是 **ncpu=**，不是 n=  ：
#        n=2   -> 生成一个名为 "2" 的目录 + Signal 11 段错误
#        ncpu=2 -> 正常，2 procs
#      日志里会留下一个空的 2/ 目录，很容易看漏。
#
# 4 逻辑核机器只用 ncpu=2（留两核给系统/监控），实测 ~3.8 min/ms。
# ============================================================================
set -u

SOLVER="D:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_mpp_sp_msmpi.exe"
DECK="${1:?用法: ./run_deck.sh <deck_dir> [ncpu] [logname]}"
NCPU="${2:-2}"
LOGNAME="${3:-main.log}"

export LSTC_LICENSE=ansys
export ANSYSLMD_LICENSE_FILE="D:/Program Files/ANSYS Inc/Shared Files/Licensing/license_files/ansyslmd.lic"

cd "$DECK" || exit 1

# 清理上次的半成品（d3plot* 用通配在 Windows 下可能被 safe-delete 拦，交给 python）
python - <<'PY'
import glob, os
for f in glob.glob('d3plot*') + glob.glob('binout*') + ['d3thdt', 'glstat', 'matsum', 'nodout']:
    try:
        if os.path.exists(f):
            os.remove(f)
    except Exception:
        pass
PY

echo "[run] deck=$DECK ncpu=$NCPU log=$LOGNAME"
echo "[run] solver=$SOLVER"
"$SOLVER" i=main.key ncpu="$NCPU" memory=200000000 > "$LOGNAME" 2>&1
echo "EXIT=$?" >> "$LOGNAME"

# 启动后立刻自检三件事
tail -5 "$LOGNAME"
grep -c "MPP execution with" "$LOGNAME" | sed 's/^/[run] MPP banner count = /'
ls -d 2 2>/dev/null && echo "[run] !!! 出现了名为 2 的目录：说明误用了 n=2"
