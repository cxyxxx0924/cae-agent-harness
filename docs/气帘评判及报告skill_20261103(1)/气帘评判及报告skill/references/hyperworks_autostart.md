# HyperWorks + MCP 自动拉起与连接：为什么会反复失败，以及唯一可靠流程

> 这份文档是「怎么让 MCP 连上 HyperWorks」的**唯一权威入口**。
> 之前几次 `10061 连接被拒`、`status.json 写 online 但实际连不上`、`HyperView 自己开了但 MCP 摸不到`，
> 根因都落在这篇讲的几件事上。先读这篇，再读 `hyperview_postprocess.md` 做后处理。

---

## 0. 一句话结论

**永远通过 `mcp__hyperworks__launch_hypermesh` 工具来启动 HyperWorks。**
不要从 Bash/PowerShell 自己 `runhwx &`，也不要靠点 Windows 桌面的 HyperWorks 快捷方式打开。
前者会被回收，后者起不来 bridge 端口（插件消息泵没转）。

MCP 工具启动的进程挂在**常驻的 MCP server** 之下，是自动化环境里唯一能活下来的父进程树，
而且它带的启动参数恰好能让 live bridge 端口（`127.0.0.1:48761`）真正监听。

---

## 1. 两层结构（必须分清谁是谁）

| 层 | 是什么 | 端口 | 谁来启 | 挂谁下面 |
| --- | --- | --- | --- | --- |
| **MCP stdio 服务器** `hyperworks_mcp` | Python 包（venv：`~/.workbuddy/binaries/python/envs/hyperworks-mcp`），提供 `mcp__hyperworks__*` 工具 | 无（stdio） | WorkBuddy 宿主（connector 启用即自动起） | WorkBuddy 扩展宿主（长驻） |
| **live bridge** | 跑在 `hwx.exe` 进程内的 TCP 服务，由 CustomPlugin `HyperWorksMCP` 提供 | `127.0.0.1:48761` | **HyperWorks 启动时随插件加载** | 必须挂在能活下来的进程下 |

> 关键事实：`mcp__hyperworks__*` 工具里凡是带 `live_` / `postprocess_` 的，全部是**转发到 bridge** 的。
> 如果 bridge 端口没监听，这些工具全部报 `WinError 10061 目标计算机积极拒绝`。
> 所以「MCP 能用」和「bridge 在监听」是**两件事**：MCP server 活着 ≠ GUI/bridge 活着。

---

## 2. 为什么反复失败：四条根因（按出现频率）

### 根因 A —— 从 Bash/PowerShell 自己启动，命令结束即被整树回收（最常见）
`runhwx` 只是包装器：它拉起真正的 `hwx.exe` 后自己 `exit 0`。在自动化环境的**短命令**里，
命令一返回，整棵进程树（包括刚拉起的 hwx）被回收。
现象：`restart` 报 `ONLINE`，下一条命令立刻 `10061`。

**判定**：凡是「启动命令和后续调用不在同一条命令里、且启动进程不是常驻父进程」，
hwx 必死。Agent 的 Bash 工具就是这种短命令环境。

✅ 解法：启动必须由**常驻进程**发起 → 只有 MCP server 满足 → 用 `launch_hypermesh`。

### 根因 B —— 启动参数缺 `-plugin/-profile/-startwith`，进程起了但端口永不监听（“假成功”）
只给 `-client HyperWorksDesktop` 时，hwx 能起来、占 ~900 MB，但 **48761 永不监听**。
原因：缺 Launcher 插件初始化 → Qt 消息泵不转 → Extension 的 `QTimer` 不触发 → bridge 不绑端口。

实测唯一能起端口的命令（与 `server.py::launch_hypermesh` 源码逐字一致）：
```bash
"D:\Program Files\Altair\2026\hwdesktop\hwx\bin\win64\runhwx.exe" \
  -client HyperWorksDesktop \
  -plugin HyperworksLauncher -profile HyperworksLauncher \
  -l en -startwith HyperView
# cwd 必须是 allowed_roots：C:\Users\hekie\Documents\HyperWorksMCP\workspace
```
`launch_hypermesh` 工具**已经把这个命令写死**，所以走它就不会踩这个坑。

### 根因 C —— 用户手动点 Windows 快捷方式打开 HyperWorks，MCP 连不上（第二常见）
桌面/开始菜单的快捷方式**不带** `-plugin HyperworksLauncher -profile HyperworksLauncher -startwith ...`，
所以 Launcher 插件不初始化 → 即便 `HyperWorksMCP` CustomPlugin 被加载，它的 `QTimer` 也不转 → **bridge 端口不开**。
结果：HyperView 界面好好的，但 `get_live_bridge_status` 一直 `connected=False`，所有 `live_*` 工具全 10061。

**这是「我已经把 HyperWorks 打开了，你连一下」这句话失效的根因。**
✅ 解法：先关掉手动开的窗口，改用 `launch_hypermesh` 让它带着正确参数重启。

### 根因 D —— 用 `status.json` 判断在线（滞后，会骗人）
`AppData\Local/HyperWorksMCP/status.json` 在进程被 `taskkill /F` 后**仍写 `online`**，
滞后数秒到数十秒。拿它当判据会误判「连上了」。

✅ 唯一可信的判据：
- `netstat -ano | findstr 48761` 出现 `LISTENING`，或
- `mcp__hyperworks__get_live_bridge_status()` 返回 `connected=true`，或
- `python scripts/hv_render.py status` 打印 `ONLINE ✔`。

---

## 3. 唯一可靠的自动拉起 + 连接流程（照做即可）

### 步骤 1 —— 确认 MCP server 在线、且当前 bridge 状态
```
mcp__hyperworks__get_live_bridge_status()
# 返回 {"connected": false, ...} 表示 GUI 还没起（或已死）
```
（若工具本身调不通，说明 `hyperworks` connector 没启用 → 在连接器菜单里启用/信任它。）

