#!/usr/bin/env bash
# run_all.sh — 气帘 IGS 四分区一键链（从种子分类之后的步骤）
# 用法:
#   export WORKDIR="E:/work/AI_CAB/onekey/work/<proj>"
#   export HM_IN="curves.hm"        # 可选, 默认 curves.hm
#   export HM_OUT="partitioned.hm"  # 可选, 默认 partitioned.hm
#   bash run_all.sh
# 前置（人工/外部）:
#   1) IGS 导入 hm         -> $WORKDIR/curves.hm (1 个 comp)
#   2) t01/t02 导出        -> out/geom_features.txt + out/lines_pts.txt
#   3) 人工种子分类        -> out/classify_prev.json  ({"line_comp": {"1":"BELT",...}})
#     种子分类按 references/01_partition_rules.md 判据 + p05 渲染图人眼确认
set -euo pipefail

S="$(cd "$(dirname "$0")" && pwd)"          # 本 skill 的 scripts 目录
: "${WORKDIR:?must set WORKDIR to the project workspace}"
PY="${PY:-C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe}"
HMBATCH="${HMBATCH:-D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe}"

cd "$WORKDIR"
echo "== WORKDIR=$WORKDIR  HM_IN=${HM_IN:-curves.hm}  HM_OUT=${HM_OUT:-partitioned.hm}"

[ -f out/classify_prev.json ] || { echo "FATAL: out/classify_prev.json 不存在, 先做人工种子分类"; exit 1; }
[ -f out/geom_features.txt ]  || { echo "FATAL: out/geom_features.txt 不存在, 先跑 t01_export_geom.tcl"; exit 1; }
[ -f out/lines_pts.txt ]      || { echo "FATAL: out/lines_pts.txt 不存在, 先跑 t02_export_pts.tcl"; exit 1; }

echo "== 1/6 切线搭接扫描 (bridge_scan) =="
"$PY" "$S/p03_bridge_scan.py"

echo "== 2/6 应用修正 FIX -> classify_final.json + 环闭合 QA =="
"$PY" "$S/p04_classify_fix.py"      # FIX 字典在脚本里, 按 bridge_scan 输出人工填写后重跑

echo "== 3/6 渲染复核 (必须人眼看图确认后才继续!) =="
"$PY" "$S/p05_render_partition.py"
"$PY" "$S/q09_seam_check.py"
if [ "${SKIP_CONFIRM:-0}" != "1" ]; then
  echo "    >>> 检查 out/v_partition.png / v_partition_all.png, 人眼确认后回车继续 (SKIP_CONFIRM=1 可跳过) <<<"
  read -r _
fi

echo "== 4/6 导出 Tcl id 列表 =="
"$PY" "$S/p06_export_class_lists.py"

echo "== 5/6 搬线建 4 comp (hmbatch) =="
rm -f "${HM_OUT:-partitioned.hm}"    # P35: *writefile 前必须删旧文件
"$HMBATCH" -tcl "$S/t07_make_comps.tcl"
grep -q "ALL_OK=1" out/make_comps_report.txt || { echo "FATAL: make_comps 失败, 看 out/make_comps_report.txt"; exit 1; }

echo "== 6/6 独立回读校验 (hmbatch) =="
"$HMBATCH" -tcl "$S/t08_verify_partitioned.tcl"
grep -q "VERIFY_FAIL=0" out/verify_partitioned.txt || { echo "FATAL: verify 失败, 看 out/verify_partitioned.txt"; exit 1; }

echo "== DONE: $WORKDIR/${HM_OUT:-partitioned.hm} =="
grep -E "OK|TOTAL" out/verify_partitioned.txt | head -12
