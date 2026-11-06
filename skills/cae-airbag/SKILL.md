---
name: cae-airbag
description: 在桌面应用中按用户确认的项目参数，编排 IGS 导入、四分区、网格、组合求解、HyperView 后处理和报告。
---

# 气帘仿真编排

本文件只负责应用流程。算法与门禁以 `docs` 中四份技能为准，禁止另造一套分区或网格算法。

## 先取得当前阶段

1. 调用 `cae_workflow` 的 `create` 或 `status`。工作流绑定当前对话。
2. 提示用户打开对话顶部的“仿真工作流”，填写当前阶段的参数。界面使用 dsh 原生侧栏与默认布局。
3. 当状态为 `parameters`、`blocked`、`review` 时停止执行，等待用户操作。只有用户表单提交后的 `ready` 状态可以 `begin`。
4. `begin` 返回 `state.executionId`、`state.skillPath`、`state.jobDirectory`、当前阶段定义及已提交参数。先读对应 skill，再读取生成的 `<stage>.parameters.json`；网格和求解分别有 `mesh.case.json`、`solve.case.json`。
5. 只执行当前阶段。完成后调用 `complete`，传 `execution_id` 和真实产物。后续阶段重新等用户填写参数；分区、网格、后处理还要用户确认结果。

用户确认只通过应用界面发生。不要代用户填表、改状态文件或连续跳过多个阶段。

## 参数来源

- IGS、工作目录、网格尺寸及类型、当前模型案例配置、车身和参考模型、材料、装配 DY/DZ、拉带数量、终止时间、CPU/内存等来自表单。
- 后处理时刻范围、帧数、帧率、云图类型来自表单。
- 报告标题、人员、模板、测点、坐标对齐依据、G.3 头部重心、测量/展开对照/起爆时刻来自表单。`g14_thickness.py` 的 `--t-main/--t-early/--tdet` 必须全部显式传入，不能使用脚本的案例默认时刻。
- 部件号、分层、锚点位置、参考卡参数应从当前模型和参考 deck 读取并校验。不能从 `cab2`、`case_config.example.json` 等样例直接复制。
- 如果技能还需要用户提供参数，或者当前输入不足以确定物理条件，调用 `request_input`，传当前 `execution_id`，在 `message` 中具体说明缺少的信息、单位及来源。界面会提示补充，等待用户提交后再执行。
- 允许从实际文件计算派生量；必须写入证据，不能用样例坐标、项目路径、个人电脑 Python 路径或经验数值替代未知输入。
- 所有输出写入本工作流目录，保留原输入。软件路径使用应用设置，Python 使用已配置工具环境；显式覆盖技能脚本中的历史默认路径。

## 六个阶段

| 阶段 | 权威技能 | 关键要求 |
| --- | --- | --- |
| import | `docs/气帘iges分区skill/SKILL.md` | 用 `t00_import_iges.tcl`，显式设置 IGES/WORKDIR/HMBATCH/PY；交付真实 curves.hm |
| partition | 同上 | v2 采样 → auto_partition2 → p06 → t07 → t08；BELT/CAVITY/SEAM/TETHER 四分区；独立回读 VERIFY_FAIL=0 |
| mesh | `docs/气帘自动网格划分_20261101(1)/气帘自动网格划分/SKILL.md` | 先读接新模型 runbook、pitfalls、generic pipeline；用本次 mesh.case.json；四道门禁全部通过 |
| solve | `docs/气帘计算求解skill_20261102(1)/气帘计算求解skill/SKILL.md` | 先读 references/09、10；组合 K，ID 审计，保持参考卡物理参数，parity/阻尼门禁后先探针再正式算 |
| postprocess | `docs/气帘评判及报告skill_20261103(1)/气帘评判及报告skill/SKILL.md` | 实际 bridge 状态 → MCP 启动 → 轮询在线；按用户时刻等参数生成四视角与动画 |
| report | 同上 | summary 只写过程摘要；assessment 使用真实测点与坐标对齐证据，缺失动态证据不得宣称法规 PASS |

