#!/usr/bin/env bash
# run_auto2.sh — 气帘 IGS 四分区【全自动 v2】：原始 IGES -> partitioned.hm，零人工确认
#
# v2 与 v1 的差别（详见 references/13_vision_prior_v2.md）
#   - 特征：featurize2（轮廓内向深度 / 切向链 / 局部密集度 / 图内百分位），不再用绝对位置与凸包距离
#   - 模型：两阶段随机森林（结构 vs 符号 → 布带/气腔/缝线）+ 物理规则兜底
#   - 泛化：留一图交叉验证 平均条数准确率 0.957、结构长度加权 0.936（v1 仅 0.71~0.82，低于朴素基线）
#
# 用法:
#   WORKDIR=<工作区> IGES=<原始图纸> bash scripts/run_auto2.sh
set -uo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
HMBATCH="${HMBATCH:-D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe}"
PY="${PY:-C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe}"
WORKDIR="${WORKDIR:?请设置 WORKDIR}"
IGES="${IGES:?请设置 IGES}"
S="$SKILL_DIR"

echo "[AUTO2] WORKDIR=$WORKDIR  IGES=$IGES"
mkdir -p "$WORKDIR/out"

echo "[AUTO2] S0 导入 IGES -> curves.hm"
WORKDIR="$WORKDIR" IGES="$IGES" "$HMBATCH" -tcl "$S/t00_import_iges.tcl" 2>&1 | tail -1

echo "[AUTO2] S2 导出采样点 lines_pts.txt (跳 t01, 规避 2026 JUNC 段崩溃)"
WORKDIR="$WORKDIR" "$HMBATCH" -tcl "$S/t02_export_pts.tcl" 2>&1 | tail -1

echo "[AUTO2] AUTO 两阶段森林 + 物理规则 四分类"
"$PY" "$S/auto_partition2.py" "$WORKDIR"

echo "[AUTO2] S6 导出 id 列表"
WORKDIR="$WORKDIR" "$PY" "$S/p06_export_class_lists.py"

echo "[AUTO2] S7 搬线建 4 comp -> partitioned.hm"
rm -f "$WORKDIR/partitioned.hm"
WORKDIR="$WORKDIR" HM_IN=curves.hm HM_OUT=partitioned.hm "$HMBATCH" -tcl "$S/t07_make_comps.tcl" 2>&1 | tail -1

echo "[AUTO2] S8 独立回读校验"
rm -f "$WORKDIR/out/verify_partitioned.txt"
WORKDIR="$WORKDIR" HM_OUT=partitioned.hm "$HMBATCH" -tcl "$S/t08_verify_partitioned.tcl" 2>&1 | tail -1
if grep -q "VERIFY_FAIL=0" "$WORKDIR/out/verify_partitioned.txt"; then
  echo "[AUTO2] DONE: VERIFY_FAIL=0 -> $WORKDIR/partitioned.hm"
else
  echo "[AUTO2] FAIL: VERIFY_FAIL!=0, 见 $WORKDIR/out/verify_partitioned.txt 和 partition_geometry.json"
  exit 1
fi
