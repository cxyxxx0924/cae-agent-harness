# 07 · 全链坑位总索引（网格 → 计算求解）

> 气帘全链路分三个技能维护，坑位编号各自独立。**本文件是总索引**：
> ① 求解阶段坑位（本技能，§A，编号 P-Sxx）；② 跨技能坑位速查表（§B，指向其他两个技能）。

---

## A. 求解阶段坑位（本技能 `气帘计算求解skill`）

### P-S01（★★★）K 单元卡漏写 eid → HM 读死机
- 单元卡写成 `pid,n1,n2,n3,n4` 漏 eid；LS-DYNA 顺序 `eid,pid,n1..n4`。
- 后果：eid 全表重复、n1 被读成 pid → 63058 幽灵 part → 拓扑崩 → HM 死机。
- 见 `references/01`、脚本 `qa_kfile_strict.py`（独立解析，退出码门禁）。

### P-S02（★★★）跨文件 id 引用飞丝（nid ≠ gid）
- 组装写 K 时 gid 重编号，后续装配拿中间 txt 的 nid+坐标当 K 的 gid → 飞丝。
- **铁律**：引用 K 节点的 id+坐标必须从**目标 K 本身**解析；中间 txt 只用于渲染/统计。
- 门禁 `diag_long_edges.py`（XZ>20mm / 3D>30mm 必须为 0）。

### P-S03 K 格式：4 位坐标+6 小数必须自由格式
- 定宽 10 字符会把 `1601.2793` 写错列 → 薄片。只用逗号自由格式或严格 10 字符定宽。
- QA 验证器不许和写入器共享字段假设（翻车主因）。

### P-S04 per-PID 自由边误判 / 先写后剔退化
- 逐 PID 算自由边会把跨 PID 共享边误判为自由；写 K **前**就剔退化（先写后剔=deck 带病）。

### P-S05 求解器是 R10.1.0 不是 R13（v193 壳里是旧版）
- `D:\Program Files\ANSYS Inc\v193\...` 四个 exe 全是 R10.1.0（rev123264）。
- **R11 之后新增关键字会被拒**（unknown keyword 而非语法错）。用新版卡前先核对关键字年代。

### P-S06 solver profile 必须显式指定
- `lspp-mcp` 的 `run_lsdyna_solver` 不填 profile → `solver profile not found: ""`。
- 填 `profile="ansys_smp_sp"`（SMP, lsdyna_sp.exe, ncpu=4）。

### P-S07 DT2MS 必须负值，禁止置 0 裸跑
- 负值 = 目标最小时间步长，步数≈ENDTIM/|DT2MS|；置 0 → 退化成最坏单元决定，dt 崩到 1e-8 算不完。
- 规范 6.1（详见 `references/06`）。

### P-S08 MCP 长跑后掉线，后处理工具不可用
- 求解 46 分钟后 MCP 会话掉线，`extract_d3plot_node_history` 失败。
- **对策**：拿到底层文件后直接 numpy 直读 d3plot（本技能 `d3plot_reader.py`）。

### P-S09（★★★）d3plot 单元连接区必须按 int32 读
- 连接区 @word(64+3N) 是 **int32**（n1..n4+part索引）；按 float32 读 = 1e-41 级小数 → 误判"全零"。
- 整数头字段（NUMNOD@word16 / NUMEL@word31）也用 **int32** 视图取（float32 视图错位成 0.0）。

### P-S10 固定节点判据 = 当前坐标逐位==初始坐标
- 唯一硬判据：d3plot 状态下固定节点 max|Δ|=0.0。
- spcforc 对 CNRB+SPC 组合**不报反力**（全 0、setid=0）→ 别用 spcforc 判固定；用 rbdout 零位移 + d3plot 逐位校验。

### P-S11 参考模型其实没固定拉带
- `Model_update` 零 SPC（仅 1 个拴 2 节点刚性体）；`Model_from_AI_07` 完全无约束。
- 用户"参考模型有固定"印象与 deck 不符；按决策固定即可。

### P-S12 锚点布置导致 z 漂移（非数值问题）
- 主锚全聚右端 x[1600,1771]，拉带固定端在 z≈305/442 两线 → 质心未完全约束 → 持续 +z 净力。
- 要压漂移：补左端锚点 / 拉带端改接布带环。

### P-S13 d3plot 时刻必须 RMS↔KE 标定
- 状态文件头部无直接可读时间；d3plot08 曾被误当 20ms（实为 17ms）。
- 用速度 RMS → KE_est=½Mv² ↔ glstat KE 标定：03≈4.4 / 05≈9.4 / 08≈17 / 09-10≈20 ms。

### P-S14（★★★）整车整合必须清算"验证工装固定点"
- 工作模型里遗留的自起爆+固定点（SPC/CNRB 工装）整合时不删 → 充气初始瞬态即爆。
- cab1 实录：10×BOUNDARY_SPC_SET（9 boss cap 全 6DOF + 900001 散点）+ 10×CNRB；
  参考 5P-BAG/Vehicle/Spring 里 SPC=0、CNRB=0。
- 症状指纹：带拉带 0.081ms 爆 / 无拉带活 / 改缆长同 cycle 同簇节点 → 固定点。
- → `references/08`

