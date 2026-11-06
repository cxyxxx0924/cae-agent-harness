#!/usr/bin/env bash
# run_case.sh — case.json 驱动的通用气帘网格流水线（blmesh 前置 washer 版）
# ============================================================================
# 与老驱动 run_pipeline.sh 的区别:
#   run_pipeline.sh  案例参数散在多个 Tcl/Python 里，换案例要改脚本
#   run_case.sh      全部参数进 case.json；Tcl 由 loops.json 生成，零硬编码线号
#
# 用法
#   bash run_case.sh --case cases/cab2/case.json --work /path/to/proj
#   SKIP_LINES=1 bash run_case.sh ...      # 复用已有 out/lines_pts.txt
#   GATE_ONLY=1  bash run_case.sh ...      # 只跑 ⑥ 门禁
#
# 目录约定
#   $WORK/input/<model>.hm     HyperMesh 库（stage0 导入后）
#   $WORK/out/                 全部中间产物：lines_pts.txt / loops.json / step1.tcl / *.txt
#   $WORK/$DECK                最终 K（默认 out/curtain_airbag.k，export DECK= 覆盖）
#
# 阶段
#   ① export_lines_pts.tcl   各 collector 线采样 → out/lines_pts.txt
#   ② chain_loops.py         端点聚类 + 平滑走链 → out/loops.json（自动成环）
#   ③ gen_step1_tcl.py       loops.json + case.json → out/step1_gen.tcl
#   ④ hmbatch step1_gen.tcl  缝线面 / 布带面 / 气腔 blmesh → out/<case>_step1_bl.txt
#   ⑤ TETHER_TCL (可选)      拉带/侧面拉带网格（结构件，需案例级轮廓输入）
#   ⑥ assemble_cab2.py       分层组装 + 拉带捏合 + 写 deck
#   ⑥b ANCHORED_TETHERS=1    拉带锚固边受布带约束（两遍法：⑥ 出旧拉带 → 反求锚固链
#                            → 三刀切重生成拉带 → 再组装）。需 TABS_POLYS=<tether_full.json>
#   ⑦ 门禁                   qa_kfile_strict → auto_gate → mesh_quality_gate
#
# ⑤ 的存在说明泛化边界: 拉带是"由 CAD 曲线围出的独立轮廓"，不同案例形状差异大，
#   目前仍需一张案例级轮廓 JSON。BAG 类产品若无拉带可整体跳过 ⑤。
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
S="$(cd "$HERE/.." && pwd)"          # scripts/
ROOT="$(cd "$S/.." && pwd)"          # 技能根目录（cases/ assets/ references/）
PY="${PY:-python}"
HMB="${HMB:-D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe}"
CASE_JSON=""
WORK="${WORKDIR:-}"
DECK="${DECK:-out/curtain_airbag.k}"
SKIP_LINES="${SKIP_LINES:-0}"
GATE_ONLY="${GATE_ONLY:-0}"
TETHER_TCL="${TETHER_TCL:-}"
TETHER_SCRIPT="${TETHER_SCRIPT:-}"
TABS_POLYS="${TABS_POLYS:-}"
ANCHORED_TETHERS="${ANCHORED_TETHERS:-0}"
GATE_CASE="${GATE_CASE:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --case) CASE_JSON="$2"; shift 2;;
    --work) WORK="$2"; shift 2;;
    --deck) DECK="$2"; shift 2;;
    -h|--help) sed -n '2,32p' "$0"; exit 0;;
    *) echo "未知参数 $1"; exit 2;;
  esac
done

if [ -z "$CASE_JSON" ] || [ ! -f "$CASE_JSON" ]; then
  echo "用法: bash run_case.sh --case <case.json> --work <工作目录>"; exit 2
fi
[ -z "$WORK" ] && WORK="$(cd "$(dirname "$CASE_JSON")/../.." && pwd)"

_ANCHORED_ENV="${ANCHORED_TETHERS:-}"
eval "$($PY "$HERE/case_env.py" --case "$CASE_JSON")"
# 命令行显式给的 ANCHORED_TETHERS / GATE_CASE / PARTITION_MANIFEST 优先于 case.json
[ -n "$_ANCHORED_ENV" ] && ANCHORED_TETHERS="$_ANCHORED_ENV"
[ -n "${GATE_CASE_OVERRIDE:-}" ] && GATE_CASE="$GATE_CASE_OVERRIDE"
[ -n "${PARTITION_MANIFEST_OVERRIDE:-}" ] && PARTITION_MANIFEST="$PARTITION_MANIFEST_OVERRIDE"
TAB_TOL="${TAB_TOL:-0.35}"; SNAP_INSIDE_TOL="${SNAP_INSIDE_TOL:-0}"
WEAK_ANCHOR_MIN="${WEAK_ANCHOR_MIN:-1}"; EDGE_BAND="${EDGE_BAND:-4.0}"
REQUIRE_PARTS="${REQUIRE_PARTS:-}"
STEP2="${STEP2:-}"; STEP2B="${STEP2B:-}"
export WORKDIR="$WORK"
cd "$WORK" || exit 2
mkdir -p out

