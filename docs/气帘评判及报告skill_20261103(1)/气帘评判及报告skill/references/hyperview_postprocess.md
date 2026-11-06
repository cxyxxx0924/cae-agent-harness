# HyperView 后处理：d3plot / H3D → 云图 → 四视角 → GIF / PPT 素材

本篇是**实测跑通**的记录，不是推测。涉及命令的地方都注明"怎么验证它对不对"。

统一入口：`scripts/hv_render.py`（子命令 `status / restart / single / shots / check / gif / anim`）。

---

## 0. 能力边界（先对齐预期，别做无用功）

| 想要 | 能不能 | 说明 |
| --- | --- | --- |
| d3plot / H3D 读入并出位移云图 PNG | ✅ | `single` / `shots` |
| 前/后/左/右 四正交视角同步截图 | ✅ | 只能在 Tcl 层设，Python 层没有相机 API |
| 多时间步 → 2×2 动画 GIF | ✅ | `anim`，21 帧 GIF 约 3.4 MB |
| 取某节点/单元的历史数值 | ✅ | `postprocess_hyperview_shots` 不返回；用 `postprocess_hyperview_result` 的 Top-N 或 `extract_hypergraph_time_history` |
| 从 H3D 里读"气帘厚度/压力/容积" | ❌ | H3D 通常只有 `Displacement` 与 `Effective plastic strain`；厚度要从 **d3plot 双层壳**算（见 `cae_measurement.md`） |
| 批量出 20 个算例的对比图 | ⚠️ | bridge 一次调用一个模型；脚本循环，但每次都要重载，慢 |

> 一句判据：**要数值 → 走 d3plot + lasso（`g14_thickness.py`）；要形貌与证据图 → 走 HyperView（本 CLI）。**
> 两者不是替代关系，报告里也常同时出现（数值表 + 形态截图）。

---

## 1. 两个 bridge 方法

### 1.1 `postprocess_hyperview_result` —— 单张云图 + Top-N 数值

```bash
python scripts/hv_render.py single --model M --result R --out out/x.png \
    --type Displacement --comp Mag --entity node --sim last --limit 10
```

| 参数 | 说明 |
| --- | --- |
| `model_file` | 白名单 `.fem .bdf .dat .h3d .rad .key` **+ d3plot 家族**（见 §2） |
| `result_file` | 白名单 `.h3d .op2 .d3plot .h5 .hdf5` **+ d3plot 家族** |
| `output_file` | 必须 `.png`，且位于 `allowed_roots` 下 |
| `data_type` / `data_component` | 如 `Displacement` / `Mag`；非法字符会被正则拒 |
| `entity_type` | `node` / `element` |
| `simulation` | 整数帧或 `"last"` |
| `query_limit` | 返回 Top-N 实体（默认 10） |

返回要点：`contour.entities[]` 里每个 `{node_id, value, contour}`；`screenshot.path / size_bytes`。
**只有数值，没有变形后坐标**——所以量距离必须另开 d3plot。

### 1.2 `postprocess_hyperview_shots` —— 多视角 × 多时间步

```bash
python scripts/hv_render.py shots --model M --result R --outdir out/ \
    --views front,back,left,right --steps 1:82:4
```

| 参数 | 说明 |
| --- | --- |
| `output_dir` | 每张写 `<view>_s<sim>.png`，并额外写 `shots.json`（本 CLI 行为） |
| `views` | `front back left right top bottom iso` 的子集 |
| `simulations` | 整数列表，或 `["last"]` |

返回：`shots[] = {view, simulation, path, size_bytes, md5, draw_status}` + `view_orientations` + `orient_errors`。
**`md5` 是内置自检字段**——四视角若相同，md5 会完全相同，这是发现"视角没生效"最快的手段。

---

## 2. d3plot 专项（踩过坑，已修）

### 2.1 文件名没有扩展名
LS-DYNA 输出的是 `d3plot`、`d3plot01`、`d3plotaa`，**`Path("d3plot").suffix == ""`**。
所以纯后缀白名单会把每一个真实 d3plot 拒掉，报：

```
ValueError: result_file must be an allowlisted HyperView result format
```

已在 `handlers.py` 修（2026-11-02）：加 `_is_d3plot_family()`，按 basename 匹配
`^d3plot(\d{1,3}|[a-z]{2})?$`，并同时放宽 `model_file` 的白名单
（d3plot 自带网格，`model_file` 与 `result_file` 传**同一个路径**）。

```bash
# 典型调用：model 与 result 同路径
--model  <ws>/Iter05_d3plot/d3plot \
--result <ws>/Iter05_d3plot/d3plot
```

### 2.2 状态数未知时先探测
`--frames N` 时 CLI 会先发一次 `views=["front"], simulations=["last"]` 探出末步 id，
再按 `1..last` 均分出 N 个步。
实测某 d3plot 只有 **6 个状态**（`Frame 6, Time 1.24647`），`--frames 9` 会被自动压到 6 步——
**不要假设你的算例有 80 帧**，先在返回的 `shots.json` 里看 `simulation` 最大值。