### P-S15（★★★）删关键字必须整块删（关键字+数据行）
- 只删关键字行留数据行 → 孤儿数据行 → forrtl severe(64)（BIGRDSECT/GETCNT）段错误级崩溃，
  d3hsp 无任何错误回显。改完必查特征行清零。 → `references/08`

### P-S16 PART 数据行 10 字符定宽，SECID 溢出（10125/10133）
- 10005→1000037 超 10 列界读成 10000；重映射按定宽字段重排，不能字符串替换。 → `references/08`

### P-S17 接触卡必须写满 4 行（含空白 A3 卡）（10246/10450）
- 缺第 4 行 → 解析器吞下一张卡。 → `references/08`

### P-S18 D3PLOT 重复定义先到先得
- include 控制卡已有 D3PLOT，主 deck 再定义无效；改输出间隔要改控制卡副本。 → `references/08`

### P-S19 跨文件 ID 冲突 → 段位偏移 + 七类审计
- 工作气帘与车身共用节点号段（114221 两边都有）→ 合并必撞。
- +30,000,000 偏移实测安全；审计七类：nodes/parts/sections/mats/curves/node-sets/part-sets。 → `references/08`

### P-S20 定宽卡字段替换按列原位映射
- AIRBAG 等空格定宽卡改 ±LCID 引用必须 10 字符字段取出写回；空格重连毁列对齐。 → `references/08`