不要调用 `hypermesh_partition_airbag`，它是早期三组件占位实现。也不要把旧的通用 mesh 工具当作四分区门禁链的替代品。
技能 shell 脚本含 POSIX 命令；Windows 上先确认 Bash 可用，或逐条用现有 PowerShell/MCP 运行相同规范脚本，不能把 `.sh` 直接当作 Windows 可执行程序。

### 求解

必须统一调用 `mcp__cae__lsdyna_solve`，它按设置选择本地软件、本地服务或远程服务。不要用其它工具绕过后端设置。`ncpu`、`memory` 使用本次提交值。

提交前提示用户：“求解通常需要数小时，具体耗时取决于模型规模、网格密度和计算资源。”界面已经要求用户确认，不必在对话中重复索要授权。
服务模式需确认模型及 INCLUDE 文件能被服务访问；结果可能为远程路径，后处理前必须让用户提供本机可读的映射或同步文件。
目前同步求解接口最长等待 48 小时。工具超时、断线、应用重启或用户停止后，先核实实际进程或服务端任务；不可自动重复提交。
不得编造百分比、剩余时间或把进程启动当作完成。检查正常终止、d3plot、健康门禁再交付。

### 后处理与报告

遵循 `references/hyperworks_autostart.md`。历史文档里的个人 workspace 是案例，当前输入输出应使用本机 bridge 实际 allowed_roots；需要配置时提示用户。
按实际接口传用户提供的时间范围、帧数、帧率、云图类型；若 CLI 不支持某选项，使用有该能力的 MCP 接口，或者 request_input 说明限制，不能静默忽略用户参数。
`hv_render.py check` 的 `unique md5` 必须等于截图数且包含四视角。脚本返回 0 但存在重复截图也不能通过应用门禁。
报告需列出真实参数、证据来源和缺失项。提供客户模板时保留主题，不用通用工具覆盖客户样式。无模板的 summary 可用通用报告工具，但必须传实际网格类型、尺寸、质量信息和 ms 单位。

## 交付与门禁协议

`complete` 的 `artifacts` 是 `{role, path, remote?}` 数组，完整路径指向当前执行产生的非空文件；不能用旧案例结果冒充。必需角色在 `status/begin` 的 `stage.outputs` 中。

- 分区的 `verification` 为本次独立回读的原始文本，包含 `VERIFY_FAIL=0`。
- 网格/求解/后处理的 `verification` 为本次门禁汇总 JSON：

```json
{
  "checks": [
    {"name": "strict_k", "passed": true, "evidence": "<本次命令输出或原始门禁 JSON 的完整路径>"}
  ]
}
```

每个 evidence 必须是真实工具刚生成的日志或原始报告，不要自行写一份 PASS 文本。应用检查文件、时效与结果，不接受只有自述的完成消息。

网格门禁使用应用生成的 `mesh.gate.json`，它指向本次 `out/curtain_airbag.k`，同步本次网格尺寸、PID、tag 和分层；不能再运行指向历史 K 的原始门禁配置。

| 阶段 | 必需 checks.name |
| --- | --- |
| mesh | strict_k、auto_gate、quality、partition_coverage |
| solve | parity、damper、probe、normal_termination、health |
| postprocess | four_views（evidence 指向 hv_render check 原始输出，unique md5: N / N，N≥4） |

任何必需门禁 FAIL、WARN 或缺证据都应暂停并说明问题。若某报告仅输出中文，保留原始输出并附带实际工具退出码与报告解释，请维护人员适配验证器，不能伪造英文 PASS。
真实文件、图片、动画展示在工作流侧栏，工具调用、思考与详细日志仍在对话中。

## 软件缺失与错误

- 导入/分区/网格缺 HyperMesh、后处理缺 HyperView、求解缺所选求解器或服务地址时暂停；界面引导至“设置 → 仿真软件”并定位路径字段，文件和参数会保留。
- `fail` 必须说明真实工具错误与日志。补充参数用 `request_input`；执行失败后重试仍要用户确认当前表单。
- 应用中断时阶段为 `interrupted`。求解重试要求用户先检查实际任务，避免重复计算。
