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
4. `begin` 返回 `state.executionId`、`state.skillPath`、`state.jobDirectory`、当前阶段定义及 `state.parameterFile`，网格和求解还返回 `state.caseFile`，网格另有 `state.gateFile`、`state.recoveryFile`。先读对应 skill，再按需读取这些文件中的当前参数；完整配置保存在文件中，工具不会重复返回其它阶段的参数或执行历史。
5. 只执行当前阶段。完成后调用 `complete`，传 `execution_id` 和真实产物。后续阶段重新等用户填写参数；分区、网格、后处理还要用户确认结果。

用户确认只通过应用界面发生。不要代用户填表、改状态文件或连续跳过多个阶段。

## 上下文预算

- 仅在进入当前阶段时读取其 skill，按引用按需读取 runbook 和脚本；大文件用 `read` 的 offset/limit 分页，不要一次加载整个 docs 目录。
- 不在对话中读取原始 IGS、完整 K 文件、节点/单元列表、完整求解日志或全部工作流状态。用本地脚本提取数量、范围、失败项与必要日志尾部，完整数据留在文件中。
- 超长工具输出会返回有限预览和完整结果路径。需要中间片段时分页读取该路径；不能因预览被裁剪而省略技能要求的门禁或验证。
- 求解轮询只返回状态变化、必要的错误和少量最新日志；不重复回传完整历史。dsh 在接近窗口预算时自动压缩历史，必须保留当前执行标识、参数文件、实际产物路径和待用户确认项。

## 参数来源

- IGS、工作目录、网格尺寸及类型、可选的已认可参考网格 K、车身和参考模型、材料、装配 DY/DZ、拉带数量、终止时间、CPU/内存等来自表单。
- 后处理时刻范围、帧数、帧率、云图类型来自表单。
- 报告标题、人员、模板、测点、坐标对齐依据、G.3 头部重心、测量/展开对照/起爆时刻来自表单。`g14_thickness.py` 的 `--t-main/--t-early/--tdet` 必须全部显式传入，不能使用脚本的案例默认时刻。
- 网格阶段不要求用户上传 `case.json`。根据当前 `partitioned.hm`、分区回读报告和 CAD 采样证据，在 `jobDirectory` 内生成本次专用 `mesh.case.json` 与 `mesh.gate.json`；需要目视时从前阶段的真实 `preview` artifact 打开分区预览。部件号、分层、厚度轴、装配/拉带输入、CAD tag 和门禁基线必须从当前模型、已验证文件或用户确认中取得，不能从 `cab1`、`cab2` 或其它案例直接复制。
- `partition_cover_check` 需要已认可的参考网格 manifest。若用户提供当前项目已认可的参考 K，按技能规定从它生成本次 manifest；否则不得用当前待验收网格冒充基线、不得跳过门禁，须通过 `request_input` 询问已认可基线或首次验收方案，并等待用户提供项目依据/确认。
- 如果技能还需要用户提供参数，或者当前输入不足以确定物理条件，调用 `request_input`，传当前 `execution_id`，在 `message` 中具体说明缺少的信息、单位及来源。界面会提示补充，等待用户提交后再执行。
- 允许从实际文件计算派生量；必须写入证据，不能用样例坐标、项目路径、个人电脑 Python 路径或经验数值替代未知输入。
- 所有输出写入本工作流目录，保留原输入。软件路径使用应用设置，Python 使用已配置工具环境；显式覆盖技能脚本中的历史默认路径。

## 六个阶段

| 阶段 | 权威技能 | 关键要求 |
| --- | --- | --- |
| import | `docs/气帘iges分区skill/SKILL.md` | 用 `t00_import_iges.tcl`，显式设置 IGES/WORKDIR/HMBATCH/PY；交付真实 curves.hm |
| partition | 同上 | v2 采样 → auto_partition2 → p06 → t07 → t08；BELT/CAVITY/SEAM/TETHER 四分区；独立回读 VERIFY_FAIL=0 且 partition_geometry.json PASS |
| mesh | `docs/气帘自动网格划分_20261101(1)/气帘自动网格划分/SKILL.md` | 先读接新模型 runbook、pitfalls、generic pipeline 与 cases/README；从当前分区模型生成本次 mesh.case.json，无需上传配置文件；四道门禁全部通过 |
| solve | `docs/气帘计算求解skill_20261102(1)/气帘计算求解skill/SKILL.md` | 先读 references/09、10；组合 K，ID 审计，保持参考卡物理参数，parity/阻尼门禁后先探针再正式算 |
| postprocess | `docs/气帘评判及报告skill_20261103(1)/气帘评判及报告skill/SKILL.md` | 实际 bridge 状态 → MCP 启动 → 轮询在线；按用户时刻等参数生成四视角与动画 |
| report | 同上 | summary 只写过程摘要；assessment 使用真实测点与坐标对齐证据，缺失动态证据不得宣称法规 PASS |

