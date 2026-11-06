# golden/ · 气帘四分区金标准库（监督训练集）

> 本目录是技能**自带的全部监督样本**：专家人工分区的四分区结果 + 同源特征 + 原始图纸 + 出处。
> `scripts/train_v2.py`（当前）与 `scripts/train_joint.py`（留档）只读本目录即可重训先验——
> **技能文件夹整体复制即带走全部能力**，不依赖任何项目工作区路径。

## 布局

每个金标准目录**统一 7 件**（缺一不可，少一件就回放不了解构过程）：

| 文件 | 作用 |
|---|---|
| `source.iges` | 原始图纸（同源核对的依据）|
| `<name>.hm` | 用户手工分区结果（几何 + 组件划分）|
| `comp_lines.json` | 组件 → 线 id 列表 = **解构的原始证据**（标签怎么来的）|
| `comp_agg.json` | 各组件几何聚合表（线数/包围盒/中位长度/深度…）= 定映射时的判据 |
| `golden_panels.png` | 逐组件高亮面板图 = **视觉定案**依据（聚合表用来排除，渲染图用来定案）|
| `lines_pts.txt` | 每条线的采样点 → **可离线重算特征，不依赖 HyperMesh** |
| `golden_line_comp.json` + `features2.json` + `source.txt` | 金标签 / 32 维特征 / 出处与映射说明 |

```
golden/
  README.md              本文件
  cab1/                  ★金标准① 5P-BAG 侧视（用户手工分组，314 分类；另留 features.json v1 版）
  cab2/                  ★金标准② NEW_CAB 8P（用户手工分组 L1~L4 + lines0，696 分类；
                          另留 zoom_L5_18fragments.png = 那次纠错的现场图）
  cab3/                  ★金标准③ 6P（用户手工精分，802 分类）
  newcab/                【留档，不进 v2 训练】NEW_CAB 早期 v14 标注
                         —— 与 cab2 是同一张图（md5 相同），已被 cab2 的人工版取代
```

> 交付态的证据（`partitioned.hm` / 渲染 / 校验报告）不放在这里，在 `cases/`。

## 训练集总览（v2：cab1 + cab2 + cab3）

| 金标准 | 图纸 | 线数 | 平面 | BELT | CAVITY | SEAM | TETHER | lines0 |
|---|---|---|---|---|---|---|---|---|
| cab1 | 5P-BAG（侧视）| 338 | X-Z | 7 | 2 | 56 | 249 | 24 |
| cab2 | NEW_CAB 8P | 828 | X-Y | 35 | 87 | 43 | 531 | 132 |
| cab3 | 6P | 911 | X-Y | 67 | 109 | 40 | 586 | 109 |

> `cab2` 的 TETHER = `L4`(531)；原 `L5`(18 条碎线) 经用户更正归入 `lines0`（2026-10-31 修订，(8)→(9)）。
> `lines0` = 人工"选择忽略"的散碎线（各 `*_Wireframe` 组件），**不参与强约束**。

## 重训（技能内自包含）

```bash
python scripts/train_v2.py          # 只读 golden/，先打印 LODO 报告，再导出 tree_model_v2.json
```

`train_v2.py` 会先做**留一图交叉验证**（每次留一张图，用其余图训练，测留出图）。
这是唯一的诚实泛化口径；同图拟合的 100% 不算数。

当前基线（2026-10-31）：

| 留出图 | 条数准确率 | 结构长度加权 |
|---|---|---|
| cab1 | 0.971 | 0.919 |
| cab2 | 0.964 | 0.944 |
| cab3 | 0.949 | 0.964 |
| 平均 | **0.961** | **0.943** |

## 新增金标准（五步法）

1. 用户在新图上手工分组，得到带 comp 的 `.hm`。
2. 建工作区：`mkdir -p <wd>/out && cp <name>.hm <wd>/curves.hm`
   ```bash
   WORKDIR=<wd> hmbatch -tcl scripts/t02_export_pts.tcl    # 采样点
   WORKDIR=<wd> hmbatch -tcl scripts/t09_dump_comps.tcl    # comp -> 线 id
   python scripts/featurize2.py <wd>                       # 特征 v2
   python scripts/ga_analyze_comps.py <wd>                 # 聚合表 + out/golden_panels.png
   ```
3. **几何 + 视觉综合研判**定 `component → BELT/CAVITY/SEAM/TETHER` 映射。
   聚合表用来排除，**渲染图用来定案**（`midr` 对长折线不可靠；cab1 的 249 条 `component4` 是硬件簇不是外包络）。
4. 生成金标签并落盘，**7 件一起进 `golden/<name>/`**：
   ```bash
   python scripts/ga_build_golden.py <wd> --map "component1=BELT,component2=CAVITY,component3=SEAM,component4=TETHER,_lines0_Wireframe=lines0"
   cp <wd>/out/{features2.json,golden_line_comp.json,comp_lines.json,comp_agg.json,golden_panels.png,lines_pts.txt} golden/<name>/
   cp <name>.hm golden/<name>/ ; cp <name>.iges golden/<name>/source.iges   # 再写 source.txt（出处+映射+依据）
   ```
5. 在 `scripts/train_v2.py` 的 `DRAWS` 登记一行 → 重跑 → **确认原有各图 LODO 指标不明显下降** →
   最后跑 `python scripts/rebuild_from_golden.py <name>` 确认新图可离线复算。

## 自包含校验（不装 HyperMesh 也能验）

```bash
python scripts/rebuild_from_golden.py        # 只用 lines_pts.txt 离线重算 32 维特征
                                            # → 三图与存档 features2.json 数值完全一致（max|Δ|=0）
python scripts/eval_vs_golden.py             # 读 cases/ 里冻结的三图交付结果，逐线对金标准
```
两者都只读技能目录内的文件：证明「拷走这个文件夹 = 带走图纸、标注、特征、模型、判据与交付证据」。

## 铁律

- **同源核对**：新增前先 `md5sum` 原始 IGES 与已有 golden 的 `source.iges`。
  同一张图不能出现两次，否则交叉验证泄漏、指标虚高。
- **不与人工标注对着干**：若某类符号在两张图里被标成不同类，那是标注口径问题，
  先对齐口径再合库；模型无法同时满足矛盾标签。