banner() { echo; echo "=============== $* ==============="; }
step()   { echo; echo "--- $* ---"; }
die()    { echo "!! $*"; exit 1; }

echo "== CASE=$CASE  WORK=$WORK"
echo "== model=input/$MODEL  comps=[$COMPS]"
echo "== mesh: size=$MESHSIZE seam=$SEAMSIZE bl=${BL_LAYER}x${BL_THICK} etype=$BL_ETYPE"
echo "== pid: belt=$PID_BELT cav=$PID_CAV seam=$PID_SEAM tether=$PID_TETHER"

if [ "$GATE_ONLY" != "1" ]; then

# ---- ① 线采样 ----
if [ "$SKIP_LINES" = "1" ] && [ -f out/lines_pts.txt ]; then
  banner "① 跳过（复用 out/lines_pts.txt）"
else
  banner "① export_lines_pts.tcl"
  COMPS="$COMPS" HM_IN="$MODEL" "$HMB" -tcl "$S/stage1_survey/export_lines_pts.tcl" -nolock \
    > out/_e_lines.log 2>&1
  grep -q __HW_DONE__ out/_e_lines.log || die "① 失败，见 out/_e_lines.log"
  echo "lines_pts.txt: $(wc -l < out/lines_pts.txt) 条线"
fi

# ---- ② 自动成环 ----
banner "② chain_loops.py  (tol=$LOOP_TOL)"
"$PY" "$S/stage2_partition/chain_loops.py" out/lines_pts.txt \
      --out out/loops.json --tol "$LOOP_TOL" || die "② 失败"
[ -f out/loops.json ] || die "② 未产出 out/loops.json"

# ---- ③ 生成 step1.tcl ----
banner "③ gen_step1_tcl.py"
"$PY" "$HERE/gen_step1_tcl.py" --case "$CASE_JSON" --loops out/loops.json \
      --out out/step1_gen.tcl || die "③ 失败"

# ---- ④ 建网格 ----
banner "④ hmbatch step1_gen.tcl"
OUTNAME="${OUTNAME:-${CASE}_step1_bl.txt}" "$HMB" -tcl out/step1_gen.tcl -nolock > out/_e_step1.log 2>&1
grep -q __HW_DONE__ out/_e_step1.log || die "④ 失败，见 out/_e_step1.log"
[ -f "out/${CASE}_step1_bl_report.txt" ] && cat "out/${CASE}_step1_bl_report.txt"

# ---- ⑤ 拉带（可选）----
if [ -n "$TETHER_SCRIPT" ]; then
  banner "⑤a $TETHER_SCRIPT"
  "$PY" "$TETHER_SCRIPT" || die "⑤a 失败"
fi
if [ -n "$TETHER_TCL" ]; then
  banner "⑤b hmbatch $(basename "$TETHER_TCL")"
  "$HMB" -tcl "$TETHER_TCL" -nolock > out/_e_tether.log 2>&1
  grep -q __HW_DONE__ out/_e_tether.log || die "⑤b 失败，见 out/_e_tether.log"
else
  banner "⑤ 跳过拉带（未设 TETHER_TCL / TETHER_SCRIPT）"
fi

# ---- ⑥ 组装 ----
banner "⑥ assemble_cab2.py → $DECK"
DECK="$WORK/$DECK" STEP1="${STEP1:-out/${OUTNAME:-${CASE}_step1_bl.txt}}" \
  STEP2="$STEP2" STEP2B="$STEP2B" REQUIRE_PARTS="$REQUIRE_PARTS" \
  TAB_TOL="$TAB_TOL" SNAP_INSIDE_TOL="$SNAP_INSIDE_TOL" WEAK_ANCHOR_MIN="$WEAK_ANCHOR_MIN" \
  EDGE_BAND="$EDGE_BAND" Z_CAV="$Z_CAV" Z_TAB="$Z_TAB" \
  "$PY" "$S/stage4_assemble/assemble_cab2.py" || die "⑥ 失败"

