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

两个服务由 dsh 通过 cordis profile 的 `uv run --project` 自动启动，**无需手动安装**，首次启动时 uv 会自动创建虚拟环境并安装依赖。

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
| DeepSeek (默认) | `https://api.deepseek.com` | DeepSeek API Key |
| QWen (通义千问) | `https://dashscope.aliyuncs.com/compatible-mode/v1` | DashScope API Key |
| Ollama (本地) | `http://localhost:11434/v1` | `ollama` |

## 快速开始

### 环境要求
- Node.js >= 24.9.0
- pnpm >= 9.x
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

首次启动时，在设置窗口填写 API Key 后保存；以后可以通过应用菜单的“设置…”修改。
桌面应用会自动打开带认证 token 的 dsh 地址。手动使用浏览器调试时，也要使用终端打印的完整 URL，直接访问 `http://127.0.0.1:3080/` 会提示需要认证。

主界面左下角的“设置 → 仿真软件”可配置 HyperWorks 安装目录、HyperMesh 批处理程序、HyperView、LS-DYNA 和仿真工作目录。
每项路径均支持浏览选择；“检查路径”会验证文件或目录是否存在，“保存并重启”会持久化路径并重启后台，使 MCP 工具读取新配置。
模型 API Key 不会通过仿真配置接口发送到主界面，保存仿真路径也不会覆盖模型设置。

CAE 界面通过 `config/cae-airbag.cordis.yml` 关闭插件管理、插件创建“更多”、账号登录/意见反馈、内置插件配置和通用 Agent 预设入口。
`packages/cae-ui/` 是基于 dsh 设置扩展接口的本地插件，负责“仿真软件”页，无需修改 dsh 的依赖包。

桌面应用优先使用设置窗口中保存的配置。直接运行 dsh 时，它会读取启动环境、项目 `.env` 和用户目录 `.env`，已有环境变量优先；仅在 `.env` 中填写 API Key 不会跳过桌面应用的首次配置窗口。
macOS 可以先验证界面、设置保存和模型对话；Windows CAE 软件的实际执行及安装包仍需在 Windows 上验证。

如果日志出现 `EADDRINUSE`，说明端口已被其他进程占用，请退出之前启动的 CAE Agent 或 dsh 后重试。
需要同时运行多个实例时，在启动前设置不同的 `DSH_PORT`（macOS 例如 `DSH_PORT=3081 pnpm dev`）。

### 打包 Windows 安装包

```bash
pnpm build && pnpm dist:win
# 输出: packages/electron-shell/dist-app/*.exe
```

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
set DEEPSEEK_API_KEY=sk-<dashscope-api-key>
pnpm exec dsh web --patch config/cae-airbag.cordis.yml --no-open
```

## 使用本地 Ollama 模型

```bash
# 先启动 Ollama 并拉取模型
ollama pull qwen2.5-coder:32b

set LLM_BASE_URL=http://localhost:11434/v1
set DEEPSEEK_API_KEY=ollama
pnpm exec dsh web --patch config/cae-airbag.cordis.yml --no-open
```

## dsh 版本

锁定 `@deepseek-ai/dsh@0.2.1-rc.5`，避免追最新 rc 引入破坏性变更。
