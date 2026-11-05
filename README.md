# CAE Agent Harness — 气帘仿真 AI Agent

基于 **dsh (deepseek-harness)** 的 CAE 气帘仿真 Agent，支持全流程自动化：
IGS 导入 → 模型分区 → 网格划分 → LS-DYNA 求解 → HyperView 导出 GIF → PPT 报告生成。

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

# 启动 dsh Agent（浏览器访问 http://localhost:3080）
npx @deepseek-ai/dsh --profile config/cae-airbag.cordis.yml
```

### 启动桌面应用（开发模式）

```bash
pnpm dev
```

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
npx @deepseek-ai/dsh --profile config/cae-airbag.cordis.yml
```

## 使用本地 Ollama 模型

```bash
# 先启动 Ollama 并拉取模型
ollama pull qwen2.5-coder:32b

set LLM_BASE_URL=http://localhost:11434/v1
set DEEPSEEK_API_KEY=ollama
npx @deepseek-ai/dsh --profile config/cae-airbag.cordis.yml
```

## dsh 版本

锁定 `@deepseek-ai/dsh@0.2.1-rc.5`，避免追最新 rc 引入破坏性变更。
