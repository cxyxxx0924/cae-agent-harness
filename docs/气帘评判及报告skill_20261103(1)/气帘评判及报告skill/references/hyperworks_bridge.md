# HyperWorks 2026 联通：MCP / live bridge 与正确启动方式

本篇解决**唯一一个真正的门槛**：怎么把 HyperView 拉起来并让 bridge 绑端口。
端口一通，其余全是普通调用（见 `hyperview_postprocess.md`）。

> **2026-11-03 增补：自动拉起 + 连接为什么反复失败、唯一可靠流程，已单独成篇
> `hyperworks_autostart.md`——那是这个问题的权威入口，先读它。**
> 本篇保留技术细节与连接参数。

---

## 1. 两层结构

| 层 | 是什么 | 端口 | 谁来启 |
| --- | --- | --- | --- |
| **MCP stdio 服务器** `hyperworks_mcp` | Python 包（venv 在 `~/.workbuddy/binaries/python/envs/hyperworks-mcp`），提供 `mcp__hyperworks__*` 工具 | 无（stdio） | 宿主；**经常没自启** |
| **live bridge** | 跑在 HyperWorks GUI（`hwx.exe`）进程内的 TCP 服务，由 CustomPlugin "HyperWorksMCP" 提供 | `127.0.0.1:48761` | HyperWorks 启动时自动加载 |

> 实践：**stdio MCP 常常不可用，但 live bridge 只要 HyperView 在跑就在**。
> 所以脚本一律直连 bridge（`scripts/hw_bridge.py`、`scripts/hv_render.py`），
> 不依赖 stdio。只有"启动 HyperWorks"这一件事，用 MCP 工具最省事。

---

## 2. 正确启动方式（关键）

**唯一可靠的命令行**（与 `hyperworks_mcp/server.py::launch_hypermesh` 完全一致）：

```bash
"D:\Program Files\Altair\2026\hwdesktop\hwx\bin\win64\runhwx.exe" \
  -client HyperWorksDesktop \
  -plugin HyperworksLauncher -profile HyperworksLauncher \
  -l en -startwith HyperView
# cwd 必须是 allowed_roots 里的目录（如 Documents/HyperWorksMCP/workspace）
```

`hv_render.py restart` 就是把上面这条 + 杀端口 + 轮询 三步封装好了：

```bash
python scripts/hv_render.py restart --app HyperView --wait 200
# [1/4] 结束占用 48761 的进程
# [2/4] 端口已释放
# [3/4] 启动 HyperView（打印完整命令与 pid）
# [4/4] 等待 bridge 上线 → ONLINE ✔
```

### 为什么"裸起"不行（三种失败模式，全试过）

| 做法 | 结果 |
| --- | --- |
| 只给 `-client HyperWorksDesktop`（缺 `-plugin/-profile/-startwith`） | 进程能起、占 ~900 MB，但 **48761 永不监听**：缺 Launcher 插件初始化，Qt 消息泵不转 → Extension 的 `QTimer` 不触发 |
| 在 agent 的 bash 后台任务里 `runhwx &` | `runhwx` 是包装器，拉起 `hwx` 后自己 exit 0；任务结束时**整棵进程树被回收**，hwx 跟着死 |
| `DETACHED_PROCESS` / `CREATE_NEW_PROCESS_GROUP` | 同上，或拿不到交互式窗口站 → GUI 初始化阶段崩 |
| **点 Windows 桌面/开始菜单快捷方式手动打开** | 快捷方式不带 `-plugin/-profile/-startwith` → Launcher 不初始化 → 即便 `HyperWorksMCP` 插件被加载，`QTimer` 也不转 → **bridge 端口永不开**。现象：HyperView 界面好好的，但 `get_live_bridge_status` 一直 `connected=false`，所有 `live_*` 工具全 10061。**（这就是「我已经把 HyperWorks 打开了，你连一下」失效的根因。）** 解法：关掉它，改用 `launch_hypermesh` 重启 |

`-plugin HyperworksLauncher -profile HyperworksLauncher -startwith HyperView` 是分水岭：
加上它，端口 10–20 s 内就监听。

### 沙箱/自动化环境的一条限制

