#!/usr/bin/env bash
# run_v9.sh — 四分区 v9 极简轮廓修正一键链（在 v8 初版四分区之后执行）
# 用法:
#   export WORKDIR="E:/work/AI_CAB/onekey/work/<proj>"   # 必须, 指向含 out/ 的工作区
#   export V9_SRC="newcab_classify8.json"                 # 可选, 默认规范 v8 (119/78/59/572)
#   export HM_IN="curves.hm"        # 可选, 默认 curves.hm
#   export HM_OUT="partitioned.hm"  # 可选, 默认 partitioned.hm
#   bash run_v9.sh
# 前置（通常来自 run_all.sh 的 v8 产物）:
#   1) IGS 导入 hm  -> $WORKDIR/curves.hm (1 个 comp)
#   2) t01/t02 导出 -> out/geom_features.txt + out/lines_pts.txt
#   3) 规范 v8 种子分类 -> out/newcab_classify8.json ({"line_comp":{"1":"BELT",...}})
#      (本脚本默认读 newcab_classify8.json；如种子分类叫别的名，用 V9_SRC 指定)
# 干的事（见 references/05_v9_minimal_contour.md）:
#   应用用户 2026-10-21 下午反馈的极简轮廓修正 -> 落 4 comp 到 partitioned.hm 并校验。
set -euo pipefail

S="$(cd "$(dirname "$0")" && pwd)"          # 本 skill 的 scripts 目录
: "${WORKDIR:?must set WORKDIR to the project workspace}"
PY="${PY:-C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe}"
HMBATCH="${HMBATCH:-D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe}"
V9_SRC="${V9_SRC:-newcab_classify8.json}"

cd "$WORKDIR"
echo "== WORKDIR=$WORKDIR  V9_SRC=$V9_SRC  HM_IN=${HM_IN:-curves.hm}  HM_OUT=${HM_OUT:-partitioned.hm}"

[ -f "out/$V9_SRC" ]           || { echo "FATAL: out/$V9_SRC 不存在, 先做规范 v8 种子分类"; exit 1; }
[ -f out/geom_features.txt ]   || { echo "FATAL: out/geom_features.txt 不存在, 先跑 t01_export_geom.tcl"; exit 1; }
[ -f out/lines_pts.txt ]       || { echo "FATAL: out/lines_pts.txt 不存在, 先跑 t02_export_pts.tcl"; exit 1; }

echo "== 1/7 应用 v9 极简轮廓修正 -> classify_v9.json (覆盖 classify_final.json) + 连通性 QA =="
V9_SRC="$V9_SRC" "$PY" "$S/v9_apply_fix.py"

echo "== 2/7 (可选) 问题区域侦察 — 看修正前后各区域线清单 =="
"$PY" "$S/v9_recon.py"    2>&1 | tail -3 || echo "  (v9_recon 跳过, 见 out/ 无输出亦可)"
"$PY" "$S/v9_recon2.py"   2>&1 | tail -3 || echo "  (v9_recon2 跳过)"

echo "== 3/7 渲染分区复核图 =="
"$PY" "$S/p05_render_partition.py"
"$PY" "$S/v9_render.py"    || echo "  (v9_render 需要 out/lines_pts.txt, 已存在则出图)"

if [ "${SKIP_CONFIRM:-0}" != "1" ]; then
  echo "    >>> 检查 out/v_partition.png / v_partition_all.png / v_v9_*.png, 人眼确认后回车继续 (SKIP_CONFIRM=1 可跳过) <<<"
  read -r _
fi

echo "== 4/7 导出 Tcl id 列表 =="
"$PY" "$S/p06_export_class_lists.py"

echo "== 5/7 搬线建 4 comp (hmbatch) =="
rm -f "${HM_OUT:-partitioned.hm}"    # *writefile 前必须删旧文件
"$HMBATCH" -tcl "$S/t07_make_comps.tcl"
grep -q "ALL_OK=1" out/make_comps_report.txt || { echo "FATAL: make_comps 失败, 看 out/make_comps_report.txt"; exit 1; }

echo "== 6/7 独立回读校验 (hmbatch) =="
"$HMBATCH" -tcl "$S/t08_verify_partitioned.tcl"
grep -q "VERIFY_FAIL=0" out/verify_partitioned.txt || { echo "FATAL: verify 失败, 看 out/verify_partitioned.txt"; exit 1; }

echo "== 7/7 渲染 v9 最终分区图 (特写) =="
"$PY" "$S/v9_render.py" || true

echo "== DONE: $WORKDIR/${HM_OUT:-partitioned.hm} =="
grep -E "OK|TOTAL" out/verify_partitioned.txt | head -12
