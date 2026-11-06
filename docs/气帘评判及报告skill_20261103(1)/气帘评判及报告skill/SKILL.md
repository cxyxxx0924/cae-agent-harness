---
name: curtain-eval-report
description: 依据 C-NCAP 附录G G.14.3 评价侧面气帘/头胸一体式气囊（外观尺寸、展开形态、动态保护），从 LS-DYNA d3plot / H3D 里量缝线带宽、非充气斑、评估区覆盖率、头部落点与 Y 向展开厚度，并把 d3plot/H3D 渲染成位移云图、前/后/左/右四视角展开动画 GIF 等报告素材，产出沿用客户模板风格的中文 PPT 报告。当用户要求"按法规评价气帘""做 IC Coverage 类报告""判断 15mm/50mm/触底是否满足""用参考报告的头部坐标评判""把 d3plot 出成云图/四视角动画""连 HyperWorks 后处理出报告素材"时使用。
agent_created: true
---

# 侧面气帘评判及报告 Skill

把"按 C-NCAP 附录G G.14.3 评价侧面气帘 + 出中文 PPT 报告"沉淀成可复现的链路：
定性判据怎么读 → 数据从哪来 → 脚本怎么量 → 结论怎么措辞 → 报告怎么排版。

## 先读哪一份

| 你要做的事 | 读这个 |
| --- | --- |
| 条文本身、尺寸链、罚分 | `references/g143_criteria.md` |
| 15 mm / 50 mm / 触底到底在说什么，常见误读 | `references/regulation_interpretation.md` |
| 从 d3plot/H3D 量厚度、缝线、覆盖率的具体算法与坑 | `references/cae_measurement.md` |
| 报告页序、每页放什么、结论怎么写 | `references/report_structure.md` |
| slidep DSL 用法、设计系统、排版校验 | `references/ppt_workflow.md` |
| **d3plot/H3D → 云图 / 四视角 / GIF 的完整后处理** | `references/hyperview_postprocess.md` |
| **截图 → PPT 素材（拼版、GIF 参数、落位、md5 校验）** | `references/ppt_assets.md` |
| HyperWorks 启动、重启、bridge 联通 | `references/hyperworks_bridge.md` |
| **MCP 自动拉起 + 连接：为什么反复失败、唯一可靠流程** | `references/hyperworks_autostart.md` |
| **头型 vs 展开气帘：离线断面/厚度/重叠图管线** | `references/head_curtain_evidence.md` |
| 客户参考报告（Autoliv IC Coverage）的结构与坐标表 | `references/reference_report_heads.md` |

## 核心认知（先记住这四条，再动手）

1. **15 mm 量的不是缝线**，是相邻两个充气腔之间那条**不充气带**的宽度；**50 mm 量的是局部不充气斑**（拉带锚点、缝线交汇、贴片）。两者都只在**评估区域内**统计，测量条件是**静态展开、袋内 0.1–0.4 bar**（或厂家推荐值）。
2. **评估区域 = 圆角四边形**，四角圆心由 5%/95% 头部重心确定；尺寸链 82/82/82/52、圆角 r=82（图 G.3）。它只在**侧视投影**上定义，Y 向没有约束。
3. **动态保护是三条同时成立**：落点在充气区（缝线区仍满足 15/50）+ 无硬接触 + 无触底。三者缺一不能判 PASS，只能判"证据不足"。
4. **两套坐标通常不能直接相减**。参考报告用整车全局系，`*AIRBAG_REFERENCE_GEOMETRY` 或平铺 IC 用局部系，量级就能差一个数量级。先证明坐标系可对齐，再谈覆盖结论。

## 工作流

### 0. 确认输入齐不齐
需要的输入与缺失后果：

| 输入 | 缺了会怎样 |
| --- | --- |
| 气帘 deck（含 BELT/CAVITY/SEAM/TETHER 四分区） | 只能做云图目检，无法分区统计 |
| d3plot 或 H3D（含节点坐标/位移） | 无法量厚度、无法定时刻 |
| 头部重心坐标（含坐标系说明） | 无法定评估区域 |
| 假人模型 + 接触力/加速度 | 触底只能算静态间隙，判不了二次尖峰 |
| 真实 inflator 质量流/压力曲线 | 展开时序全部不可用（见坑 1） |