### 2.3 拷贝位置
大 d3plot 必须落在 `Documents/HyperWorksMCP/workspace` 下（`allowed_roots`）。
172 MB / 7 段的 d3plot 拷进去约 10 s。**不要用符号链接/联接**——bridge 会做真实路径校验。

---

## 3. 视角控制：只能走 Tcl，且四个细节全踩过

Python 侧 `hw.hv` 的 Window 对象在本构建里**没有任何相机方法**
（`dir(window)` 87 个方法里没有 `setView/setOrientation/getView/camera`），
唯一可用的是 `hw.evalTcl` 转发到 HyperView 的 `hwi` 命令栈。

正确命令序列（已封装在 `postprocess_hyperview_shots`）：

```tcl
hwi GetSessionHandle __s1
__s1 GetProjectHandle __p1
__p1 GetPageHandle __pg1 <真实的 page.id>     ;# 不是 1！
__pg1 GetWindowHandle __w1 1
__w1 GetViewControlHandle __vc1
__vc1 GetActiveView
__vc1 SetOrientation Front                    ;# 首字母大写；没有 SetView
__vc1 Fit
__w1 Draw
```

四个致命细节：

1. **`GetPageHandle` 必须用 Python 侧 `int(page.id)`。**
   Python 新建的 Page 通常是 **id=2** 且成为 active page；
   写死 `1` 会去操作 page 1 的**空窗口** → `SetOrientation` 全部"成功"、
   `GetOrientation` 返回全 0、**截图永远不变**。
   诊断：Tcl 里 `__p1 GetActivePage` 的返回值就是真实页号（实测 2）。
2. **Tcl handle 跨 `eval_tcl` 调用不会自动清。** 同名再 `GetSessionHandle` 抛
   `__s: object with this name already exists`，**整条命令链在此中断**，
   后面的 `SetOrientation` 一条都不执行 → 表现为"只有第一个视角生效"。
   解法：每次调用用唯一名（`__s1/__s2/...`），或全部 `catch{}` 包住。
3. **没有 `SetView`。** `hwIViewControl` 上只有 `SetOrientation <Front|Back|Left|Right|Top|Bottom|ISO>`；
   `hwIWindow` 上也没有 `SetView`。写 `SetView` 只会静默失败。
4. **Python `window.draw()` 会把相机重置回默认等轴测**，冲掉 Tcl 设的方位。
   设完视角后只用 `__w1 Draw`（必要时再 `__c1 Draw`）。
   同理 `result.simulation = sid` 会触发一次 Python 重绘 → **先切时间步，再设视角**。

验证手法（比看日志可靠）：

```bash
python scripts/hv_render.py check --shots out/shots.json
# unique md5 == 总数  → 视角区分正常
# unique md5 == 1     → 上面四条必有一条没做到
```

---

## 4. 从截图到报告素材

| 素材 | 怎么来 | 用在哪 |
| --- | --- | --- |
| 单张云图 PNG | `single` | 证据页（附时刻、结果类型、量程） |
| 2×2 四视角 GIF | `anim` → `--gif` | 展开过程页（模仿客户参考报告第 4 页） |
| 末帧 2×2 静态拼版 PNG | `anim` → `--png` | 动画不播/打印时的兜底，同页并列放 |
| 四视角单帧（front/back/left/right） | `shots` 的 `out/*.png` | 需要单格排版时逐张用 |

排版细节（裁白边、角标、GIF 参数、`<Image>` 必写宽高）见 `ppt_assets.md`。

---

## 5. 故障排查表

| 症状 | 原因 | 处置 |
| --- | --- | --- |
| `WinError 10061 目标计算机积极拒绝` | bridge 没起 / 进程已被回收 | `hv_render.py status`；用 MCP 的 `launch_hypermesh(start_with="HyperView")` 或自己终端跑 `restart` |
| hwx 占 900 MB 但端口不监听 | 非官方参数启动，缺 `-plugin/-profile/-startwith`，Qt 消息泵不转 | 用 `restart` 里的完整命令（见 `hyperworks_bridge.md`） |
| `result_file must be an allowlisted...` | d3plot 无扩展名 | 确认 `handlers.py` 已含 `_is_d3plot_family`（2026-11-02 补丁） |
| `ValueError: Output path is outside configured save roots` | 路径不在 `allowed_roots` 下 | 拷到 `Documents/HyperWorksMCP/workspace/...` |
| 四张图 md5 全相同 | page id 写死 1 / handle 重名 / `SetView` / Python draw 重置 | 见 §3 四条 |
| 改了 `handlers.py` 却没生效 | 扩展**无热重载**，只在启动时读一次 | 重启 HyperView |
| 调用超时（60 s 默认） | 大 d3plot 首次加载慢 | `HW_BRIDGE_TIMEOUT=900` |
| `slidep screenshot` 报 Vulkan 错 | 无头环境没有 GPU 合成 | 改用 zip 校验（见 `ppt_assets.md`） |
