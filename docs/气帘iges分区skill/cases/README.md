# cases/ · 端到端验收快照（冻结证据）

> 每个目录 = 一次**从原始 IGES 全新导入**跑 `scripts/run_auto2.sh` 的产物快照，
> 用于「日后回来看当初到底交付了什么」，以及在没有 HyperMesh 的机器上核对结果。
> **不要修改**这里的文件；要复跑请用 `run_auto2.sh` 输出到新工作区。

## 验收表（2026-10-31 22:25，`grep VERIFY_FAIL` + `eval_vs_golden.py`）

| 目录 | 图纸 | 线数 | `VERIFY_FAIL` | 与人工金标准逐线 | 自动计数 BELT/CAVITY/SEAM/TETHER |
|---|---|---|---|---|---|
| `v2_cab1/` | 5P-BAG（X-Z）| 338 | **0** | **314/314 = 1.000** | 7 / 3 / 58 / 270 |
| `v2_cab2/` | NEW_CAB 8P（X-Y）| 828 | **0** | **692/696 = 0.994** | 38 / 89 / 51 / 650 |
| `v2_cab3/` | 6P（X-Y）| 911 | **0** | **797/802 = 0.994** | 69 / 109 / 44 / 689 |

差异性质：cab2 剩 4 条结构互换（`TETHER→BELT`×2、`CAVITY→BELT`×1、`TETHER→CAVITY`×1），
cab3 剩 5 条（`CAVITY→BELT`×2、`TETHER→CAVITY`×2、`CAVITY→SEAM`×1），都落在硬件符号与结构线的接触处。
其余全部是"金标准 lines0 → 被判了类"（v2 设计上不产 lines0 残线），视觉无害。

## 每个目录里有什么

| 文件 | 含义 |
|---|---|
| `partitioned.hm` | **交付件**：四分区结果（可回读校验） |
| `classify_final.json` | 逐线分类结果 `{line_id: CLASS}`（828 条全落类） |
| `class_lists.tcl` | 上一步导出的 id 列表（t07 的输入，可复现建 comp） |
| `render_v2.png` | 自动结果渲染（红=BELT 蓝=CAVITY 绿=SEAM 橙=TETHER）|
| `render_golden.png` | 同图人工金标准渲染，用于肉眼对照（灰 = 金标准 lines0）|
| `verify_partitioned.txt` | `t08_verify_partitioned.tcl` 独立回读报告（`VERIFY_FAIL=0`）|
| `make_comps_report.txt` | `t07_make_comps.tcl` 建 comp 报告 |
| `t00_import_report.txt` | 原始 IGES 导入报告 |

## 复现与比对

```bash
# 1) 重跑（输出到任意新工作区，不动本目录）
WORKDIR=<新工作区> IGES=E:/work/AI_CAB/分区训练/igs/cab2.iges bash scripts/run_auto2.sh

# 2) 与金标准逐线比对：不带参数时优先读本目录的 cases/v2_<name>/
python scripts/eval_vs_golden.py
python scripts/eval_vs_golden.py --pred-root <新工作区父目录>/     # 比对外部新结果
```

## 已记录的复现性证据

- 2026-10-31 22:29 用重训后的模型从 `igs/cab2.iges` 全新导入跑一遍（`onekey/work/v2b_cab2`），
  与 `cases/v2_cab2/classify_final.json` **逐线 0 差异**、`VERIFY_FAIL=0` → 同一模型同一图可复现。
- 2026-10-31 22:36 `scripts/rebuild_from_golden.py`：只用 `golden/<name>/lines_pts.txt` 离线重算
  32 维特征，三图与存档 `features2.json` **数值完全一致（max|Δ|=0）** → 特征链路不依赖 HyperMesh。