### 1. 几何筛查（不需要结果文件）
```bash
python scripts/g14_mesh_check.py --deck cab1_clean.k --out out/ \
  --points heads.json --dz -270 \
  --cog5-x 3197.2 --cog5-z 1126.2 --cog95-z 1135.2
```
输出 `g14_screening.json`：缝线连通域、带宽（含 `rows_across` 单排判定）、非充气斑、评估区覆盖率、落点分类。
判读要点：
- `rows_across < 2` → 缝线是单排理想化，**15 mm 判据不可验证**，结论只能是 INDETERMINATE，别说 PASS；
- `coverage_pct.CAVITY` 才是"被充气区覆盖"的比例；BELT/SEAM 不算；
- 落点 `OUT_OF_CUSHION` 先怀疑坐标系，别急着写"覆盖不足"。

### 2. 厚度与时刻定格
```bash
# 使用 lspp-mcp 环境里的 lasso（系统 python 通常没有）
"C:/Users/hekie/.workbuddy/binaries/python/envs/lspp-mcp/Scripts/python.exe" \
  scripts/g14_thickness.py --d3plot run/d3plot --points heads.json \
  --dx -1515 --dz -625 --t-main 160 --t-early 120 --tdet 100 --figures --out out/
```
- 气帘是双层壳，按**初始态** (x,z) 配对两张壳，厚度 = 变形后两节点的 Y 向距离；
- 初始厚度应当是一个常数（本例 1.0 mm）；不是常数说明配对错了；
- 输出 `thickness_summary.json` / `thickness_points.json` / 两张图；
- 不知道平移量时用 `--solve-translation`（点位里带 `thk` 目标值），它会反求一个使厚度匹配的 (dx,dz)，但**必须当成临时基准**写进报告。

### 3. 汇总判据
每条判据只允许三种结论：`PASS` / `FAIL` / `INDETERMINATE`，并在报告里写清证据来源（哪个文件、哪个时刻、哪张图）。判据与证据的对应表见 `references/report_structure.md`。

### 4. 出报告素材（云图 / 四视角动画）
一条命令从 d3plot 或 H3D 拿到可进报告的图：

```bash
python scripts/hv_render.py status                       # 先确认 bridge 在线
python scripts/hv_render.py restart --app HyperView      # 不在线就自己拉起来
python scripts/hv_render.py anim \
    --model  <ws>/Iter05_d3plot/d3plot --result <ws>/Iter05_d3plot/d3plot \
    --outdir <ws>/Iter05_d3plot/out --frames 21 \
    --gif assets/fourview_animation.gif --png assets/fourview_last.png
```

硬性要求：
- `<ws>` = `C:\Users\hekie\Documents\HyperWorksMCP\workspace`（bridge 的 `allowed_roots`，输入输出都必须在这里）。
- `--model` / `--result` 传**同一路径**（d3plot 自带网格）。d3plot 文件名没有扩展名，靠 basename 白名单放行。
- **必须过 `check`**：`unique md5 == 截图总数`。只有 1 个 unique 就是视角没生效，
  这份素材不能进报告（排查见 `references/hyperview_postprocess.md` §3）。
- 素材怎么拼、怎么落进 slide、怎么验内嵌 md5，见 `references/ppt_assets.md`。

### 5. 出报告
- 走 `workbuddy-pptx`（slidep CLI），**沿用客户模板主题**（颜色/字体/标题条），不要自创风格；
- 页序按 `references/report_structure.md` 的四段式（概览 / 判据 / 结果 / 结论与下一步）；
- 每页写完立刻 `slidep lint`，全篇写完做边界与图片比例校验（见 `references/ppt_workflow.md` 的校验脚本）。

## 脚本

| 脚本 | 作用 | 依赖 |
| --- | --- | --- |
| `scripts/g14_common.py` | deck 解析、部件名匹配、栅格最近邻、G.3 圆角区域、连通域 | numpy |
| `scripts/g14_mesh_check.py` | 缝线带宽 / 非充气斑 / 覆盖率 / 落点分类 | numpy |
| `scripts/g14_thickness.py` | d3plot 厚度场、点位采样、反求平移、出图 | numpy + lasso-python |
| `scripts/curtain_footprint.py` | `*AIRBAG_REFERENCE_GEOMETRY` 包围盒与头部点同系核对 | numpy |
| `scripts/hw_bridge.py` | 极薄 bridge 转发（看原始返回、调未封装方法） | — |
| `scripts/hv_render.py` | **后处理一体化 CLI**：`status/restart/single/shots/check/gif/anim`，含视角自检与路径安全提示 | Pillow + hyperworks-mcp venv（`live_bridge`） |
| `scripts/make_assessment_region_svg.py` | 由 CoG 生成评估区示意图 SVG | — |
| `scripts/g14_headcurtain_build.py` | 合并 deck：气帘(保留原节点ID)+头型(偏置)→`.key` + `.npz` | numpy |
| `scripts/g14_headcurtain_sections.py` | 平面求交断面 / Y 厚度(±30mm窗) / 头型-气帘 KDTree 间隙 | numpy + scipy |
| `scripts/g14_headcurtain_figs.py` | 4 张进报告图：重叠/四断面/评估区投影/厚度沿轴（离线 matplotlib） | numpy + matplotlib |

