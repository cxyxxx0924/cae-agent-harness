#!/usr/bin/env bash
# run_auto.sh — 气帘 IGS 四分区【全自动】模式（无需人工确认）
# 原始 IGES -> partitioned.hm，全程由"学到的气帘研判先验"(tree_model.json) 驱动。
# 用法:
#   WORKDIR=<工作区> IGES=<原始图纸> bash scripts/run_auto.sh
# 说明:
#   - 自动判定坐标平面 X-Y / X-Z
#   - 跳过 t01(几何特征, 仅 bridge 用; 本模式只用 lines_pts 采样点, 规避 2026 JUNC 段崩溃)
#   - auto_partition.py: 端点焊接+连贯性+视觉/功能/几何特征 -> 决策树 -> 四分类
#   - 末段 p06->t07->t08 与标准链路一致, 以 VERIFY_FAIL=0 为真门禁
set -uo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
HMBATCH="${HMBATCH:-D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe}"
PY="${PY:-C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe}"
WORKDIR="${WORKDIR:?请设置 WORKDIR}"
IGES="${IGES:?请设置 IGES}"
S="$SKILL_DIR"

echo "[AUTO] WORKDIR=$WORKDIR  IGES=$IGES"
mkdir -p "$WORKDIR/out"

echo "[AUTO] S0 导入 IGES -> curves.hm"
WORKDIR="$WORKDIR" IGES="$IGES" "$HMBATCH" -tcl "$S/t00_import_iges.tcl" 2>&1 | tail -1

echo "[AUTO] S2 导出采样点 lines_pts.txt (跳 t01, 规避 2026 JUNC 段崩溃)"
WORKDIR="$WORKDIR" "$HMBATCH" -tcl "$S/t02_export_pts.tcl" 2>&1 | tail -1

echo "[AUTO] AUTO 自动四分类(视觉/功能/连贯性 先验树)"
WORKDIR="$WORKDIR" TREE_MODEL="$S/tree_model.json" "$PY" "$S/auto_partition.py"

echo "[AUTO] S6 导出 id 列表"
WORKDIR="$WORKDIR" "$PY" "$S/p06_export_class_lists.py"

echo "[AUTO] S7 搬线建 4 comp -> partitioned.hm"
rm -f "$WORKDIR/partitioned.hm"
WORKDIR="$WORKDIR" HM_IN=curves.hm HM_OUT=partitioned.hm "$HMBATCH" -tcl "$S/t07_make_comps.tcl" 2>&1 | tail -1

echo "[AUTO] S8 独立回读校验"
rm -f "$WORKDIR/out/verify_partitioned.txt"
WORKDIR="$WORKDIR" HM_OUT=partitioned.hm "$HMBATCH" -tcl "$S/t08_verify_partitioned.tcl" 2>&1 | tail -1
if grep -q "VERIFY_FAIL=0" "$WORKDIR/out/verify_partitioned.txt"; then
  echo "[AUTO] DONE: VERIFY_FAIL=0 -> $WORKDIR/partitioned.hm"
else
  echo "[AUTO] WARN: VERIFY_FAIL!=0, 见 $WORKDIR/out/verify_partitioned.txt"
fi