# ---- ⑥b 拉带锚固边受布带约束（两遍法，可选）----
# 第一遍 ⑥ 已经产出带旧拉带的 K；用它反求锚固链 → 重生成锚固受约束的拉带 → 再组装一次。
# 需要: TABS_POLYS=tether_full.json  TETHER_TCL/OUT 由本段自动指向 out/tabs_anchored*
if [ "${ANCHORED_TETHERS:-0}" = "1" ]; then
  [ -n "$TABS_POLYS" ] || die "ANCHORED_TETHERS=1 需要 TABS_POLYS=<tether_full.json>"
  # TABS_POLYS 可写相对 WORKDIR / 技能根目录 / scripts
  if [ ! -f "$TABS_POLYS" ]; then
    if [ -f "$ROOT/$TABS_POLYS" ]; then TABS_POLYS="$ROOT/$TABS_POLYS"
    elif [ -f "$S/$TABS_POLYS" ]; then TABS_POLYS="$S/$TABS_POLYS"; fi
  fi
  [ -f "$TABS_POLYS" ] || die "TABS_POLYS 不存在: $TABS_POLYS"
  banner "⑥b-1 plan_anchors.py（从 $DECK 的布带反求锚固链）"
  "$PY" "$S/stage3_mesh/plan_anchors.py" --k "$DECK" \
        --belt "$PID_BELT" --cav "$PID_CAV" --tether "$PID_TETHER" \
        --out out/anchors.json --png out/anchors.png || die "⑥b-1 失败"

  banner "⑥b-2 gen_tabs_anchored.py（三刀切）"
  "$PY" "$S/stage3_mesh/gen_tabs_anchored.py" --polys "$TABS_POLYS" \
        --anchors out/anchors.json --model "$MODEL" \
        --out out/tabs_anchored.tcl --export out/tabs_anchored_export.txt \
        || die "⑥b-2 失败"

  banner "⑥b-3 hmbatch tabs_anchored.tcl"
  "$HMB" -tcl out/tabs_anchored.tcl -nolock > out/_e_tabs.log 2>&1
  grep -q __HW_DONE__ out/_e_tabs.log || die "⑥b-3 失败，见 out/_e_tabs.log"
  [ -f out/tabs_anchored_report.txt ] && cat out/tabs_anchored_report.txt

  banner "⑥b-4 重新组装（TAB_TOL=$TAB_TOL SNAP_INSIDE_TOL=$SNAP_INSIDE_TOL WEAK_ANCHOR_MIN=$WEAK_ANCHOR_MIN）"
  STEP2="${STEP2:-out/tabs_anchored_export.txt}" STEP2B="$STEP2B" REQUIRE_PARTS="$REQUIRE_PARTS" \
  TAB_TOL="$TAB_TOL" SNAP_INSIDE_TOL="$SNAP_INSIDE_TOL" WEAK_ANCHOR_MIN="$WEAK_ANCHOR_MIN" \
  EDGE_BAND="$EDGE_BAND" Z_CAV="$Z_CAV" Z_TAB="$Z_TAB" \
  DECK="$WORK/$DECK" STEP1="${STEP1:-out/${OUTNAME:-${CASE}_step1_bl.txt}}" \
    "$PY" "$S/stage4_assemble/assemble_cab2.py" || die "⑥b-4 失败"
fi

fi  # GATE_ONLY

# ---- ⑦ 门禁 ----
banner "⑦a qa_kfile_strict"
"$PY" "$S/gate/qa_kfile_strict.py" "$DECK" || echo "  (qa_kfile_strict 报 FAIL，见上)"

# GATE_CASE 可写相对 WORKDIR，也可写相对技能根目录（cases/xxx/gate_case.json）
if [ -n "$GATE_CASE" ] && [ ! -f "$GATE_CASE" ]; then
  if [ -f "$ROOT/$GATE_CASE" ]; then GATE_CASE="$ROOT/$GATE_CASE"
  elif [ -f "$S/$GATE_CASE" ]; then GATE_CASE="$S/$GATE_CASE"; fi
fi
if [ -n "$GATE_CASE" ] && [ -f "$GATE_CASE" ]; then
  banner "⑦b auto_gate"
  "$PY" "$S/gate/auto_gate/run_gate.py" --case "$GATE_CASE" || true
else
  step "⑦b 跳过 auto_gate（未设 GATE_CASE）"
fi

banner "⑦c mesh_quality_gate（碰撞网格形状口径）"
"$PY" "$S/gate/mesh_quality_gate.py" "$DECK" \
      --pids "$PID_BELT,$PID_CAV,$PID_SEAM,$PID_TETHER" \
      --out out/qgate.json --png out/qgate.png
QG=$?
[ $QG -eq 2 ] && die "⑦c 质量门禁 FAIL（不合格率 > 5%）"

# ⑦d 分区覆盖核对：按 PID 比对面积 / 连通组分 / 包围盒，防"整块丢"
#     --manifest 指向已认可模型的 manifest（首次用 --write 生成）
if [ -n "${PARTITION_MANIFEST:-}" ]; then
  banner "⑦d partition_cover_check（分区覆盖 / 防丢块）"
  "$PY" "$S/gate/partition_cover_check.py" --k "$DECK" \
        --pids "$PID_BELT,$PID_CAV,$PID_SEAM,$PID_TETHER" \
        --manifest "$PARTITION_MANIFEST" || die "⑦d 分区覆盖 FAIL —— 有整块丢失，不要交付"
else
  step "⑦d 跳过分区覆盖（未设 PARTITION_MANIFEST；首次可 --write 建基线）"
fi

banner "DONE — $DECK"