## 坑（都是实际踩过的）

1. **占位 inflator 曲线**：`*AIRBAG_LOAD_CURVE_ID` 指向 (0,0)(100,1e−5)(200,1e−5) 这种阶跃常数时，起爆后 2.5 ms 就"展完"，压力列恒为 0（质量流驱动不输出压力）。任何"展开时间/触底时刻"结论都不可用，必须在报告里标注。
2. **H3D 没有厚度场**，但 d3plot 的双层壳可以算出厚度——不要因为 H3D 没有就写"无法测量"。
3. **`slidep` 的 `<Image>` 只写 width 不按真实比例取高**，必须同时写 width + height，否则图被压扁。
4. **坐标系不可硬套**：整车 X 3197–4225 与平铺 IC X 911–3117 不是平移关系，差的是"卷开/贴合"映射；硬加 +200 mm 只会得到 600–1500 mm 的假越界。
5. **缝线节点与腔体共节点**，节点距恒为 0，不能用"节点距×2"当带宽；用元素面积/长边。
6. **别把 IC 厚度当缝线宽度**：厚度是袋鼓起高度，缝线宽度是平面上的不充气带宽度，两个量无关。
7. `binout` 里可能没有 `nodout`，节点历史要靠 d3plot 的 `node_displacement` 自己叠。
8. **HyperWorks 启动参数不完整 = "假成功"**：只给 `-client HyperWorksDesktop` 时进程能起、占 900 MB，
   但端口永不监听（缺 `-plugin HyperworksLauncher -profile HyperworksLauncher -startwith HyperView`，
   Launcher 插件不初始化 → Qt 消息泵不转 → Extension 的 QTimer 不触发）。判断标准只有一个：
   `48761` 是否 LISTENING + `ping` 是否通。
9. **四视角全相同的头号原因是 `GetPageHandle` 写死 1**：Python 新建 Page 通常 id=2 且是 active page，
   写死 1 会去操作空窗口，`SetOrientation` 全部"成功"而截图不变。必须用 Python 侧 `int(page.id)`。
   次因是 Tcl handle 跨调用重名（`already exists` 会中断整条命令链）、以及设完视角又调了 Python `window.draw()`。
10. **d3plot 文件名没有扩展名**（`d3plot` / `d3plot01` / `d3plotaa`），`Path.suffix` 为空，
    纯后缀白名单会拒掉所有真实 d3plot。已在 `handlers.py` 加 basename 白名单。
11. **改 `handlers.py` 必须重启 HyperView**：扩展无热重载，注册表在 `__init__` 一次性绑定。
    另外在受管沙箱的短命令里启动 HyperView 会被整树回收 → 自动化环境用 MCP 的 `launch_hypermesh`。

## 这次报告（2026-11-03）新增的坑

12. **MCP 连不上的根因只有四类**，全部落在 `hyperworks_autostart.md`：
    - **A 进程树回收**：Bash/PowerShell 里 `runhwx &` 或 `hv_render.py restart` 拉起的 hwx 在命令返回即被回收（restart 报 ONLINE 下条命令 10061）。
    - **B 假成功**：启动缺 `-plugin/-profile/-startwith` → 端口永不开。
    - **C 桌面快捷方式手动开**：同样缺那些参数，bridge 端口永不开（"我已经开了你连一下" 失效的根因）。
    - **D `status.json` 滞后**：进程被杀后仍写 online，以 netstat/`get_live_bridge_status` 为准。
    **唯一可靠做法**：先 `get_live_bridge_status`，不连就调 `launch_hypermesh`，再轮询到 `ONLINE`。绝不走 Bash 启动、绝不走桌面快捷方式、绝不读 status.json。
13. **`launch_hypermesh` 是 fire-and-forget**（源码 `subprocess.Popen` 后即返回），端口要 10–20 s 才监听；
    必须在它之后轮询 `get_live_bridge_status` / `hv_render.py status`，看到 `connected=true` 前不要调任何 `live_*` 工具。
14. **头型-气帘离线管线**（见 `head_curtain_evidence.md`）：合并 deck 必须**保留气帘原始节点 ID**（否则不能回 HyperView 叠 H3D）；
    `*PART`/`*SECTION_SHELL` 必须写全三段否则 HV 加载崩；厚度窗宽用 **±30 mm**（±10 会在腔间喉部退化成 0.8 mm 假薄）；
    头型 ID 偏置 10M/20M/30M/40M。结论：形态对照用 HV 渲染，进报告的标注图用离线 matplotlib（配色/尺寸可控）。