`hv_render.py restart` 在**你自己的终端**里没问题（Windows 默认父进程退出不杀子进程）。
但在**受管沙箱的短命令里**启动，即便加了 `CREATE_BREAKAWAY_FROM_JOB`，子进程仍会被回收
（实测：restart 报 ONLINE，下一条命令就 10061）。

→ 在自动化环境里请用 MCP 工具启动（它的父进程是常驻 MCP server）：

```
mcp__hyperworks__launch_hypermesh(start_with="HyperView", language="en")
```

### 重启完整循环（改完 handlers.py 必做）

```bash
# 1) 找出监听者并结束（不要盲杀所有 hwx，可能误伤用户的 HyperMesh）
PID=$(netstat -ano | grep 48761 | grep LISTENING | awk '{print $5}' | head -1)
taskkill //PID $PID //F
# 2) 等端口释放（TIME_WAIT 未清会导致重绑失败，通常 3–10 s）
# 3) 启动（§2 命令 或 MCP 工具）
# 4) 轮询：python scripts/hv_render.py status  直到 ping OK（约 10–20 s）
```

**扩展没有热重载**：`handlers.py` 只在 HyperWorks 启动时读一次，注册表在 `__init__` 一次性绑定。
改代码 → 必须重启，没有别的办法。

---

## 3. 连接参数（客户端自动读取）

`C:\Users\hekie\AppData\Local\HyperWorksMCP\bridge.json`：

| 字段 | 值 |
| --- | --- |
| `host` / `port` | `127.0.0.1` / `48761` |
| `token` | 64 字符 HMAC，`LiveBridgeClient` 自动注入 |
| `allowed_roots` | `["C:\\Users\\hekie\\Documents\\HyperWorksMCP\\workspace"]` |
| `request_timeout_seconds` | 600 |

- 探活：`python scripts/hw_bridge.py ping` → `{"bridge":"hyperworks-mcp-extension","version":"0.9.1"}`
- 能力：`python scripts/hw_bridge.py get_capabilities` → `hm / hw / hw.hv / hw.hg / report / hwx.gui`
- **输入输出都必须在 `allowed_roots` 内**，否则 `ValueError: Output path is outside configured save roots`。
  做法：把 `.h3d` / d3plot 拷到 `Documents/HyperWorksMCP/workspace/<子目录>/`，截图也写在那下面。
  （不要用符号链接/联接绕过——会做真实路径校验。）

---

## 4. 客户端

| 工具 | 用途 |
| --- | --- |
| `scripts/hw_bridge.py` | 极薄转发：`hw_bridge.py <method> '<json>'`，看原始返回 |
| `scripts/hv_render.py` | 面向任务：`status/restart/single/shots/check/gif/anim`，带自检与安全提示 |

两者都从 venv 的 site-packages 动态 import `hyperworks_mcp.live_bridge`，
所以**用系统 python 跑即可**（venv 里没有 Pillow，`hv_render.py` 出 GIF 需要 Pillow）。

---

## 5. 处理器源码位置（要改行为时）

```
C:\Users\hekie\Documents\Altair\CustomPlugins\HyperWorksMCP\hyperworks_mcp_extension\
├─ handlers.py     # 方法实现与 dispatch 注册表（__init__ 里一次性绑定）
├─ bridge.py       # TCP 服务、HMAC 校验、daemon 线程 + QTimer
└─ runtime.py      # load() → BridgeRuntime().start()
```

已做的两处本地增强（2026-10-31 / 11-02）：

1. `postprocess_hyperview_shots`（新增）—— 多视角 × 多时间步截图，返回 md5；
2. d3plot 家族白名单 `_is_d3plot_family()` —— 放行无扩展名的 `d3plot/d3plot01/d3plotaa`，
   同时放宽 `model_file`（d3plot 自带网格）。

---

## 6. 已知脆性

- 200 MB+ H3D 的重型调用偶发掉线（WinError 10061）；重跑或重启后恢复。
- 同一 HyperView 里反复新建 Page 会累积；大批量算例建议每次重启，别在一个会话里跑几十个模型。
- `status.json`（在 `AppData\Local\HyperWorksMCP\`）会滞后：进程被 `taskkill /F` 后它仍写 `online`。
  **以 `netstat` + `ping` 为准，不要信 status.json。**
