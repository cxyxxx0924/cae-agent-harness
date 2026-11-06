# 02 · 求解器配置与求解设置

> 气帘是显式动力学（气囊充气），时间步由 **DT2MS 负值**控制，质量缩放门禁 <3%。
> **强行规范**：计算时间由时间步长控制，不是靠 ENDTIM 硬扛（详见 references/06 规范条款）。

## 1. 本机求解器实况（2026-10-16 实测，重要）

- `D:\Program Files\ANSYS Inc\v193\ansys\bin\winx64\` 下 `lsdyna_sp/dp/mpp_sp_msmpi/mpp_dp_msmpi.exe`
  **四个全是 LS-DYNA R10.1.0（rev 123264，2018-01-12 构建）**，并非 v193 应有的 R13.x。
  `LSDYNA.exe` 只是 1.8MB 启动壳。ANSYS 许可可用（能跑出 d3hsp/messag）。MS-MPI 在默认路径。
- **后果：R11 之后新增的关键字本机会被拒**（报 unknown keyword 而非语法错）——用新版教程/模板的卡前先核对关键字年代。
- **LS-PrePost 4.6 已装**：`D:\Program Files\LSTC\LS-PrePost 4.6\lsprepost4.6_x64.exe`
  （同目录有 lsrun/runqueuer/tetgen_64）；`D:\LSTC\LS-DYNA` 是**空目录**（无独立求解器）。
- Altair 2026 无求解器（只有 hmbatch），求解走 ANSYS/LSTC 工具链。

## 2. lspp-mcp 求解（首选，56 工具）

- 包 `lspp-mcp` 0.10.0，venv `~/.workbuddy/binaries/python/envs/lspp-mcp`，
  配置 `E:\work\lspp-mcp-server\config.json` + `~/.workbuddy/mcp.json` 的 `lspp-mcp` 条目。
- **solver_profile 必须显式指定**，否则报 `solver profile not found: ""`：
  - `ansys_smp_sp`：mode=smp, exe=`D:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_sp.exe`, ncpu=4
  - `ansys_mpp_sp`：msmpi + mpiexec
- 调用：`run_lsdyna_solver(deck="...newcab_calc.k", profile="ansys_smp_sp", ncpu=4)`
- 返回 `returncode=0, normal_termination` 即正常终止。
- **坑（本会话实测）**：求解器跑完（46 分钟）后 MCP 服务器会话**掉线**，
  `extract_d3plot_node_history` 三次重试失败 → 被迫 numpy 直读 d3plot（见 references/04）。
  **对策**：长跑任务不要依赖 MCP 后处理；拿到底层 `.k` 和输出文件后直接 numpy 解析。

## 3. 本机直跑（MCP 掉线时兜底）

```bash
cd E:/work/lsdyna-agent/newcab_trial
"D:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_sp.exe" i=newcab_calc.k \
    ncpu=4 memory=2000m 2>&1 | tee solve.log
```
- 输出：`d3hsp` / `messag` / `glstat` / `matsum` / `abstat` / `rbdout` / `spcforc` / `d3plot` + `d3plotNN`。

## 4. 标准卡（规范 6.1，气帘随参考取）

```
*CONTROL_TERMINATION
$ ENDTIM ENDCYC DTMIN ENDENG ENDMAS
  20.0      0    0.0    0.0    0.0
*CONTROL_TIMESTEP
$ DTINIT TSSFAC ISDO TSLIMT DT2MS LCTM ETHR MSTMS
   0.0     0.9    0    0.0   -5.5E-4  0   0.0  1.0
```
- **DT2MS 取负值 = 目标最小时间步长**；步数 ≈ ENDTIM / |DT2MS|。
- **禁止把 DT2MS 置 0 裸跑**（退化成由最坏单元决定，实测 dt 崩到 1.57E-8、算不完）。
- 气帘参考取 `TSSFAC 0.9 / DT2MS -5.5E-4`（标准卡是 0.7 / -7.0E-4，照搬即可）。

## 5. 质量缩放门禁（规范 6.2，★★★）

- 2 步试运行看 `glstat` 的 mass scaling + `matsum` 各部件：
  **质量增加必须 < 3%**；超标部件查网格质量（特征长度太小）与材料 E、ρ。
- 本会话 NEW_CAB 实测：质量增加 **0.0002%**（远低于 3%），最大单单元质量增加 0.866e-6 kg。

## 6. 网格硬条款（规范 2.2，求解前必须确认）

法向一致、每部件无自由边（充气口/外轮廓合法自由边除外）、part 间无初始穿透、
**禁止重复单元与重复节点**、**最小单元尺寸 > 3mm**。
- 症状"时间步长太小"：① 试运行关质量缩放查时间步长信息；② 查材料单位制。

## 7. 输出文件用途速查

| 文件 | 看什么 |
|---|---|
| `d3hsp` | 求解器初始化、单元/节点统计、终止原因 |
| `messag` | 时间步、能量、警告（Reference Geometry / 翘曲角 / 形状 criterion） |
| `glstat` | 总动能/内能/沙漏能/外力功/能量比/质量增加/时间步（健康门禁主源） |
| `matsum` | 各 part 质量 + x/y/z 动量（漂移诊断主源） |
| `abstat` | 气腔体积/压力/气体质量/温度（充气自洽主源） |
| `rbdout` | 刚性体（含 nodal rigid body）位移/速度（固定生效证） |
| `spcforc` | SPC 反力（注意：CNRB+SPC 组合本版本不报反力，见 references/03） |
| `d3plot` + `d3plotNN` | 几何 + 各状态坐标/速度/加速度（逆向见 references/04） |
