#!/usr/bin/env bash
# run_full.sh — 气帘 CAD 四分区 **端到端** 一键链（原始 IGES/IGS → 4 组 partitioned.hm）
#
# 用法（换项目只改 3 个环境变量，脚本内零硬编码）:
#   export WORKDIR="E:/work/AI_CAB/onekey/work/<proj>"       # 工作区（英文路径！P40/P41）
#   export IGES="E:/.../Drawing0904ZHEDIETU.iges"            # 原始 CAD（可选，已有 curves.hm 可省）
#   export SEED="newcab_classify8.json"                      # 人工种子分类 json（在 out/ 下）
#   export DELTA="v14"                                       # v9/v10/v12/v13/v14/none，默认 none
#   SKIP_CONFIRM=1 bash run_full.sh
#
# 阶段（可断点续跑：已存在产物且未设 FORCE 的阶段自动跳过）:
#   S0  IGES 导入        -> curves.hm              (t00_import_iges.tcl)
#   S1  几何特征导出     -> out/geom_features.txt  (t01_export_geom.tcl)
#   S2  采样点导出       -> out/lines_pts.txt      (t02_export_pts.tcl)
#   S3  【人工】种子分类 -> out/$SEED              判据见 references/01_partition_rules.md
#   S4  应用修正 delta   -> out/classify_final.json (v9…v14 累积，DELTA=none 则直接复制种子)
#   S5  渲染 + 终检报告  -> out/v_partition*.png + out/final_report.txt（人工看图确认）
#   S6  导出 Tcl id 列表 -> out/class_lists.tcl    (p06)
#   S7  搬线建 4 comp    -> partitioned.hm         (t07, hmbatch)
#   S8  独立回读校验     -> out/verify_partitioned.txt (t08, hmbatch)  ← 唯一真门禁
#
# 关键（踩过的坑，详见 SKILL.md §9）:
#   * t00/t07 写盘前必须 file delete 旧文件（P35，否则 Overwrite? 弹窗=不可 catch 致命错）
#   * t07/t08 首行读 $::env(WORKDIR)，**漏设会静默失败并留下上一版报告**（P49）
#     本脚本全程 export WORKDIR，并在跑 t08 前 rm 旧报告
set -euo pipefail

S="$(cd "$(dirname "$0")" && pwd)"
: "${WORKDIR:?must set WORKDIR to the project workspace}"
PY="${PY:-C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe}"
HMBATCH="${HMBATCH:-D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe}"
HM_IN="${HM_IN:-curves.hm}"
HM_OUT="${HM_OUT:-partitioned.hm}"
SEED="${SEED:-newcab_classify8.json}"
DELTA="${DELTA:-none}"
export WORKDIR HM_IN HM_OUT

cd "$WORKDIR"
mkdir -p out
echo "== WORKDIR=$WORKDIR  IGES=${IGES:-<skip>}  SEED=$SEED  DELTA=$DELTA"

