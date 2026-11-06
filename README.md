# CAE Agent Harness — 气帘仿真 AI Agent

基于 **dsh (deepseek-harness)** 的 CAE 气帘仿真 Agent，支持全流程自动化：
IGS 导入 → 模型分区 → 网格划分 → LS-DYNA 求解 → HyperView 导出 GIF → PPT 报告生成。

## Python MCP 服务（hyperworks-mcp & qilan-solve-mcp）

项目集成了两个 Python FastMCP 服务，需要 [uv](https://docs.astral.sh/uv/) >= 0.4：

```bash
# Windows 安装 uv（PowerShell）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

| 包目录 | MCP Server 名 | 工具前缀 | 用途 |
|--------|--------------|---------|------|
| `packages/hyperworks-mcp/` | `hyperworks` | `mcp__hyperworks__*` | HyperMesh/HyperView/HyperStudy 全套自动化（~70 个工具）|
| `packages/qilan-solve/` | `qilan_solve` | `mcp__qilan_solve__*` | LS-DYNA 气帘求解专用（校验、求解、GIF 渲染）|

桌面应用会在 dsh 启动后异步准备两个服务的虚拟环境；MCP 进程直接运行虚拟环境中已安装的入口程序，因此 Python 和依赖下载、uv 环境锁都不会阻塞聊天界面。环境准备好后，dsh 会自动重连并注册工具。首次准备需要联网，打包版 Windows 默认使用清华 PyPI 镜像；可通过 `UV_INDEX_URL` 或 `CAE_UV_INDEX_URL` 覆盖。

直接运行 dsh（不经过 Electron）时，请先准备依赖：

```bash
uv sync --project packages/hyperworks-mcp
uv sync --project packages/qilan-solve
```

### 额外环境变量

```bash
# Altair HyperWorks 安装根目录（hyperworks-mcp 必需）
set HYPERWORKS_HOME=C:\Altair\2023
```

`LSDYNA_BIN` 由 cordis 自动从 `CAE_LSDYNA` 转发，无需单独设置。

## 架构

```
CAE Agent (Electron Window)
  └── dsh runtime  (AI Agent Loop + Web UI at :3080)
        └── MCP Client → @cae/mcp-server  (stdio)
              ├── mcp__cae__hypermesh_import_igs
              ├── mcp__cae__hypermesh_partition_airbag
              ├── mcp__cae__hypermesh_generate_mesh
              ├── mcp__cae__lsdyna_solve
              ├── mcp__cae__hyperview_export_gif
              └── mcp__cae__generate_ppt_report
```

## 大模型支持

通过环境变量切换，无需改代码：

| 模型 | `LLM_BASE_URL` | `DEEPSEEK_API_KEY` |
|------|---------------|-------------------|
| DeepSeek (默认) | `https://api.deepseek.com/v1` | DeepSeek API Key |
| QWen (通义千问) | `https://dashscope.aliyuncs.com/compatible-mode/v1` | DashScope API Key |
| Ollama (本地) | `http://localhost:11434/v1` | `ollama` |

## 快速开始

### 环境要求
- Node.js >= 24.9.0
- pnpm 10.x
- Windows 10/11 x64（运行时目标）
- Altair HyperWorks 2022/2023（含 hmbatch.exe、hw.exe）
- LS-DYNA R13.x（ls971.exe）

### 安装

```bash
# 克隆 / 进入项目
cd ~/Documents/cxy/cae-agent-harness

# 安装所有依赖
pnpm install

# 构建 MCP Server
pnpm build:mcp
```

### 配置路径

复制 `config/config.yaml` 为 `config/config.local.yaml` 并修改：

```yaml
windows:
  hmbatch:   "C:\\Altair\\2023\\hwdesktop\\hw\\bin\\win64\\hmbatch.exe"
  hyperview: "C:\\Altair\\2023\\hwdesktop\\hw\\bin\\win64\\hw.exe"
  lsdyna:    "C:\\LSTC\\ls971_s_R13.1_winx64_ifort131.exe"
workdir: "D:\\cae_projects\\airbag"
```

或使用环境变量：

```bash
set DEEPSEEK_API_KEY=sk-...
set CAE_WORKDIR=D:\cae_projects\airbag
set CAE_HMBATCH=C:\Altair\2023\hwdesktop\hw\bin\win64\hmbatch.exe
set CAE_LSDYNA=C:\LSTC\ls971_s_R13.1_winx64_ifort131.exe
set CAE_HYPERVIEW=C:\Altair\2023\hwdesktop\hw\bin\win64\hw.exe
```

### 仅启动 Agent（无 GUI，用于调试）

```bash
# 先启动 MCP Server（确认可用）
node packages/cae-mcp-server/dist/index.js

# 启动 dsh Agent，然后打开终端打印的完整 URL（含 ?token=...）
pnpm exec dsh web --patch config/cae-airbag.cordis.yml --no-open
```

### 启动桌面应用（开发模式）

```bash
pnpm dev
```

启动后直接进入主界面。未配置模型或已保存配置无效时，点击“选择模型”或“新建会话”（含快捷键）会打开应用内的“设置 → 模型”弹窗；关闭弹窗可继续浏览主界面。填写 API Key 和接口地址，获取列表并勾选模型后保存即可使用。应用菜单的“设置…”也打开同一弹窗。
API Key 填写密钥，API Base URL 填写以 `http://` 或 `https://` 开头的接口网址；填写颠倒时会提示错误，不会保存或重启。
“设置 → 模型”保留已保存的 API Key、接口地址、默认模型和可选模型列表；旧版单模型配置会自动保留，可通过“重新获取模型”刷新和清理。
“设置 → 缓存”提供“清除缓存并刷新”，用于修复设置入口缺失、界面显示异常等问题；如果设置页无法正常显示，也可使用应用菜单“视图 → 清除缓存并刷新…”。确认后清理界面资源缓存、脚本缓存及当前界面的离线缓存并重新加载，保留已保存的模型配置、仿真软件设置、对话记录和文件；未保存的输入会丢失。桌面应用启动时也会自动清理界面缓存，避免升级后继续使用旧资源。
“获取模型列表”会请求当前接口的 `/models`，以标签显示返回的型号。点击标签选择要使用的模型，支持全选、全不选、仅看已选和搜索；默认模型从已选项中下拉选择，无需输入模型 ID。保存后，只有已选模型会出现在输入框下方的模型菜单中，重新打开设置时会保留完整目录和勾选状态。
“重新获取模型”会替换旧目录，清除接口不再提供的型号，并保留仍在列表中的勾选。“测试已选”会发送简短对话请求（可能产生少量用量，每次最多 50 个），移除明确不存在、不支持对话或无模型访问权限的型号；限流、网络失败和其他无法确认的错误会提示并保留。未选择模型时不能保存；取消默认模型或移除不可用模型后，会自动使用剩余已选项中的第一个作为默认。切换接口地址或密钥后需重新获取列表。
列表内模型共用当前 API Key 和 Base URL；切换提供方时请同步修改接口地址、密钥和模型列表。主界面的“设置 → 模型”不会回传密钥明文，API Key 留空会保留已保存的密钥。
`deepseek-flash` 和 `deepseek-v4-pro` 可在输入框下方的模型菜单中选择推理等级：Off（关闭）、Low（低）、High（高）、Max（最高）。支持 High 的模型均默认使用 High，与其他模型混合配置也会保留该默认值；手动选择其他等级后，后续请求使用所选等级。不支持推理等级的模型沿用普通请求。
模型通过 OpenAI Chat Completions 兼容接口调用，支持 DeepSeek、通义千问、Ollama 和兼容网关。
桌面应用会自动打开带认证 token 的 dsh 地址。手动使用浏览器调试时，也要使用终端打印的完整 URL，直接访问 `http://127.0.0.1:3080/` 会提示需要认证。

主界面左下角的“设置 → 仿真软件”可配置求解位置、接入方式、HyperWorks 安装目录、HyperMesh 批处理程序、HyperView 和仿真工作目录。
每项路径均支持浏览选择；“检查路径”会验证文件或目录是否存在，“保存并重启”会持久化路径并重启后台，使 MCP 工具读取新配置。
模型 API Key 不会通过仿真配置接口发送到主界面，保存仿真路径也不会覆盖模型设置。尚未配置模型时也可以先保存仿真软件设置。

CAE 界面通过 `config/cae-airbag.cordis.yml` 关闭插件管理、插件创建“更多”、账号登录/意见反馈、内置插件配置和通用 Agent 预设入口。
`packages/cae-ui/` 是基于 dsh 设置扩展接口的本地插件，负责桌面应用的“模型”“仿真软件”和“缓存”页，无需修改 dsh 的依赖包。

对话顶部的“仿真工作流”打开 dsh 原生右侧栏，按六个阶段展示参数、实际产物和执行记录。小窗口的侧栏、对话与思考区域沿用 dsh 默认布局。每个阶段先由用户提交参数，再执行当前阶段；四分区、网格和后处理还需确认结果。缺少 HyperMesh、HyperView 或所选求解器配置时会引导到“设置 → 仿真软件”，保留当前文件和参数草稿。

网格阶段无需用户上传 `case.json`：表单只收网格尺寸、类型和可选的已认可参考 K 文件；系统在任务目录保存分区模型，助手据当前模型与项目证据生成 `mesh.case.json` 和 `mesh.gate.json`。无法可靠确定的分层、部件、装配参数或门禁基线必须暂停询问，不会套用 docs 样例，也不会跳过门禁。求解的装配位移、拉带数和终止时间，以及法规评判的测点、坐标依据和时刻都必须由当前项目提供。AI 分区预览支持点击放大、Esc 和关闭按钮。详细编排协议见 `skills/cae-airbag/SKILL.md`，算法仍来自 `docs` 下的四份技能。

对话沿用 dsh 原生上下文计量与压缩：CAE 预设显式挂载自动压缩、工具结果修剪和 `/compact`，约在窗口预算的 70% 压缩较早的历史，并为输出和压缩预留空间。`deepseek-flash`、`deepseek-v4-pro` 按当前内置模型目录使用 1,000,000 token 窗口；其它兼容模型暂使用 65,536 token 默认预算，实际容量仍由服务端决定。单次超长工具输出保留约 4,096 token 的预览和完整结果路径，完整参数配置、执行记录、几何与求解数据留在文件中，按当前阶段分页读取。工作流工具返回当前阶段摘要与参数文件路径，避免反复把完整状态放入模型上下文。

求解通常需要数小时，提交前需确认提示。同步求解工具最长等待 48 小时；后台重启或断线后须先检查实际任务状态再重试。执行中保存模型或软件设置会重启后台，因此应用会要求等当前阶段结束后再保存。工作流状态按对话保存在应用数据目录的 `workflows/` 中；Windows 打包同时携带工作流插件和对应技能脚本。

桌面应用使用应用内保存的模型配置；未配置时不会使用启动环境或 `.env` 中的模型密钥。直接运行 dsh 时，它会读取启动环境、项目 `.env` 和用户目录 `.env`，已有环境变量优先。
macOS 可以先验证界面、设置保存和模型对话；Windows CAE 软件的实际执行及安装包仍需在 Windows 上验证。

桌面应用只运行一个实例，重复打开会唤起现有窗口。启动时会先显示连接进度，并检查后台端口；端口被其他程序占用时会直接提示。
如需调整默认的 3080 端口，可在启动前设置 `DSH_PORT`（macOS 例如 `DSH_PORT=3081 pnpm dev`）。
Windows 启动日志保存在 `%APPDATA%\@cae\electron-shell\logs\startup.log`；文件超过 2 MiB 后轮转为 `startup.log.previous`。日志会记录后台标准输出、错误和退出状态，并遮盖已配置的 API Key、求解服务令牌及启动 URL 的 token。启动失败对话框会显示日志路径和最近的后台输出。

### 求解器部署方式

“设置 → 仿真软件”和桌面应用菜单的“设置…”均支持以下配置：

| 求解位置 | 本地求解方式 | 配置项 |
|----------|--------------|--------|
| 本地 | 软件 | 本机 LS-DYNA 可执行文件路径，沿用已有配置 |
| 本地 | 求解服务 | 本机 HTTP 求解服务地址，例如 `http://127.0.0.1:8000`，以及可选的访问令牌 |
| 服务端 | — | 远程 HTTP 求解服务地址，以及可选的访问令牌 |

默认使用“本地 → 软件”，已有设置会自动补齐默认值。切换模式保留各自的软件路径、服务地址和令牌；只有当前模式的连接信息会传给求解工具。选择服务模式后不会启动本地 LS-DYNA。前处理和后处理仍使用本机配置的 HyperWorks，与求解位置独立。

“测试连接”只发送健康检查，不提交求解任务；服务地址和令牌在保存时校验。仅使用模型对话时，软件路径可以留空。

求解服务需实现以下 CAE Agent HTTP 接口（服务本身需另行部署，本项目不自动安装求解服务）：

- `GET <服务地址>/health`：返回 HTTP 200 和 `{"status":"ok"}`。
- `POST <服务地址>/solve`：接受以下 JSON，**求解完成后**返回结果；服务地址可包含路径前缀。
- 配置访问令牌时，以上请求携带 `Authorization: Bearer <令牌>`。

```json
{
  "solver": "lsdyna",
  "keyword_file": "D:\\shared_jobs\\airbag\\main.k",
  "ncpu": 8,
  "memory": "4g",
  "output_dir": "D:\\shared_jobs\\airbag\\results"
}
```

`output_dir` 可省略，由服务选择默认输出目录。服务返回格式如下，`status` 必填，其他字段可选；`status` 支持 `ok`、`warning`、`error`。失败时可通过 `message` 或 `log` 返回原因。排队或执行中的任务需要由服务适配为完成后的同步结果，不能直接返回任务 ID 代替求解结果。

```json
{
  "status": "ok",
  "exitCode": 0,
  "d3plot": "D:\\shared_jobs\\airbag\\results\\d3plot",
  "logFile": "D:\\shared_jobs\\airbag\\results\\messag",
  "log": "Normal termination"
}
```

服务模式中的模型、INCLUDE 引用文件和输出目录路径均由求解服务解释，客户端不会要求这些路径在本机存在，也不会自动上传模型或下载结果。跨机器使用时需配置共享存储，或由服务适配文件路径；在本机后处理之前，结果必须能被本机访问。请求超时或断线后应先检查服务端任务状态，客户端不会自动重试提交任务。

直接运行 MCP/dsh 时，也可通过环境变量选择模式：`CAE_SOLVER_LOCATION=local|server`、`CAE_LOCAL_SOLVER_TYPE=software|service`、`CAE_SOLVER_SERVICE_URL`、`CAE_SOLVER_SERVICE_TOKEN`。地址填写服务根地址，不包含末尾的 `/health` 或 `/solve`；桌面设置优先于启动环境。

### 一键打包 Windows 压缩包和安装包

在项目根目录执行；首次使用先安装依赖：

```bash
pnpm install

# 同时生成 ZIP 免安装版和 EXE 安装包
pnpm dist:win

# 只生成 ZIP 免安装版
pnpm dist:win:zip

# 只生成 EXE 安装包
pnpm dist:win:installer
```

输出目录为 `packages/electron-shell/dist-app/`，文件名中的版本号跟随应用版本：

- `CAE-Agent-0.1.1-Windows-x64.zip`：完整解压后打开 `CAE Agent.exe`，不能只复制 EXE。
- `CAE-Agent-0.1.1-Windows-x64-Setup.exe`：安装向导，可选择安装目录，安装后从快捷方式启动。
- 每个发行文件都有对应的 `.sha256` 校验文件。

构建环境要求 Node.js >= 24.9.0 和 pnpm 10.x，支持在 macOS 或 Windows 上构建 Windows x64 版本。
脚本会自动构建项目、按锁文件安装 Windows 后台依赖，并内置 Node.js 24.14.0 和 uv；同时生成两个版本时只准备一次运行环境。
应用适用于 Windows 10/11 x64，使用时无需安装 Node.js 或 pnpm。
启动后直接进入主界面，开始使用模型时再填写自己的模型密钥。本机前后处理需安装 HyperWorks 并配置许可证；本地软件求解还需安装 LS-DYNA 并配置许可证，也可连接另行部署的本地或远程求解服务。首次启用 Python 工具需联网下载环境和依赖。桌面应用会先打开聊天界面，再在后台完成下载；下载失败会自动重试，不会阻塞 dsh 启动。

## 项目结构

```
cae-agent-harness/
├── packages/
│   ├── cae-mcp-server/          # MCP Server（所有 CAE 工具）
│   │   └── src/
│   │       ├── tools/
│   │       │   ├── hypermesh.ts  # hmbatch.exe 工具
│   │       │   ├── lsdyna.ts     # ls971.exe 求解器
│   │       │   ├── hyperview.ts  # hw.exe 后处理
│   │       │   └── report.ts     # pptxgenjs 报告
│   │       └── index.ts          # MCP Server 入口
│   └── electron-shell/          # Electron 桌面 Shell
│       └── src/main.ts           # 启动 dsh + BrowserWindow
├── skills/
│   └── cae-airbag/SKILL.md      # AI 工作流指引
└── config/
    ├── cae-airbag.cordis.yml    # dsh Profile（LLM + MCP + 系统提示）
    └── config.yaml              # Windows 可执行文件路径
```

## 切换到 QWen 模型

```bash
set LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
set LLM_MODEL=qwen-max
set DEEPSEEK_API_KEY=sk-<dashscope-api-key>
pnpm exec dsh web --patch config/cae-airbag.cordis.yml --no-open
```

## 使用本地 Ollama 模型

```bash
# 先启动 Ollama 并拉取模型
ollama pull qwen2.5-coder:32b

set LLM_BASE_URL=http://localhost:11434/v1
set LLM_MODEL=qwen2.5-coder:32b
set DEEPSEEK_API_KEY=ollama
pnpm exec dsh web --patch config/cae-airbag.cordis.yml --no-open
```

## dsh 版本

锁定 `@deepseek-ai/dsh@0.2.1-rc.5`，避免追最新 rc 引入破坏性变更。
