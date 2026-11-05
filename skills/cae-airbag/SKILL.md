# CAE 气帘（侧帘气囊）仿真工作流

## 触发条件
当用户提到"气帘仿真"、"气囊分析"、"airbag simulation"、"igs 导入"、"LS-DYNA 求解"等关键词时使用此 skill。

## 工作流概览
气帘 CAE 仿真分六个顺序步骤，每步依赖上一步的输出文件：

```
IGS文件 → [导入] → model.hm → [分区] → model_partitioned.hm
        → [网格] → model_meshed.hm + airbag.key
        → [求解] → d3plot → [导出GIF] → result.gif
        → [报告] → report.pptx
```

## Step 1 — 导入 IGS/IGES 几何
**工具**: `mcp__cae__hypermesh_import_igs`
- 请用户提供 IGS 文件的完整 Windows 路径（如 `D:\projects\airbag\cushion.igs`）
- 默认比例因子 1.0（毫米模型无需缩放）
- 输出 `model.hm` 保存到 `CAE_WORKDIR`
- **常见问题**: 若导入失败，检查路径中无中文字符，确认 HyperMesh 版本 ≥ 2020

## Step 2 — 气帘模型分区
**工具**: `mcp__cae__hypermesh_partition_airbag`
- 默认创建三个组件: `airbag_cushion`（气囊织物）、`airbag_inflator`（充气器侧板）、`airbag_vent`（泄气孔区域）
- 用户可自定义组件名称
- 此步将几何按功能区域分配到不同 Component，便于后续差异化网格和材料定义
- **注意**: 分区完成后建议用户在 HyperMesh GUI 中核实边界是否正确

## Step 3 — 网格划分
**工具**: `mcp__cae__hypermesh_generate_mesh`
- 推荐参数: `element_size=5.0` mm，`element_type=quad`
- 质量标准: `quality_warpage≤5°`，`quality_aspect≤5`
- 输出: `model_meshed.hm` + `airbag.key`（LS-DYNA 关键字文件）
- 若质量不达标，减小 `element_size` 或切换为 `mixed` 类型重试

## Step 4 — LS-DYNA 显式求解
**工具**: `mcp__cae__lsdyna_solve`
- 输入: `airbag.key`
- 推荐: `ncpu=4`，`memory=2000m`（根据机器配置调整）
- 气帘典型仿真时间 30ms，求解耗时约 30–120 分钟（视网格密度和 CPU 数量）
- 求解完成后检查 `d3plot` 文件是否生成
- **若出现 *** Error**: 将 messag 文件内容转交给用户分析

## Step 5 — HyperView 导出 GIF
**工具**: `mcp__cae__hyperview_export_gif`
- 输入: `d3plot` 文件路径
- 推荐: `result_type=displacement`，`fps=10`，`width=1280`，`height=720`
- 也可导出 `stress` 或 `pressure` 云图
- 输出: `result.gif`

## Step 6 — 生成 PowerPoint 报告
**工具**: `mcp__cae__generate_ppt_report`
- 汇总前五步的关键信息：网格统计、求解参数、GIF 动画
- 默认语言：中文，可通过 `title` 参数修改
- 输出: `report.pptx`

## 错误处理策略
| 错误类型 | 处理建议 |
|---------|---------|
| hmbatch.exe 不存在 | 检查 `CAE_HMBATCH` 环境变量或 `config.yaml` 中的路径 |
| IGS 导入失败 | 检查文件是否被占用，路径无中文，用 HyperMesh GUI 验证文件有效性 |
| LS-DYNA negative volume | 检查网格质量，减小时间步或增加 Hourglass 控制 |
| HyperView GIF 导出空白 | 确认 d3plot 文件完整，尝试减少帧范围 |
| pptx 生成失败 | 确认 GIF 文件路径正确，或跳过 gif_path 参数 |

## 默认文件路径（可通过环境变量覆盖）
```
CAE_WORKDIR  = D:\cae_projects\airbag
CAE_HMBATCH  = C:\Altair\2023\hwdesktop\hw\bin\win64\hmbatch.exe
CAE_LSDYNA   = C:\LSTC\ls971_s_R13.1_winx64_ifort131.exe
CAE_HYPERVIEW = C:\Altair\2023\hwdesktop\hw\bin\win64\hw.exe
```

---

## 扩展 MCP 工具（hyperworks-mcp & qilan-solve-mcp）

### HyperWorks MCP（`mcp__hyperworks__*`）
通过 `packages/hyperworks-mcp` Python 包提供约 70 个 HyperWorks 工具，覆盖：
- **hmbatch 脚本执行** — `mcp__hyperworks__run_hmbatch_script`
- **工作提交（OptiStruct/Radioss）** — `mcp__hyperworks__submit_optistruct_job`, `mcp__hyperworks__submit_radioss_job`
- **实时 HyperMesh Bridge** — `mcp__hyperworks__live_send_tcl`, `mcp__hyperworks__live_get_session_info`
- **HyperView 后处理** — `mcp__hyperworks__hyperview_open_result`, `mcp__hyperworks__hyperview_export_animation`
- **HyperStudy DOE** — `mcp__hyperworks__hyperstudy_create_study`
- **环境探测** — `mcp__hyperworks__probe_environment`

运行时需要 `HYPERWORKS_HOME` 环境变量指向 Altair 安装根目录。

### Qilan Solve MCP（`mcp__qilan_solve__*`）
通过 `packages/qilan-solve` Python 包提供 LS-DYNA 气帘仿真专用工具：

| 工具 | 说明 |
|------|------|
| `mcp__qilan_solve__check_environment` | 检查 Python/LS-DYNA/HyperView 环境 |
| `mcp__qilan_solve__check_hyperview` | 验证 HyperView 可执行路径 |
| `mcp__qilan_solve__validate_kfile` | 验证 LS-DYNA .key 文件语法 |
| `mcp__qilan_solve__health_gate` | 网格质量门控（前处理快速检查） |
| `mcp__qilan_solve__read_d3plot` | 读取 d3plot 结果（时间步 / 节点位移） |
| `mcp__qilan_solve__render_deployment` | 渲染气帘展开动画并生成 GIF |

### 建议工具调用链（集成版）
```
IGS 导入
  → mcp__hyperworks__run_hmbatch_script (import + partition)
  → mcp__hyperworks__run_hmbatch_script (mesh)
  → mcp__qilan_solve__validate_kfile    (.key 文件校验)
  → mcp__qilan_solve__health_gate       (网格质量门控)
  → mcp__cae__lsdyna_solve              (求解)
  → mcp__qilan_solve__read_d3plot       (读取结果)
  → mcp__qilan_solve__render_deployment (生成 GIF)
  → mcp__cae__generate_ppt_report       (生成报告)
```