# ---------------- S0 IGES -> curves.hm ----------------
if [ -n "${IGES:-}" ]; then
  if [ -f "$HM_IN" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "== S0 跳过导入: $HM_IN 已存在 (FORCE=1 强制重导)"
  else
    echo "== S0 导入 $IGES -> $HM_IN"
    IGES="$IGES" "$HMBATCH" -tcl "$S/t00_import_iges.tcl" >/dev/null
    cat out/t00_import_report.txt
  fi
else
  echo "== S0 跳过导入 (未设 IGES)"
fi
[ -f "$HM_IN" ] || { echo "FATAL: $HM_IN 不存在"; exit 1; }

# ---------------- S1 几何特征 ----------------
if [ -f out/geom_features.txt ] && [ "${FORCE:-0}" != "1" ]; then
  echo "== S1 跳过: out/geom_features.txt 已存在"
else
  echo "== S1 导出几何特征"; WORKDIR="$WORKDIR" HM_IN="$HM_IN" "$HMBATCH" -tcl "$S/t01_export_geom.tcl" >/dev/null
fi
[ -f out/geom_features.txt ] || { echo "FATAL: t01 未产出 geom_features.txt"; exit 1; }

# ---------------- S2 采样点 ----------------
if [ -f out/lines_pts.txt ] && [ "${FORCE:-0}" != "1" ]; then
  echo "== S2 跳过: out/lines_pts.txt 已存在"
else
  echo "== S2 导出采样点"; WORKDIR="$WORKDIR" "$HMBATCH" -tcl "$S/t02_export_pts.tcl" >/dev/null
fi

# ---------------- S3 种子分类（人工） ----------------
if [ ! -f "out/$SEED" ]; then
  echo "== S3 需要人工种子分类:"
  echo "    1) 先看 out/ 渲染底图 / 用 p03_bridge_scan.py 出搭接候选"
  echo "    2) 判据: references/01_partition_rules.md + references/02_tangent_continuity.md"
  echo "    3) 写 out/$SEED = {\"line_comp\": {\"1\":\"BELT\", ...}}"
  echo "    （NEW_CAB 可直接用规范 v8 种子 newcab_classify8.json: 119/78/59/572）"
  exit 1
fi
echo "== S3 种子分类 OK: out/$SEED"

# ---------------- S4 应用 delta -> classify_final.json ----------------
echo "== S4 应用修正 delta=$DELTA"
case "$DELTA" in
  none) cp -f "out/$SEED" out/classify_final.json ;;
  v9)   V9_SRC="$SEED" WORKDIR="$WORKDIR" "$PY" "$S/v9_apply_fix.py" ;;
  v10)  V10_SRC="$SEED" WORKDIR="$WORKDIR" "$PY" "$S/v10_cavity_open_port.py" ;;
  v12)  V12_SRC="$SEED" WORKDIR="$WORKDIR" "$PY" "$S/v12_add_l161.py" ;;
  v13)  V13_SRC="$SEED" WORKDIR="$WORKDIR" "$PY" "$S/v13_cavity_seal_chain.py" ;;
  v14)  V14_SRC="$SEED" WORKDIR="$WORKDIR" "$PY" "$S/v14_remove_tiny_circles.py" ;;
  *)    echo "FATAL: unknown DELTA=$DELTA"; exit 1 ;;
esac
[ -f out/classify_final.json ] || { echo "FATAL: 未产出 classify_final.json"; exit 1; }

# ---------------- S5 渲染 + 终检报告（人工看图） ----------------
echo "== S5 渲染 + 终检报告"
WORKDIR="$WORKDIR" "$PY" "$S/p05_render_partition.py" || echo "  (p05 跳过)"
# 不能 | head (pipefail 下 SIGPIPE 会整链失败); 报告全文落 out/final_report.txt, 这里只回显摘要
WORKDIR="$WORKDIR" "$PY" "$S/p07_report.py" > out/final_report.log 2>&1 || echo "  (p07 跳过)"
grep -E "^计数|^--- |小分量, 疑符号残留" out/final_report.log | head -14
if [ "${SKIP_CONFIRM:-0}" != "1" ]; then
  echo "    >>> 检查 out/v_partition*.png + out/final_report.txt，人眼确认后回车继续 <<<"
  echo "    >>> 重点: 小分量(疑符号残留) / 主环自由端是否为设计允许开口 / 重复线 <<<"
  read -r _
fi

# ---------------- S6 导出 id 列表 ----------------
echo "== S6 导出 Tcl id 列表"
WORKDIR="$WORKDIR" "$PY" "$S/p06_export_class_lists.py"

# ---------------- S7 搬线建 comp ----------------
echo "== S7 搬线建 4 comp (hmbatch)"
rm -f "$HM_OUT"                       # P35
WORKDIR="$WORKDIR" HM_IN="$HM_IN" HM_OUT="$HM_OUT" "$HMBATCH" -tcl "$S/t07_make_comps.tcl" >/dev/null
grep -q "ALL_OK=1" out/make_comps_report.txt || { echo "FATAL: t07 失败"; tail -20 out/make_comps_report.txt; exit 1; }

# ---------------- S8 独立回读校验（唯一真门禁） ----------------
echo "== S8 独立回读校验"
rm -f out/verify_partitioned.txt      # P49: 防旧报告假 PASS
WORKDIR="$WORKDIR" HM_OUT="$HM_OUT" "$HMBATCH" -tcl "$S/t08_verify_partitioned.tcl" >/dev/null
grep -q "VERIFY_FAIL=0" out/verify_partitioned.txt || { echo "FATAL: t08 失败"; cat out/verify_partitioned.txt; exit 1; }

echo "== DONE: $WORKDIR/$HM_OUT =="
grep -E "lines=|COUNT|TOTAL|VERIFY_FAIL" out/verify_partitioned.txt | head -12