15. **四个脚本 import 改名要同步**：`g14_headcurtain_figs.py` 里 `from g14_headcurtain_sections import plane_segments`，
    重命名脚本时这个 import 必须跟着改。

## 变更记录

**2026-11-03（v4）——MCP 自动拉起成体系 + 头型-气帘离线证据管线**
- 新增 `references/hyperworks_autostart.md`：**MCP 连 HyperWorks 为什么会反复失败 + 唯一可靠自动拉起流程**。
  四条根因（进程树回收 / 假成功缺参数 / 桌面快捷方式手动开 / status.json 滞后）逐一讲清，
  给出「`get_live_bridge_status` → `launch_hypermesh` → 轮询到 `ONLINE`」三步法。这是该问题的权威入口。
- `references/hyperworks_bridge.md` 增补：失败模式表新增「点桌面快捷方式手动开 → bridge 永不开」，
  并指向 `hyperworks_autostart.md`。
- 新增 `references/head_curtain_evidence.md` + 三个脚本 `g14_headcurtain_build/sections/figs.py`：
  气帘 deck + HV 末态坐标 + 头型 .key → 合并 deck(保留原 ID) + npz → 断面/厚度/间隙 → 4 张进报告图。
  覆盖 P12–P15（重叠 / 四断面 / 评估区投影 / 厚度沿轴）。
- `SKILL.md`：阅读表与脚本表各加 2/3 行；坑新增 #12–#15（MCP 四类根因、fire-and-forget 轮询、离线管线注意点、改名同步 import）。

**2026-11-02（v3）——后处理能力成体系**
- 新增 `scripts/hv_render.py`：后处理一体化 CLI（`status / restart / single / shots / check / gif / anim`），
  替代原先散落的 `fourview_render/`（已删除）。`restart` 封装了唯一可靠的启动命令，
  `check` 用 md5 唯一性把"视角没生效"挡在报告之外。
- 新增 `references/hyperview_postprocess.md`：d3plot/H3D → 云图 → 四视角的全链路、能力边界、
  两个 bridge 方法的参数与返回、Tcl 相机控制的四个致命细节、故障排查表。
- 新增 `references/ppt_assets.md`：裁白边 / 等比缩放 / 角标 / GIF 参数、slide DSL 落位三规则、
  无截图环境下的 pptx 内嵌 md5 校验、素材页自检清单。
- `references/hyperworks_bridge.md` 重写：给出与 `server.py` 一致的启动命令
  （`-plugin HyperworksLauncher -profile HyperworksLauncher -startwith HyperView`），
  解释三种"裸起"失败模式、重启完整循环、无热重载、`status.json` 不可信。
- `handlers.py` 修 d3plot 白名单（`_is_d3plot_family`，放行无扩展名的 d3plot 家族，
  并放宽 `model_file`）；实测：172 MB / 7 段 d3plot，4 视角 × 6 状态 = 24 张，md5 全不同。
- 实测四视角渲染：G143 H3D，4 视角 × 21 时间步 = 84 张，84 个 md5 全不同，GIF 3.4 MB / 21 帧。

**2026-11-02（v2）**
- 新增 `scripts/g14_common.py`、`g14_mesh_check.py`、`g14_thickness.py`，把一次性分析脚本整理成带参数的 CLI，并在 R676 算例上实测通过（缝线带 4.48 mm / 单排不可分辨、厚度 160 ms 峰值 168.6 mm、反求平移 −1515/−625）。
- 新增 `references/regulation_interpretation.md`（判读理解与六类误读）、`references/cae_measurement.md`（d3plot 读数与三条算法对比）、`references/report_structure.md`（四段式报告骨架与判据—证据对照表）。
- `g143_criteria.md` 补齐图 G.3 尺寸链（82/82/82/52/r82）与图 G.4（594/693、126/147）。
- `ppt_workflow.md` 补 `<Image>` 必须写宽高、边界/比例自检脚本、截图不可用的环境限制。
- `hyperworks_bridge.md` 修正"crash H3D 无厚度场"的推论：H3D 没有，但 d3plot 双层壳可以算。
- 修正缝线带宽算法：节点距恒为 0（共节点）、质心双向距离在曲面上虚高，改用元素面积/长边并加 `rows_across` 单排判定。

**2026-10-31（v1）**
- 首版：法规要点、HyperWorks bridge、四视角渲染、11 页报告模板。