不要调用 `hypermesh_partition_airbag`，它是早期三组件占位实现。也不要把旧的通用 mesh 工具当作四分区门禁链的替代品。
技能 shell 脚本含 POSIX 命令；Windows 上先确认 Bash 可用，或逐条用现有 PowerShell/MCP 运行相同规范脚本，不能把 `.sh` 直接当作 Windows 可执行程序。

### 网格重试与产物恢复

先读取 `state.recoveryFile`。应用核对参数、已确认分区与上次输入的 SHA-256，并记录当前工作目录的实际产物。

- `mode=verify_existing`：保留 `.hm/.k/preview`；在全新 hmbatch 进程运行网格技能的 `scripts/gate/readback_mesh.tcl`，设置 `WORKDIR` 和 `MESH_HM`，输出 `out/mesh_readback.txt`。再执行 `python scripts/gate/verify_mesh_readback.py --hm <现有HM> --k <现有K> --readback <回读文本> --out <out/mesh_readback.json>`，逐节点坐标与壳单元连接对比 HM/K。
- 对现有 K 重跑严格 K、auto_gate、质量、分区覆盖四道门禁；`verification.checks` 增加 `mesh_readback`，指向本次生成的 `mesh_readback.json`。全部通过后直接 `complete`，旧产物可在哈希匹配时复用，门禁证据仍必须是本次生成。禁止 touch、复制文件刷新时间或改写 WARN 为 PASS。
- `mode=rebuild`、用户要求调整、输入/参数变化或实际检查失败时，按真实失败范围返工；不可仅为清除允许的 WARN 重划或降低门限。
- 新建网格前，旧分区也要用分区 t08 试建面预检；若只有线数回读 PASS，仍需补齐 `partition_geometry.json`。原始 CAD 的设计开口以诊断保留，不擅自归线或加大容差；面边界必须闭合，布带面积必须满足“外轮廓 − 气腔”，裁切前后面积守恒。

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

`complete` 的 `artifacts` 是 `{role, path, remote?}` 数组，完整路径指向当前执行产生或按恢复协议重新核验的非空文件；不能用旧案例结果冒充。必需角色在 `status/begin` 的 `stage.outputs` 中。

- 分区的 `verification` 为本次独立回读的原始文本，包含 `VERIFY_FAIL=0`；`geometry_verification` 指向 t08 生成的 `out/partition_geometry.json`，包含真实试建面闭环、裁切面积、源模型和开口线端点诊断。闭环或面积失败时先修正分区，不能直接进入网格。
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

必需门禁 FAIL、缺证据或未知 WARN 必须暂停。`auto_gate` 使用五项原始 JSON 结果（拓扑、分层、环面积/节点路程、环几何、拉带连接）：无 FAIL 时仅允许既定的短边 WARN，以及真缺口为零、有自有 fabric/跨 PID fabric 覆盖的局部特征 WARN；保留 `overall=WARN`、原始明细和证据路径，汇总 `passed=true` 表示满足此验收规则。应用在结果确认卡展示警告，用户仍需确认结果。其它检查 WARN 继续拦截，不能统一按退出码 0 放行，也不能通过降低门限或关闭检查取得 PASS。若报告格式不受支持，保留原始输出并附带实际退出码与解释，请维护人员适配，不能伪造英文 PASS。
真实文件、图片、动画展示在工作流侧栏，工具调用、思考与详细日志仍在对话中。

## 软件缺失与错误

- 导入/分区/网格缺 HyperMesh、后处理缺 HyperView、求解缺所选求解器或服务地址时暂停；界面引导至“设置 → 仿真软件”并定位路径字段，文件和参数会保留。
- `fail` 必须说明真实工具错误与日志。补充参数用 `request_input`；执行失败后重试仍要用户确认当前表单。
- 应用中断时阶段为 `interrupted`。求解重试要求用户先检查实际任务，避免重复计算。