### 步骤 2 —— 用 MCP 工具启动（不要碰 runhwx、不要碰桌面快捷方式）
```
mcp__hyperworks__launch_hypermesh(start_with="HyperView", language="en")
# 返回 {"launched": true, "pid": <n>, "application": "HyperView", ...}
```
这一步做了四件对的事：
1. 父进程是常驻 MCP server → hwx 不会被回收（解决根因 A）；
2. 带了完整 `-plugin/-profile/-startwith` 参数 → 端口会监听（解决根因 B）；
3. `cwd` 设在 `HYPERWORKS_MCP_WORKSPACE`（`Documents/HyperWorksMCP/workspace`）→ 满足 bridge 白名单；
4. 不依赖 `status.json`。

> 注意：`launch_hypermesh` 是 **fire-and-forget**（Popen 后立即返回），它**不会等端口起来**。
> 端口要 10–20 s 才监听，必须下一步轮询。

### 步骤 3 —— 轮询直到 bridge 真正连上（以 netstat / bridge status 为准）
循环调用（间隔 2–3 s，最多 ~30 s）：
```
mcp__hyperworks__get_live_bridge_status()
```
或等价地用脚本直连 bridge（不经 MCP）：
```bash
python scripts/hv_render.py status
# ONLINE ✔   (出现这个才算数)
```
看到 `connected=true` / `ONLINE ✔` 才算拉起成功。**在此之前不要调任何 `live_*` 工具。**

### 步骤 4 —— 正常调用后处理
现在 `mcp__hyperworks__*` 的 `live_*` / `postprocess_*` 工具全部可用，按 `hyperview_postprocess.md` 出图。

---

## 4. 重启完整循环（改了 `handlers.py` 或 bridge 卡死时必做）

1. **找监听者 PID（只杀 48761 的占用者，别盲杀所有 hwx）**
   ```bash
   netstat -ano | findstr 48761 | findstr LISTENING
   # 取最后一列 PID
   ```
2. **结束它**
   ```bash
   taskkill /PID <pid> /F
   ```
3. **等端口释放**（TIME_WAIT 没清会重绑失败，通常 3–10 s）。
4. **重新启动** → 走 §3 步骤 2 的 `launch_hypermesh`，不要走桌面快捷方式。
5. **轮询** → 走 §3 步骤 3。

> 扩展**没有热重载**：`handlers.py` 只在 HyperWorks 启动时读一次（`__init__` 一次性绑定注册表）。
> 改了代码 → 必须走上面的完整循环重启，没有别的办法。

---

## 5. 环境/配置核对清单（出问题先逐项打勾）

| 项 | 正确值 / 位置 | 怎么查 |
| --- | --- | --- |
| `hyperworks` connector | 已启用且已信任 | WorkBuddy 连接器菜单 |
| `HYPERWORKS_HOME` | `D:\Program Files\Altair\2026` | `~/.workbuddy/mcp.json` 的 `hyperworks.env` |
| `HYPERWORKS_MCP_WORKSPACE` | `C:\Users\hekie\Documents\HyperWorksMCP\workspace` | 同上；也是 bridge `allowed_roots` |
| `HYPERWORKS_MCP_BRIDGE_CONFIG` | `C:\Users\hekie\AppData\Local\HyperWorksMCP\bridge.json` | 同上 |
| bridge 端口 | `127.0.0.1:48761` | `bridge.json` 的 `host`/`port` |
| bridge 白名单 | `allowed_roots` 仅含上面的 workspace | `bridge.json` |
| CustomPlugin 位置 | `C:\Users\hekie\Documents\Altair\CustomPlugins\HyperWorksMCP\` | 文件系统 |
| 启动参数 | 含 `-plugin HyperworksLauncher -profile HyperworksLauncher -startwith HyperView` | 只能经 `launch_hypermesh` 保证 |

---

## 6. 故障速查

| 症状 | 根因 | 处置 |
| --- | --- | --- |
| `WinError 10061` 调 `live_*` 工具 | bridge 没起 / 进程被回收 | 走 §3：`launch_hypermesh` → 轮询到 `ONLINE` |
| HyperView 界面在、但 bridge 连不上 | 根因 C：手动快捷方式开的，参数缺 Launcher | 关掉它，改用 `launch_hypermesh` 重启 |
| `launch_hypermesh` 返回了，但紧接着 10061 | 没轮询（fire-and-forget，端口要 10–20 s） | 走 §3 步骤 3 轮询 |
| hv_render.py `restart` 报 ONLINE 但下条命令 10061 | 根因 A：restart 从临时 python 子进程拉起，被回收 | **自动化里别用 `restart`**，只用 `launch_hypermesh` |
| 端口占着但 `status.json` 写 online 实际死 | 根因 D：status.json 滞后 | 以 netstat / `get_live_bridge_status` 为准 |
| 大 H3D 调用偶发掉线 | 重型调用偶发断连 | 重跑或重启后恢复 |
| 改了 `handlers.py` 没生效 | 扩展无热重载 | 走 §4 完整重启循环 |

---

## 7. 给以后的自己 / 后续会话的约定

- **「我要连 HyperWorks」= 先调 `get_live_bridge_status`，不是 `connected` 就调 `launch_hypermesh`，再轮询。**
  不要用 Bash 启动，不要用桌面快捷方式。
- 轮询用 `get_live_bridge_status` 或 `hv_render.py status`，**不要读 status.json**。
- 任何 `live_*` / `postprocess_*` 调用前，先确认 `ONLINE`。
- 重型结果（200 MB+ H3D）单次调用设超时 `HW_BRIDGE_TIMEOUT=900` 或更高。
