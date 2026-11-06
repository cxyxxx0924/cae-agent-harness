#!/usr/bin/env bash
# run_cab3.sh — 气帘 cab3 类项目 **端到端一键链**（曲线 → 三环共形网格 → Y 分层 K → 全门禁）
#
# 用法（换项目只改环境变量，脚本内零硬编码）:
#   export WORKDIR="./cab3"      # 工作区（含 lines_pts_all.txt / cab3.hm / loops_v3.json / tether_mesh.txt）
#   export REFDIR="./ref"     # 参考模型目录（需含 MAT.K + 03_Control_card.k；无则仅出网格 K）
#   export MESH_START="5.0"                                # 起始网格尺寸 (mm)，默认 5.0
#   export MESH_MIN="2.0"                                  # 自动调优下限，默认 2.0
#   export CMAX_LIMIT="0.5"                                # 边界绝对偏差门限 (mm)
#   SKIP_HM=1 bash run_cab3.sh                             # 跳过 hmbatch（复用已有网格，只跑门禁/组装/渲染）
#   bash run_cab3.sh
#
# 阶段（每阶段落盘产物，可断点续跑：已有产物且未设 FORCE 的阶段自动跳过）:
#   S1  环链分析            -> loops_all.json                     (loop_analyze.py)
#   S2  环序构建            -> loops_v3.json                      (build_loops3.py，项目一次性，见 references/11)
#   S3  网格 Tcl 生成       -> cab3_step1_v3.tcl                  (gen_step1_v3.py $MESH)
#   S4  hmbatch 网格        -> cab3_step1_v3_mesh.txt             (*interactiveremeshsurf, 保共形)
#   S5  形状门禁 v3         -> shape_gate_v3_report.json          (shape_gate_v3.py)
#       └─ 若 FAIL: MESH 减半重跑 S3-S5，直到 PASS 或触底 MESH_MIN   ← **全自动，无人工干预**
#   S6  Y 分层组装          -> cab3_full_v3.k                     (assemble_v3.py: 双层+washer+充气口封口+拉带吸附)
#   S7  结构门禁            -> final_gate + tether_conn_check
#   S8  交付渲染            -> v_final_shape/layers/port.png      (render_final.py)
#
# 关键设计（踩过的坑，详见 references/11_cab3_auto_pipeline.md）:
#   * 形状门禁 C 判据是**弦误差自适应**的: 允许偏差 = DP_EPS(0.2) + L^2/(8R)，
#     R 由"网格边两端点 + 边上最远原始曲线点"三点外接圆估计。5mm 直边跨 R=5.8mm 圆弧
#     固有矢高 0.55mm，用固定 0.5mm 门限会误判 -> 必须自适应。
#   * 洞贴合检查必须用**原始线采样点**，不能用闭合环：洞环两端点落在气腔主边界上(1.4mm 缺口)，
#     桥接弦横切急弯会产生 0.66mm 伪差（实测伪差 vs 真实 0.194mm）。
#   * 拉带链可能有"去而又回"的零面积针状突出（链式追逐伪迹），门禁必须先剔除，
#     否则 HM automesh 正确忽略它、门禁却报 0.542mm 假 FAIL。
#   * 网格尺寸由门禁驱动自动调优：cab3 实测 5.0mm -> cavity C=0.638 FAIL；3.0mm -> 0.289 PASS。
set -euo pipefail

S="$(cd "$(dirname "$0")" && pwd)"
export WORKDIR="${WORKDIR:-./cab3}"
PY="${PY:-C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe}"
HMBATCH="${HMBATCH:-D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe}"
HM_IN="${HM_IN:-cab3.hm}"
MESH_START="${MESH_START:-5.0}"
MESH_MIN="${MESH_MIN:-2.0}"
CMAX_LIMIT="${CMAX_LIMIT:-0.5}"
export REFDIR="${REFDIR:-./ref}"   # 参考模型目录(需含 MAT.K + 03_Control_card.k)

cd "$WORKDIR"
echo "== WORKDIR=$WORKDIR"
echo "== REFDIR=$REFDIR"
echo "== MESH: start=$MESH_START min=$MESH_MIN  CMAX_LIMIT=$CMAX_LIMIT"

# ---------- S0 环境检查 ----------
for f in lines_pts_all.txt "$HM_IN" loops_v3.json tether_mesh.txt; do
  [ -f "$f" ] || { echo "!! 缺少输入: $f  (S1/S2 产物或项目数据)"; exit 2; }
done
[ -f loops_all.json ] || "$PY" "$S/loop_analyze.py"
echo "== S1 loops_all.json OK"

# ---------- S2 环序（项目一次性；已有 loops_v3.json 则跳过） ----------
if [ ! -f loops_v3.json ] || [ "${FORCE:-0}" = "1" ]; then
  echo "!! loops_v3.json 不存在 -> 需先跑 build_loops3.py 并按 references/11 确认环序"
  "$PY" "$S/build_loops3.py"
fi
echo "== S2 loops_v3.json OK"

# ---------- S3-S5 网格 + 形状门禁 + 自动调优 ----------
MESH="$MESH_START"
GATE_OK=0
while true; do
  echo "== S3 生成网格 Tcl (MESH=$MESH)"
  "$PY" "$S/gen_step1_v3.py" "$MESH"
  if [ "${SKIP_HM:-0}" != "1" ]; then
    RUN="runs/hm_$(echo "$MESH" | tr . _)_$(date +%H%M%S)"
    mkdir -p "$RUN"
    ( cd "$RUN" && HYPERWORKS_HOME="D:/Program Files/Altair/2026" \
        "$HMBATCH" -tcl "$WORKDIR/cab3_step1_v3.tcl" > run.log 2>&1 )
    grep -q "__HW_DONE__" "$RUN/run.log" || { echo "!! hmbatch 未完成, 见 $RUN/run.log"; tail -5 "$RUN/run.log"; exit 3; }
  fi
  [ -f cab3_step1_v3_mesh.txt ] || { echo "!! 网格文件未生成"; exit 3; }
  echo "== S5 形状门禁 v3 (MESH=$MESH)"
  if "$PY" "$S/shape_gate_v3.py" cab3_step1_v3_mesh.txt "$CMAX_LIMIT"; then
    GATE_OK=1
    echo "== 形状门禁 PASS @ MESH=$MESH"
    break
  fi
  NEXT=$("$PY" -c "print(max($MESH_MIN, $MESH/2.0))")
  if [ "$NEXT" = "$MESH" ]; then
    echo "!! 已到 MESH_MIN=$MESH_MIN 仍 FAIL —— 停止，需人工看 shape_gate_v3_report.json"
    exit 4
  fi
  echo "== 形状门禁 FAIL @ MESH=$MESH -> 自动细化到 $NEXT"
  MESH="$NEXT"
done

# ---------- S6 组装 ----------
echo "== S6 Y 分层组装"
"$PY" "$S/assemble_v3.py"

# ---------- S7 结构门禁 ----------
echo "== S7 结构门禁"
"$PY" "$S/final_gate.py" cab3_full_v3.k
"$PY" "$S/tether_conn_check.py" cab3_full_v3.k

# ---------- S8 渲染 ----------
echo "== S8 交付渲染"
"$PY" "$S/render_final.py"

echo ""
echo "================ 交付完成 ================"
echo "  K 文件      : $WORKDIR/cab3_full_v3.k"
echo "  形状门禁    : shape_gate_v3_report.json (ALL PASS @ MESH=$MESH)"
echo "  渲染        : v_final_shape.png / v_final_layers.png / v_final_port.png"
echo "==========================================="
