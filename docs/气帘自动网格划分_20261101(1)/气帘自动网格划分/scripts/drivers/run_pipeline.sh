#!/usr/bin/env bash
# run_pipeline.sh — 气帘自动网格划分 · 全链路一键复现
#   曲线(.hm/.iges) → 调查/清理 → 分区 → 裁切拓扑三面网格 → 拉带网格+捏合 → 充气口封口 → 门禁 → K
#
# 用法（换项目只改环境变量，脚本内零项目硬编码）:
#   WORKDIR=/path/to/proj bash run_pipeline.sh          # 全链（WORKDIR 需含 input/*.hm 或 *.iges）
#   SKIP_IMPORT=1 WORKDIR=/path/to/proj bash run_pipeline.sh   # 已有 input/*.hm，跳过导入
#   GATE_ONLY=1 WORKDIR=/path/to/proj bash run_pipeline.sh     # 只跑门禁+auto_gate（复用已有网格）
#   PY=... HMB=... bash run_pipeline.sh                  # 指定 Python / hmbatch
#
# 目录约定: WORKDIR/input/ 放 CAD(.hm 或 .iges)；WORKDIR/out/ 出全部中间产物与最终 K
# 最终交付: $WORKDIR/$DECK（默认 out/airbag_step1_2026.k，可用 DECK 环境变量覆盖）
set -euo pipefail

# ---- 自定位（本脚本在 <技能目录>/scripts/drivers/ 下）----
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/../.." && pwd)"

WORKDIR="${WORKDIR:-.}"
PY="${PY:-python}"
HMB="${HMB:-D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe}"
SKIP_IMPORT="${SKIP_IMPORT:-0}"
GATE_ONLY="${GATE_ONLY:-0}"
DECK="${DECK:-out/airbag_step1_2026.k}"

export WORKDIR
cd "$WORKDIR"
mkdir -p out
banner() { echo; echo "=============== $* ==============="; }

S="$SKILL_DIR/scripts"
echo "== SKILL_DIR=$SKILL_DIR"
echo "== WORKDIR=$WORKDIR"

# ---- ① 导入（已有 .hm 可跳过）----
if [ "$GATE_ONLY" != "1" ] && [ "$SKIP_IMPORT" != "1" ] && ! ls input/*.hm >/dev/null 2>&1; then
    banner "① stage0 import_igs_2026.tcl  CAD → .hm"
    "$HMB" -tcl "$S/stage0_import/import_igs_2026.tcl" -noconcurrent
    grep -E "geomimport|writefile|comps=|lines=" out/import_igs_report.txt || true
else
    banner "① 跳过导入 (GATE_ONLY / SKIP_IMPORT / input/*.hm 已存在)"
fi

if [ "$GATE_ONLY" = "1" ]; then
    banner "GATE_ONLY=1 → 直跳 ⑦ 门禁"
else

# ---- ② 几何调查 + 线点云导出 ----
banner "② stage1 survey_comps + export_lines_pts + export_tabs"
"$HMB" -tcl "$S/stage1_survey/survey_comps.tcl" -noconcurrent
"$HMB" -tcl "$S/stage1_survey/export_lines_pts.tcl" -noconcurrent
"$HMB" -tcl "$S/stage1_survey/export_tabs.tcl" -noconcurrent
grep -E "comp id|spline" out/survey_comps.txt || true

# ---- ③ 分区识别（拉带 9 区域 / 四分区归类）----
banner "③ stage3 tabs_extract.py  → tabs_polys.json"
"$PY" "$S/stage3_mesh/tabs_extract.py"

# ---- ④ 裁切拓扑三面网格（缝面/气腔/布带，界面天然共节点）----
banner "④ stage3 build_step1_2026.tcl + stage4 assemble_step1_2026.py"
"$HMB" -tcl "$S/stage3_mesh/build_step1_2026.tcl" -noconcurrent
"$PY" "$S/stage4_assemble/assemble_step1_2026.py"

# ---- ⑤ 拉带网格 + 与单层布带节点捏合 ----
banner "⑤ gen_tabs_tcl.py + build_tabs_2026.tcl + assemble_tabs.py"
"$PY" "$S/stage3_mesh/gen_tabs_tcl.py"
"$HMB" -tcl "$S/stage3_mesh/build_tabs_2026.tcl" -noconcurrent
cp out/airbag_step1_2026_pre_tabs.k "$DECK"          # 从干净基底重来（幂等）
"$PY" "$S/stage4_assemble/assemble_tabs.py"

# ---- ⑥ 充气口上下唇捏合到 Y0 ----
banner "⑥ assemble_port.py"
"$PY" "$S/stage4_assemble/assemble_port.py"

fi  # GATE_ONLY

# ---- ⑦ 门禁（任一失败即整体失败）----
banner "⑦ 门禁: qa_kfile_strict + diag_long_edges + diag_cavity_port + diag_strap_ends"
"$PY" "$S/gate/qa_kfile_strict.py" "$DECK"
"$PY" "$S/gate/diag_long_edges.py"
"$PY" "$S/gate/diag_cavity_port.py"
"$PY" "$S/gate/diag_strap_ends.py"

# ---- ⑦b 几何门禁: 逐环几何匹配 + 拉带连接检查（需 ring_spec.json + lines_pts.txt）----
RING_SPEC="${RING_SPEC:-out/ring_spec.json}"
LINES_PTS="${LINES_PTS:-out/lines_pts.txt}"
if [ -f "$RING_SPEC" ] && [ -f "$LINES_PTS" ]; then
    banner "⑦b 几何门禁: geom_match_check + tether_conn_check"
    "$PY" "$S/gate/geom_match_check.py" --lines "$LINES_PTS" --mesh "$DECK" \
      --rings "$RING_SPEC" --map xy --atol 0.15 --bnd 8 --sel-tol 8 --render out/v_geom_match.png
    "$PY" "$S/gate/tether_conn_check.py" --mesh "$DECK" --map xy \
      --rings "$RING_SPEC" --render out/v_tether_conn.png
else
    banner "⑦b 跳过几何门禁 (缺 $RING_SPEC 或 $LINES_PTS; 先跑 gen_ring_spec.py 生成)"
fi

# ---- ⑦c auto_gate 统一自动校验套件（零依赖，自出图，规则可迭代）----
# 案例配置模板见 $SKILL_DIR/cases/；GATE_CASE 指向新项目复制出来的配置即可
GATE_CASE="${GATE_CASE:-}"
if [ -n "$GATE_CASE" ] && [ -f "$GATE_CASE" ]; then
    banner "⑦c auto_gate 统一校验套件 (case=$(basename "$GATE_CASE"))"
    "$PY" "$S/gate/auto_gate/run_gate.py" --case "$GATE_CASE" || true
else
    banner "⑦c auto_gate 跳过 (未设 GATE_CASE; 模板: $SKILL_DIR/cases/*/gate_case.json)"
fi

banner "DONE — 交付物 $WORKDIR/$DECK"