### P-S21 材料与参考逐字一致 → 丢自己的用参考 MAT.K
- include 内嵌 *KEYWORD/*END 对 *INCLUDE 无害；手工拼接（去 *END 连写）必出伪影。 → `references/08`

### P-S22 EXTRA_NODES_SET 报 20367：锚点已在刚体内
- 锚点节点本就是刚体网格节点时再加焊接卡 → "already contains extra node"；该卡只焊独立节点。 → `references/08`

### P-S23 时间读数陷阱：cycle×dt 交叉验证
- "problem time 8.0681E-02" = 0.081ms，不是 80.7ms；163 循环 × dt=4.95E-4ms。
- mass increase percent ~1E+8 = 单元翻转；"termination time reached" 才是正常。 → `references/08`

### P-S24 dt2ms 钉步速度基线 + 两段式跑法
- 本气帘 dt≈0.5µs（织物曲线刚度）：2ms 探针 8min（n=2，~8.5 cyc/s）、60ms≈4h。
- 先 2ms 探针（死亡点×24）再 60-120ms 长跑；cable 拉带吃质量缩放属正常。 → `references/08`

### P-S25 块级二分定位 forrtl 类崩溃
- 单 include 探针定位肇事文件 → 按关键字切块做 25/50/75/100% 前缀探针定位肇事块。
- 崩溃前三名：孤儿数据行、列宽破坏、全局去逗号。 → `references/08`

### P-S26 换装法归因 + host 接线
- 把工作气帘装进参考 host（03_Control+MAT.K+Vehicle.k+Spring 改接），唯一变量是气帘。
- Vehicle.k 自带袋-身 S2S（slave=SET_PART 2）→ set 2 必须含全部气帘件；
- 排除参考 6P_CAB（AIRBAG_LOAD_CURVE 会双重充气）；拉带袋侧端点最近贪心改接。 → `references/08`

### P-S27 MPP 提交模板与崩溃判读
- `mpiexec -n 2`（n=4 许可拒绝）；LSTC_LICENSE=ansys + ANSYSLMD_LICENSE_FILE=1055@server。
- "ended prematurely exit code 64" = 段错误（查 P-S15/P-S20）；exit 0 + Error 列表 = 优雅报错。 → `references/08`

### P-S28（★★★）拉绳锚点投影：同 X 邻域 + Z 向上，禁全局最近
- 车身侧锚点 = 气帘侧节点沿 Z 向上在车身上的投影。**全局最近邻**会把锚点甩到几百 mm 外的另一块板
  （X 漂移 200~600mm）→ 拉绳强行斜拉 → 巨大接触力 → mass increase。
- 正确：锁 `XTOL≈45mm` 的 X 邻域，先筛 `bz>z`，再按 `(dX, |dY|, -Z)` 选；放宽到 `3*XTOL` 兜底，
  最后才全局兜底（正常不应触发）。 → `references/09`

### P-S29 BIW 文件混入他模型孤立节点（约 33790 个）
- 干净车身 `BIW_clean.k` 的 `*NODE` 常混入气帘孤立节点（ID/坐标与 cab1 完全一致且不被任何壳单元引用）。
- 危害：被全节点 SPC 固定会干扰气帘；Z 向上投影会落到"气帘自己"身上。
- 正确：先收集被车身 `*ELEMENT_SHELL` 真实引用的节点集，只保留被引用节点，其余整行删除。 → `references/09`

### P-S30 重编号与坐标提取的 ID 基准必须一致
- 重编号后集合里存的是 `+30M` ID；取原始坐标要先 `-NOFF` 还原再查坐标表。已重编号又减 NOFF = 错位坐标。
- 统一用 `cab_coord_orig(nid)`（原始 ID → 平移后坐标）；重编号 ID 与原始 ID 打印时一并输出核对。 → `references/09`

### P-S31 平移只改 Y/Z，DY 莫错加到 X
- 节点字段 `nid,x,y,z`，Y 是索引 2。写 `p[2]=y+DY`、`p[3]=z+DZ`；写成 `p[1]=x+DY` 会把气帘整体沿 X 平移。 → `references/09`

### P-S32 节点行索引错位（node_rows ↔ body_lines）
- 剔除混入节点时，行号在 `append` **之后**记录 `(len(body_lines), nid)`；先记录再 append 会命中错行 → 删错/留错。 → `references/09`

### P-S33 SET ID 冲突：车身集用 900101/102/103
- 车身集合避开气帘原有集（900010~900018、10200009 等），防止 `*INCLUDE` 后集合被覆盖/重复定义。 → `references/09`

### P-S34 车身刚体不加全节点 SPC；锚点已在刚体内勿加 EXTRA_NODES_SET
- 参考车身 = `MAT_RIGID` 可动刚体，不做全节点 SPC。锚点若已属同一刚体 part，再加
  `*CONSTRAINED_EXTRA_NODES_SET` → 报 20367 already contains extra node（该卡只焊跨 part 独立节点）。 → `references/08,09`

### P-S35 平移量 DY/DZ 由"参考模型顶部距离差"确定（用户铁律）
- 用户原话"安全DZ可以参考参考模型的顶部距离差，一致即可"。量法：取工作/参考两模型"气帘顶→车身顶"
  节点对距离 p50，令相等解出 DZ（本例参考 +522.0mm、工作 DZ=-270 时 +522.9mm 一致；DY=-615）。
  绝不靠肉眼对齐。 → `references/09`

### P-S36 弹簧/阻尼能量 4.8e4 异常 = 投影缺陷副产物（已定位）
- 早期中间态 2ms 探针 `spring and damper energy ≈ 4.8e4`，参考仅 ~1e-4；但**最终修正版（run_probe7）回落到 `2.0e-20 ≈ 0`**，与参考一致。
- 根因 = 拉绳被错误拉伸：全局最近投影(P-S28 反面) / cap 节点 ID 基准错位(P-S30) / 重复 EXTRA_NODES_SET(P-S34)
  使锚点落错板、拉绳斜拉数百 mm → 弹簧储能爆掉。
- **结论**：该异常是**锚点几何错误的报警**，不是物理设置固有差异；看到它就回查 P-S28/P-S30/P-S34，
  别去调拉绳间距或约束语义（本例拉绳间距 147~380mm 与参考不同，但修正后能量仍≈0，间距非主因）。 → `references/09`

### P-S37 接触用 SINGLE_SURFACE_ID SSID=2，气帘作 slave
- 区别于 P-S26 的 Vehicle.k S2S。照抄参考 main.key：`*CONTACT_AUTOMATIC_SINGLE_SURFACE_ID`，
  `SSID=2` → 气帘零件集（set 2）作 slave 与全场（车身）接触；必须写满 4 行（P-S17）。 → `references/09`

### P-S38 投影质量验收：看 dXY≈0（锚点未横向甩偏），dZ 不必等于参考 tether dZ
- 拉绳近似竖直，记 `dXY=hypot(bx-x,by-y)`、`dZ=bz-z`。本例最终(run_probe7) 10 根全部 `dXY<64mm`（近似竖直、锚点未甩到错板），`dZ∈[+135,+378]mm`（均值≈+225mm）。
- **关键澄清**：dZ 量级由 cap/锚点具体布置决定，**不必等于参考 tether dZ**（参考锚点位置不同）；真正的相对位一致由 P-S35 顶部距离差 +522mm 保证。某根 `dXY>200mm` 或 dZ 为负或锚点落非预期零件 = 投影失败 → 回查 P-S28 层级。 → `references/09`

### P-S39 主 deck ENDTIM=200ms 参考一致，与用户选项 80ms 不同；改 ENDTIM 直接替换控制卡定宽串
- `gen_deck.py` 把 `main.key` 钉成 `ENDTIM=200.0`（注释写明"参考一致"，对应 `Model_update_Move_Iter04` 的 200ms 设定），而用户早期在选项中选过 **80ms**——两者不同，属"完全参考参考模型"的设计取舍，非 bug。
- **要改 ENDTIM**：直接整串替换控制卡里的定宽数（注意前导空格对齐）：
  `     200.0         0       0.0       0.0       0.0` → `      80.0         0       0.0       0.0       0.0`
  不要只改数字不改列宽（定宽卡会被错列解析）。 → `references/09` §10

### P-S40 主跑估时陷阱：先按 dt 估算再投，200ms≈11h 易超预期
- 本例稳定步长 `dt = 4.95e-7 s`（= 4.95E-04 ms，与探针一致，inflation/contact 不显著改变）。
- 估算：`步数 ≈ ENDTIM / dt`；200ms ≈ **40 万步**，`n=2` 实测 40ms 用 **~2h13m**（15:12→17:25）→ 200ms ≈ **11 小时**。
- **用户曾因"时间过长"中断主跑**；故投全量 200ms 前，先用 2ms 探针过健康门禁，再用**截断 ENDTIM（如 80ms，约 4.5h）**看部署中段是否达标，确认无误再全量。 → `references/09` §10

### P-S41（★★★）`*AIRBAG_REFERENCE_GEOMETRY` R10.1 按"4 字段/记录连续流"读取，写 6 字段必炸 Error 30099
- 本机 R10.1.0 解析该卡时每行只认 **4 个字段**（nid, x, y, z），日志满屏 `Warning 10457 (KEY+457) too many items in line only 4 expected`。
- 若照抄参考模型旧版格式写 6 字段（`nid, x, y, z, 0, 0`），解析器把多余字段当作**下一条记录的开头** → 整个节点流错位，
  每个节点坐标被吞/移位 → 膜片单元全部塌陷 → **Initialization 阶段 `Error 30099 (INI+99): element ID xxx has a zero normal vector`** 终止。
- **指纹**：KEY+457 警告 + INI+99 零法向 + 两者都"超过 50 次" → 99% 是该卡字段数不匹配。
- **正确**：严格 4 字段 `nid, x, y, z`；坐标必须与气帘 K 文件 `*NODE`（平移+重编号后）逐点一致。
  注意：`Error 30099` 出现在 RefGeom 引入后才出现且坐标明明一致时，先怀疑**字段数**而非坐标值。 → `references/09` §11

### P-S42 SMP 启动必须显式 `memory=50000000`（默认 20M words 不够）
- 同一 deck MPP 能跑，SMP 默认 memory=20000000 words 报 `Error 70021 (MEM+21): Memory is set 2305067 words short`。
- 启动行加 `memory=50000000 ncpu=2`（本机 4 核、许可证 2，ncpu=2 稳）；OMP_NUM_THREADS=2 同步。
- SMP 优点：**写单个 d3plot**（几何+状态一体），旧 d3plot_reader 直接可读 → 渲染走 SMP 版（见 P-S44）。

### P-S43 后台任务里 `nohup ... &` 会被静默杀掉，solver 必须是后台任务的**前台进程**
- 后台 shell 任务里再 `nohup lsdyna_sp.exe ... &`：launcher 立刻退出（exit 0），内层 solver 随 shell 退出被杀，
  日志只到 "license OK / reading deck" 就断——**无任何报错，极易误判为已启动**。
- **正确**：后台任务里直接前台执行 solver（`lsdyna_sp.exe i=... > log 2>&1`，不加 `&`/nohup），任务存活=solver 存活。
- 启动后 20~90s 内必查：`tasklist | grep lsdyna` 进程在 + 日志推进（echo 卡片/初始化）才算启动成功。

### P-S44 MPP d3plot 主文件只含单 domain 几何，SMP 版 reader 渲染必越界 → 渲染用 SMP 跑
- MPP（mpiexec -n 2）的 `d3plot` 主文件只有 1 个 domain 的节点（本例 126707），状态文件 `d3plotNN` 用**全局节点号**（最大 231681）
  → 按 SMP 单文件逆向的 `d3plot_reader.py` 会 `IndexError: index 231681 out of bounds for size 126707`。
- **对策（本技能取舍）**：要渲染就**另跑一个 SMP 验证版**（同 deck、ENDTIM 截断、memory=50000000，P-S42），
  SMP 单文件 d3plot 直接可读；不做 MPP 节点 ID 映射（工程上不划算）。SMP 与 MPP 结果一致性由同 deck 保证。

### P-S45 `*DATABASE_EXTENT_BINARY` 输出开关会破坏定长偏移读取 → 渲染专用控制卡全关
- STRFLG/SIGFLG/EPSFLG/RLTFLG/ENGFLG=1 时，每个状态帧在坐标/速度之后**追加单元级数据块**，
  帧长不再等于 `140+9N`（向上取整）→ 定长 stride 扫描失效。
- **对策**：复制控制卡做**渲染专用版**（`*_rd.k`），把 5 个输出 flag 置 0（纯输出开关，物理零差异），配 `main_rd.key` 使用。
- 同理 `*DATABASE_BINARY_D3PLOT` DT=2.5ms 输出间隔，前 27ms ≈ 11 帧，够看部署过程。

### P-S46 git-bash heredoc 里的 Windows python 不认 `/e/...` POSIX 路径
- `python - <<'EOF'` 中 `open("/e/work/...")` 报 FileNotFoundError，但 `ls` 同路径正常——POSIX 路径只有 bash 工具认识。
- **正确**：python 内一律用 Windows 风格 `E:/work/...`（正斜杠 Windows API 也接受）；ls/cp 等 bash 命令用 `/e/...`。

### P-S47 `*LOAD_BODY_Z` 第 1 字段是曲线 ID（LCID），不是零件集号
- 把气帘零件集号 9001 填进第 1 字段 → R10.1 当 LCID → `Error 10141 (KEY+141) Load curve id 9001 is undefined`；改字段序 `1 0.0098 9001` 也错（第 3 字段同样被当曲线）。
- **正确**：完全照抄已验证参考写法 `1    0.0098    0`（LCID=1 已定义曲线、SF=0.0098、SID=0 全模型）。改卡前先 grep 参考 K 文件里同卡的原值，不要按手册记忆重构字段序。
- 附：模型时间单位是 ms（dt≈5e-4、ENDTIM=200、d3plot DT=2.5），别把 glstat 的 t 值当秒（口诀 9 的"判时间用 cycle×dt"同理适用于 glstat 块）。

### P-S48 气帘腔体 part 必须留在接触集内，剔除=可见抖动（matsum 定位法）
- 症状：上拉段（点爆前）气帘网格肉眼可见抖动，但全局健康（added mass<1%、KE 单调衰减、车身刚体纹丝不动）。
- **定位法（三步锁定）**：① matsum 末块按 part 分解 kinen → 动能集中在腔体 part（实测占 83%）= 它在独立拍打；② 对照参考模型同卡 → 参考单面接触集**包含**腔体；③ 查本方生成器 → 曾以"腔体壳与织物同位初始穿透→质量暴增"为由剔除。
- **根因**：剔除后腔体层无任何接触约束，在织物层间自由拍动。当初的担忧不成立——`*CONTROL_CONTACT IGNORE=1`（初始穿透忽略，参考同值）已使同位初始穿透安全。
- **修复**：接触集恢复为全部气帘零件（含腔体）；实测同 t=2ms 全局动能 35.3→18.5（近乎减半），探针 added mass 仍 0.04%。
- 通用教训：**"某 part 抖"先查它在不在接触集里**；剔零件出接触集必须给出"参考模型也不含它"的依据，否则一律跟参考。

### P-S49（★★★ 方法论）"完全参考参考模型"= 卡片参数不可动，要动只能动"模型条件"
- 用户硬约束："我要的就是所有设置跟参考模型完全一样"。抖动时把 `C` 从 0.2 压到 0.010 属**遮症状**——
  症状消失但 deck 与参考不再可比，后续结论全部失去基准（本次被用户当面否决）。
- **正确顺序**：① 逐卡 diff 证明抄对了（`parity_audit.py`）→ ② 抄对了为何行为不同（模型条件差异）→
  ③ 哪条物理约束被破坏 → ④ 改什么能恢复约束而**不动参考参数**（本案：补节点质量）。
- **判据**：任何"改参考值让症状消失"的方案，必须先证明"参考值在本模型物理不可用"，并给出不动参数的替代解。 → `references/10` §1

### P-S50（★★★）`MAT_DAMPER_VISCOUS` 显式失稳 `C < 2m/dt`（抖动根因判据）
- 拉带锚点是纯网格节点，质量 `24.4~42.4 g`；`dt=4.95E-4 ms` → `C_crit = 2m/dt = 0.098~0.171`；
  参考 `C=0.2` **刚跨过临界 1.2~2 倍** → 每步速度过冲 → 数值注入能量 → 上拉段肉眼抖动，而 glstat 全局"健康"。
- **阈值实证**：同 deck 只改 C，KE 峰值 `0.2→572（爆）` / `0.10→1.1E-04（健康）`，跨 5 个数量级 ——
  断层式响应 = 显式失稳指纹（不是"阻尼大小的平缓影响"）。算出的临界带 0.098~0.171 正好覆盖 0.1~0.2。
- **定位捷径**：内能分解——`spring and damper` 占内能 **99.3%** 时，嫌疑人直接从"整个模型"缩到"那 10 个阻尼器"。
- **跑之前就能算**：`scripts/damper_mass_gate.py`（门禁 S6，早于 3ms 试算）。 → `references/10` §2

### P-S51（解法）不改参考卡，用 `*ELEMENT_MASS` 把锚点补到 120 g
- 在 `Spring_swap.k` 末尾追加 10 条 `*ELEMENT_MASS`，`mass = target - 现有`（增量，不是总质量），
  `ANCHOR_MASS_TARGET = 1.2E-4` tonne（**120 g**）→ `C_crit=0.48`，裕度 2.4 倍；总加质量 ≈1.1 kg（added mass 0.023%）。
- 效果：3ms 最大 KE `572 → 5.70E-03`（参考 1.16E-02 的 0.49 倍）；首帧抖动 `46.6mm → 1.3mm`。
- 方案对比：B 降 C=0.010（否决，破坏可比性）/ C 换 `MAT_DAMPER_NONLINEAR_VISCOUS`（否决，换类型）/ A 补质量（采用）。 → `references/10` §3

### P-S52（★）`*ELEMENT_MASS` 用逗号格式，8+8 定宽会粘连
- 定宽 `%8d%8d%8.5E`：`nid=30112068` 正好占满 8 位，与 eid 直接拼成 16 位数字 → 读错。
- 正确：`%d,%d,%.5E` 逗号自由格式（与 P-S03 同源）。

### P-S53（★）气囊卡整块照抄，不在生成器里重映射曲线 ID
- 解析参考 `*AIRBAG_*` 再替换 LCID 会引入撞号/定宽错列/混用 `*AIRBAG_LOAD_CURVE` 与 `*AIRBAG_HYBRID` 的风险。
- 改为常量整块搬 `*AIRBAG_LOAD_CURVE_ID`（SID=1 气帘、RBID=3、LCID=21；曲线 21 = `0→0, 100→1E-5, 200→1E-5 MPa` 全程近零压，
  压力由 CV 气体驱动不由曲线驱动）。重映射只在 ID 必然冲突（跨模型合并）时才做，且定宽原位替换（P-S20）。

### P-S54（工具化）全卡 diff 审计 + 已知等价差异清单
- `scripts/parity_audit.py --ours main.key --ref <REF>/main.key --skip-bulk --diff-only`：
  自动展开 `*INCLUDE`、`*XXX_TITLE` 规范化、ID 类卡按 ID 配对（曲线 30M 段用 `--id-map DEFINE_CURVE:30000000`）。
- **必过**：设置类卡片全 MATCH；有意偏离用 `--ack "KEYWORD:field=N|key=id:N|*"` 逐条登记并写理由。
- **已知等价差异**：接触 `SSID`（只是零件集号）/ `SPR=MPR=1` vs 0 / 我方多写接触第 4-5 行全零（P-S17 要求写满）；
  唯一**有意物理偏离** = `*DATABASE_BINARY_D3DUMP` 间隔 500000→25000（缩短重启间隔，便于诊断）。
- **审计范围 = 气帘件 + 全局控制/接触/载荷/传感/气囊**；车身自带的 `SECTION_SHELL`/`MAT_RIGID` 用 `--ignore` 排除
  （参考的车身来自 Vehicle.k，本来就不是同一套网格）。 → `references/10` §6

### P-S55（★）质量缩放读数是百分比：`2.29E-02` = 0.023%，不是 2.30%
- glstat 的 added mass 已经是百分数；门禁 3% 对应 `3.0E+00`。`2.29E-02` 读成 2.3% 会误判"逼近门禁"。
- 同一日志里既有绝对质量（tonne）又有百分比，读之前先确认这行是哪个。

### P-S56（OPEN 未结案）点爆瞬间 external work +370 kJ 与 abstat 1E-5 MPa 差 6 个数量级
- 200ms 算例 `t=100→110ms` external work `-1.5→+370 kJ`，按 `W=p·ΔV` 反算 ≈9.7 MPa，而 abstat 打印 `1E-5 MPa`；
  同期体积 `8→45→50 L`（CV 充气正常）。
- **已排除**：接触力 / 沙漏(0) / 重力(量级差 3 个数量级) / 气囊卡抄错 / 曲线 21 抄错 / part set 指错（6 项）。
- **待验证**：从 `d3dump08`（t≈99ms）重启 4ms，三组对照（原样 / 删 `*AIRBAG_*` / 曲线置 0）。
  若删气囊后跳变消失 → 属 CV/LOAD_CURVE 交互实现细节，报告注明"external work 含充气器做功，不可与 p·V 直接对账"。
- **纪律**：写报告必须如实标注该疑点，不能因为"曲线与参考一致"就默认无问题。 → `references/10` §8

### P-S57（★）节点质量估算必须用 `SECTION_SHELL` 的 T1，不能用裸布厚度
- 用 0.3mm（裸布）估 → `6.7~12.7 g`，比真值小 3 倍（section T1=1.0mm 含涂层等效厚度）。
- 后果不是结论错（都判 FAIL），而是**裕度算错**：0.3mm 得 `C_crit=0.027~0.051`（看似超 4~7 倍，容易误判成别的问题）；
  1.0mm 得 `0.098~0.171`（实际超 1.2~2 倍，与"C=0.1 健康 / 0.2 爆"实测严丝合缝）。
- 铁律：动力学质量/面密度一律用 section 厚度；`damper_mass_gate.py` 已按此实现。

---

## B. 跨技能坑位速查（指向其他两个技能，避免重复维护）

| 阶段 | 技能 | 坑位范围 | 主题 |
|---|---|---|---|
| 原始 IGES → 四分区 | `气帘iges分区skill` | P35–P55 | IGS 导入 1 comp、切线搭接、人工种子分类、delta 累积、渲染人眼复核、t08 假 PASS（漏 WORKDIR）、白线≠垃圾、小圆圈剔除 |
| 曲线 → 面 → 网格 → K | `hypermesh2026_CURVEtoMESH_skill` | P21–P47 | 2026 模板加载、建实体数据名、版本不等价、裁切拓扑、composite 裁不动、eid 漏写(P39)、退化四边形(P40)、2026 无 translator(P41)、交付门禁(P42)、飞丝(P29)、washer/短边、拉带 1-to-1 贪心/去重/单边连接、几何匹配自检(P43–P47)、hmbatch 写盘前 `file delete -force`、顺滑追链法 |

> 三个技能各自维护自己的 P 编号；换项目时按阶段查对应技能，不要在项目里另写一份。

---

## C. 一句话避坑口诀

1. K 格式只用自由格式；QA 比写入器更严。
2. id 引用从目标 K 解析，不信中间 txt。
3. 求解器是 R10.1，R11+ 关键字会拒；DT2MS 负值，profile 必填。
4. d3plot 连接区 / 头整数按 int32 读。
5. 固定节点用"坐标逐位==初始"验证，不信 spcforc。
6. MCP 掉线就 numpy 直读，时刻用 RMS↔KE 标定。
7. 漂移先看锚点布置，不是先怀疑数值。
8. **整合先清算验证工装（SPC/CNRB 全删，boss 自由+缆锚定）；删关键字必须整块删。**
9. **跨文件合并先过七类 ID 审计，重编号用段位偏移；判时间用 cycle×dt，别把 E-02 当 ms。**
10. **forrtl 64 / 段错误 = 先查孤儿数据行、列宽、去逗号；块级二分两轮定位到行。**
11. **从零组合两干净模型时：平移量用"顶部距离差一致"回算（P-S35），别肉眼对齐。**
12. **拉绳锚点投影先锁 X 邻域再 Z 向上（P-S28），全局最近点会把锚点甩偏 200~600mm 致 mass increase；验收看 dXY≈0 锚点未甩偏（P-S38），dZ 不必等于参考 tether dZ。**
13. **车身文件会混入他模型孤立节点（P-S29），只留被壳单元引用的节点；重编号与坐标提取的 ID 基准必须一致（P-S30），平移只改 Y/Z（P-S31）。**
14. **主 deck ENDTIM 按参考一致=200ms，可能与用户选项(如80ms)不同（P-S39）；改 ENDTIM 整串替换定宽数；主跑前先按 dt 估时（P-S40），200ms≈11h 易超预期，先用探针+截断 ENDTIM 验证。**
15. **RefGeom 在 R10.1 上严格 4 字段/行（P-S41），6 字段=解析错位→Error 30099 零法向；SMP 启动 memory=50000000（P-S42）；后台任务里 solver 做前台进程别 nohup &（P-S43）；要渲染用 SMP 跑（P-S44），渲染控制卡关 EXTENT_BINARY 输出 flag（P-S45）。**
16. **LOAD_BODY_Z 第 1 字段=LCID，照抄参考 `1 0.0098 0`（P-S47）；改卡前先 grep 参考同卡原值，别按手册记忆重构。**
17. **"某 part 抖"先查它在不在接触集里（P-S48）：matsum 末块按 part 分解 kinen 定位拍打件，再对照参考集；腔体必须在接触集内，IGNORE=1 使同位初始穿透安全。**
18. **抖动先算 C（P-S50/P-S57）：`C_crit = 2m/dt`，锚点质量按 `SECTION_SHELL` 厚度算；跑之前用 `damper_mass_gate.py` 判，别用 3ms 试算去发现。**
19. **"完全参考"= 卡片一个数不动（P-S49）；改 C 让它不抖属遮症状，一律否决；要动只动模型条件（补锚点质量 P-S51）。**
20. **全卡 diff 交给 `parity_audit.py`，等价差异逐条 `--ack` 登记理由（P-S54）；允许的物理偏离只能有一条且写清（本例仅 D3DUMP 间隔）。**
21. **质量用 section 厚度估（P-S57，0.3mm 裸布会低 3 倍）；added mass 是百分数，`2.29E-02` = 0.023%（P-S55）。**
22. **气囊卡整块搬不重映射（P-S53）；`*ELEMENT_MASS` 用逗号格式（P-S52）；200ms 实测 13h01m/404041 步（P-S40 估时按 13h 报）。**
23. **`*ELEMENT_BEAM`/`*ELEMENT_DISCRETE` 只认定宽（8 字符/80 列），逗号会被去逗号后按 10 字符重切 → Error 10246（P-S58）；同一 deck 里 `ELEMENT_MASS` 反而必须逗号（P-S52），三种格式并存是正常的。**
24. **从参考文件尾部 append 前先剥 `*END`（P-S59），否则追加的 MAT/SECTION 全部被截断 → Error 10304 "MATERIAL ID does not exist"。**
25. **全刚体模型无变形单元 → dt 无上界（5.5E-4 涨到 4.8E-1），独立车身试算只是烟测；判 dt 要在含气帘的组合模型里看（P-S60）。**
26. **include 里可以有 `*END`，但绝不能有 `*CONTROL_*`（后者覆盖前者，ENDTIM 会被试算文件改掉）；独立可跑件与被 include 的网格件要分两份（P-S61）。**
27. **上升段"不抖"用两个数量化验收：10 个拉带锚点 Z 位移相互散差 + 反向步数（P-S62）；本次 2 ms 散差 10.3 μm、反向步数 0。**
28. **`parity_audit.py --ack` 是 append 型，必须重复写 `--ack`，逗号拼接只算一个 key（P-S63）。**
29. **MPP d3plot 是逐状态分文件但几何只含单 domain，自写读取器会挂；节点历史走 MCP `extract_d3plot_node_history`，且不能并发（P-S64）。**
30. **`k_health_gate.py` 的 `(IE+KE)/EW` 会漏掉 `sliding interface energy`（独立累加项），接触一做功就 FAIL；真判据是 glstat 自带的 `total energy / initial energy`（P-S65）。**
31. **先定单位制：本参考模型是 mm-kg-ms（应力 GPa、能量 J），`1.0E-5` GPa 只有 0.1 bar，别按 tonne 读成 100 bar（P-S66）。**
32. **`*AIRBAG_LOAD_CURVE_ID` 是压力曲线袋（无气体 CV、无质量流），起爆由 `*SENSOR_SWITCH` 控；后处理看 abstat 的 pressure/volume 即可（P-S67）。**
33. **拉带锚点必须取"凸台顶面"，取根部会让绳子跨过凸台 → 凸台翻卷、气帘扭转成螺旋（P-S68）。**
34. **绳长有 95 mm 硬下限：更短会让 cable beam 的 natural dt 掉到 |DT2MS| 以下，触发质量缩放把节点质量放大到 1E+05 kg（P-S69/P-S73）。只 `grep "largest mass increase"` 为空还不够，要看 glstat 的 added mass。**
35. **`MAT_CABLE_DISCRETE_BEAM` 是 E=0 的恒力索（只有 0.4 N 预张力），`1.E10` 是"预张力终止时间"不是模量；调刚度改 E 完全无效（P-S71）。卡片含义只信 d3hsp 回显。**
36. **真实节点质量要用 part 总质量 ÷ 节点数反算（0.0075 g），不要按单元面积手算（旧记录写的 24~42 g 大了 3000 倍）；C=0.2 vs C_crit=0.030 超临界 6.6 倍 → 每点补 1 g 即把裕度拉到 20 倍（P-S74）。**
37. **绳系统数值失稳的 30 秒定位：glstat 里 spring&damper energy 从 1E-5 跳到 1E+5 J、added mass >1 kg、dt 被钳到 4.95E-4，三条同现就是它（P-S75）。**
38. **无人值守必备两件套：watch_run.py（dt/质量/停滞/能量看门狗，触发即 kill）+ check_tethers.py（lasso 直读 d3plot 判锚点同步性），二者都不依赖 LS-PrePost 或 MCP（P-S76）。**
39. **lasso 读 MPP d3plot 的 `node_displacement` 给的是"当前坐标"，必须减 state0 才是位移（P-S76）。**
40. **判"能量异常"之前必须把参考模型同刻跑一遍做对照；SPR≈0.025·t³ 是这套绳-阻尼器的固有特征，不是失稳（P-S78~/13.1）。**
41. **`*MAT_RIGID` 的 `CMO CON1 CON2 = 1.0 7. 7.` 等于把刚体钉死；`*LOAD_BODY_Z` 只推得动气帘，车身是墙（P-S78）。**
42. **`MAT_CABLE_DISCRETE_BEAM` E=0 + F0 是恒力绞盘，不会"拉直就停"；车身固定时气帘会被无休止收上去（P-S79）。**
43. **MPP 启动写 `ncpu=2`；写 `n=2` 会生成名为 "2" 的目录并 Signal 11 段错误（P-S81）。**
44. **解析 `*ELEMENT_SHELL` 自由格式要取 `s[2:6]`（s[1] 是 pid），取 `s[1:5]` 会静默丢光所有单元、且不报错（P-S82）。**
45. **参考模型 10 根拉带绳里 7 根连的是不存在的 node 1~7，别照抄；全部连真实凸台顶面节点（P-S83）。**
46. **`*AIRBAG_REFERENCE_GEOMETRY` 记录数必须 = 气帘节点数，少一条那条节点就没参考坐标，气帘越吹越小（P-S84）。**
47. **锚点要取拉带凸台的【顶面】不是根部**：凸台高 147mm，取根部会让绳斜飞跨过整个凸台，凸台自由翻卷、气帘扭成螺旋，肉眼表现就是"只有充气口和右边在拉伸"（P-S68、`references/11 §1`）。
48. **绳长硬下限 95mm**：cable beam 的自然 dt ≈ L/c，L=81mm 时低于 `|DT2MS|=5.5E-4` → 求解器把节点质量缩放到 1E+05 kg → 0.05ms 就 Error。投影取点必须 `if dz < MIN_ROPE: continue`（P-S73）。
49. **`C_crit=2m/dt` 里的 m 必须用 part 总质量 ÷ 节点数反算**（实测 0.0075 g）。按单元面积手算会大 3000 倍，写成"补 24~42 g"是错的；正解是每点固定补 **1 g**（P-S50/P-S74）。
50. **判"拉带不同步"绝对不能用锚点彼此的 dZ 散差**：各绳长度不同（96~428mm），每根升到自己的绳长就锁死，末态散差天然 177mm 却完全正常。正解是算 **dZ/L**（本轮 9/10 精确 =1.000）+ 在"全未绷紧窗口"内比拟合斜率（P-S86/P-S87、`references/12 §4`）。
51. **看门狗本身必须被验证**：`check_tethers` 调用漏传 `--json` 会让看门狗一直读陈旧文件，本轮连续 40 分钟报 `t=5.0ms 太早不判`，而算例已到 104ms。每次重启监控后核对 `monitor.log` 里的 t 与 `main.log` 是否一致（P-S85、`references/12 §6`）。
52. **`*NODE` 的定宽是 I8+3E16（坐标各占 16 字符），`*ELEMENT_*` 是 I8**。两者混用会把 2010.092155 拆成 "20"+"10092155"，参考模型只解析出 1 根绳且包络全错（P-S88）。
53. **同一对节点常被 `*ELEMENT_BEAM` 和 `*ELEMENT_DISCRETE` 各定义一次**（参考模型做法，同时给弹性+阻尼）。解析必须按 (n1,n2) 节点对去重，否则 10 根数成 20 根，速度/散差统计全部翻倍失真（P-S89）。
54. **拿别人的 glstat 当标尺前先 `grep INCLUDE`**：`ref-Output/Model_update` 的 main.key 只含气帘、不含 Vehicle/Spring，它的 `spring_and_damper_energy` 恒为 6.4E-19 —— 误以为"参考的阻尼器是死的"，会推出完全错误的结论（P-S90、`references/11 §6`）。
55. **交付前必看一个数：所有锚点的末态 `dZ/L` 是否全 = 1.000**。这是这套"恒力索 + 固定车身"构造最强的正确性证据（拉直到几何长度后锁死，无超伸、无穿绳）。9/10 精确 1.000 即通过（P-S91）。
