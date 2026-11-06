# 01 · HyperMesh MCP 接入与 live bridge（2026）

> 实测环境：HyperWorks 2026.0.0.27 `D:\Program Files\Altair\2026`
> MCP 包 `hyperworks_mcp` **0.10.0**（FastMCP 2.14.7，65 个工具）

---

## 1. 服务端本体

| 项 | 值 |
|---|---|
| 包 | `hyperworks_mcp` 0.10.0 |
| venv | `C:\Users\hekie\.workbuddy\binaries\python\envs\hyperworks-mcp` |
| 启动 | `python -m hyperworks_mcp`（stdio 传输） |
| 源码 | `<venv>\Lib\site-packages\hyperworks_mcp\` |
| 关键模块 | `environment.py`（安装根探测）、`projects.py`（project_id 校验）、`live_bridge.py`（GUI 通道） |

### mcp.json 完整条目

```jsonc
"hyperworks": {
  "command": "C:\\Users\\hekie\\.workbuddy\\binaries\\python\\envs\\hyperworks-mcp\\Scripts\\python.exe",
  "args": ["-m", "hyperworks_mcp"],
  "env": {
    "HYPERWORKS_HOME": "D:\\Program Files\\Altair\\2026",
    "HYPERWORKS_MCP_WORKSPACE": "C:\\Users\\hekie\\Documents\\HyperWorksMCP\\workspace",
    "OPTISTRUCT_EXECUTABLE": "E:\\BaiduNetdiskDownload\\Hyperworks2020\\2020\\hwsolvers\\scripts\\optistruct.bat",
    "RADIOSS_EXECUTABLE": "E:\\BaiduNetdiskDownload\\Hyperworks2020\\2020\\hwsolvers\\scripts\\radioss.bat",
    "PYTHONUTF8": "1"
  }
}
```

**2026 不带 hwsolvers**（无 OptiStruct/Radioss）→ 求解器必须指回 2020。
`HYPERWORKS_HOME` 决定 hmbatch / runhwx / hstbatch 的探测根。

---

## 2. 热切换安装根（不用重启 MCP）

```
mcp__hyperworks__configure_installation(path="D:\\Program Files\\Altair\\2026")
```
返回应含：
```
installation_root : D:\Program Files\Altair\2026
runhwx(GUI)       : ✓ hwx\bin\win64\runhwx.exe
hmbatch(批处理)   : ✓ hm\bin\win64\hmbatch.exe
hstbatch / hstpy  : ✓
framework_hwx     : ✓
optistruct/radioss: ✗  ← 2026 没装，正常
```
切回 2020 同理，把 path 换成 `E:\BaiduNetdiskDownload\Hyperworks2020\2020`。

**验证三连**（服务端活着的判据）：
```
get_environment → get_live_bridge_status → get_live_capabilities
```

---

## 3. live bridge（GUI 内 Python 直连）

### 前置条件（缺一不可）

1. **HyperMesh 2026 GUI 已启动**
   - **让用户自己启动**（我代用 `launch_hypermesh` 起过，结果多出一个孤儿实例要 taskkill）
   - profile 选 **LsDyna (Keyword971_R16.0)**
2. **Extension 开关打开**：HyperWorks MCP Bridge（0.9.1）
   - 扩展已装在 `C:\Users\hekie\Documents\Altair\CustomPlugins\HyperWorksMCP`
   - 安装树里**找不到**该目录，它在用户 Documents 下，对 2026 通用
3. 端口 `127.0.0.1:48761` 处于 LISTENING

### 状态自检

```powershell
netstat -ano | Select-String 48761
Get-Content "C:\Users\hekie\AppData\Local\HyperWorksMCP\status.json"
Get-Process | ? { $_.ProcessName -match "^hw$|^hwx|runhwx" }     # 应只有 1 个
```

### 载入模型的正确姿势（顺序不能反）

```
1) create_project(name="cab1_2026_live")
     → 返回 project_20261020_110617_037243
2) 复制输入文件到 <workspace>/projects/<proj>/input/
3) load_live_model(input_name="cab1.hm", project_id="<proj>", replace_current=true)
```

> **P8**：`project_id` 必须是 `create_project` 返回的**项目 id**，
> 传磁盘路径会报 invalid。`projects.py` 里校验的是 workspace 下的项目注册表。
>
> **P8b**：`load_live_model(path=...)` 这种直接传绝对路径的写法也失败——
> 必须走"建项目 → 放 input → 按 input_name 载入"三步。

### 可用 live 方法（40 个，常用）

| 类别 | 工具 |
|---|---|
| 模型 | `get_live_model_summary` / `list_live_entities` / `get_live_session_info` |
| 网格 | `automesh_surfaces` / `repair_mesh_quality` / `get_mesh_quality` / `get_model_metrics` |
| 交互 | `interactive_select`（模型树框选，配合 GUI 目检） |
| 通道 | `run_hmbatch` / `write_tcl_script` / `get_live_capabilities` |

**工作方式建议**（用户偏好）：
几何/图形类工作**用图像对话，不要自动猜语义**——我先把数据渲染成固定坐标系的标准底图
（`export_lines_pts.tcl` + `render_lines.py`），用户在图上高亮/描线，我再按坐标做空间匹配。
语义归人，几何归机器。

---

## 4. 与 hmbatch 的分工

| 场景 | 选 |
|---|---|
| 交付链 / 批量 / 要可复现 | **hmbatch**（确定性，无 GUI 依赖） |
| 探查几何、目检网格、试参数 | **MCP live bridge** |
| 求解 | 都不行，走 2020 hwsolvers 或 LS-DYNA |

**实际用法**：MCP 里探明白 → 固化成 Tcl → hmbatch 跑交付。
不要把交互式探测结果直接当交付物。

---

## 5. 常见故障

| 现象 | 原因 / 处理 |
|---|---|
| MCP 一直 "Still connecting" | 服务端启动失败；用 `python -m hyperworks_mcp` 手动跑一次看 stderr |
| `get_live_bridge_status` 说 offline | GUI 没启动，或 Extension 开关没打开 |
| live 调用首次超时 | GUI 正忙（载入大模型），重试即可——不是配置问题 |
| 存在多个 hw.exe | 杀掉多余实例；只保留用户启动的那个 |
| `get_environment` 显示 2020 | 忘了 `configure_installation`，或 mcp.json 未生效（改配置要重开会话） |
