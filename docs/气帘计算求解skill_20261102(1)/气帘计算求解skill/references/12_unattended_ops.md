# 12 无人值守作业规范（长时算例的"边算边判、错了立刻重开"）

> 场景：单机 4 逻辑核、200 ms 算例要跑 13 小时。
> 用户原话：「等算完后再看已经时间都浪费了」、「发现异常随时就要重启，这是无人值守的能力」。
>
> 本文给出三层监控 + 判据表 + 重启决策树 + 阈值标定法 + 误报清单。
> 脚本：`scripts/watch_run.py`（进程级）、`scripts/check_tethers.py`（几何级）、`scripts/plot_d3plot.py`（视觉级）。

---

## 1. 为什么必须有：一次真实的时间损失

| 事故 | 如果等算完 | 实际（有监控） |
|---|---|---|
| 质量缩放 19%（绳太短） | 13 小时后才发现，全废 | **启动 1 分钟内**被抓，损失 1 分钟 |
| 拉带锚点取错（凸台根部） | 13 小时后看到气帘扭成螺旋 | 2 ms 形态图即识破，损失 40 分钟 |
| 看门狗自身失效（漏传 `--json`） | 以为在监控，其实 40 分钟没体检 | 靠日志里 `t=5.0ms` 与实际 104 ms 不符被抓 |

**教训**：无人值守 ≠ 挂个脚本就完事。**看门狗本身也要被验证**（见 §6）。

---

## 2. 三层监控

```
┌─ L1 进程级  watch_run.py      每 60 s 读 glstat + main.log
│    · 数值健康：dt / 质量缩放 / 能量 / 沙漏 / 停滞
│    · 触发即 taskkill /F /T /PID（整棵 mpiexec+lsdyna 进程树）并写 ALERT.txt
│
├─ L2 几何级  check_tethers.py   每 20 次轮询（≈20 min）读 d3plot
│    · 拉带是否平行上移 / 是否超伸 / 是否拍打
│    · 判据全部相对"各自绳长"，不看彼此散差
│
└─ L3 视觉级  plot_d3plot.py + plot_anchors.py  人工/定时抽查
     · 前期（2 ms 内）出形态图，肉眼确认没有扭转、绳没穿布
     · 上升段中期出一次，点爆后再出一次
```

启动方式（三个都要，缺一个就是盲区）：

```sh
# L1+L2 一起（watch_run 内部会调 check_tethers）
python scripts/watch_run.py <deck_dir> main.log --interval 60 --stall-min 45

# L3 抽查
python scripts/plot_d3plot.py <deck_dir>/d3plot <out_img_dir> --views=xz
python scripts/plot_anchors.py <deck_dir> <out_img_dir>     # 初始几何 + 绳线
```

---

## 3. L1 判据表（`watch_run.py`）

| 编号 | 判据 | 阈值 | 级别 | 说明 |
|---|---|---|---|---|
| T1 | dt 崩塌 | 最近 6 帧 dt 全 < 1.5E-4 | FATAL | 正常 4.95E-4 / 6.45E-4 |
| T2 | 质量缩放失控 | added mass / total > 3% | FATAL | 0.01% 级正常；19% 是绳太短 |
| T3 | 求解报错 | `*** Error` / `negative volume` | FATAL | 见 log 尾部 |
| T4 | 停滞 | t 连续 45 min 不动 | FATAL | 卡在 I/O 或死锁 |
| T5 | 能量爆炸 | KE > 10 × max(EW, 100 J) | FATAL | |
| T6 | 沙漏失控 | HG / IE > 10% | FATAL | |
| T9 | 绳能量跑带 | `SPR > 20 × 0.025·t³`（t in ms） | FATAL | **参考模型标定带**，见 §5 |
| T7 | 垂直速度反向 | vz 由正转负且跌幅 > 峰 60% | WARN | 拍打征兆 |
| T8 | 锚点不同步 | 10 锚点 Z 散差 > 5% 行程 | FATAL | 优先用 L2 的 J2 |

> `T9` 是本轮新增的。没有它，`SPR` 从 2E-5 涨到 1.95 J 的过程完全不会触发任何告警
> ——但也**不能**用绝对阈值报警（否则天天误报，见 §5）。

---

## 4. L2 判据表（`check_tethers.py`）

### 4.1 先明确正确的物理图像（**这是本轮最大的认知修正**）

拉绳是 `MAT_CABLE_DISCRETE_BEAM`（E=0、F0=0.4 N）的**恒力绞盘**。
车身固定。所以每个锚点的运动是：

```
t=0 ────────► 以 ~2 mm/ms 匀速上升 ────────► 到达 dZ = L（自己的绳长）→ 锁死不动
```

**各绳长度不同（96 ~ 428 mm），末态 dZ 天然差几十上百毫米。**
本轮实测末态散差 177 mm，但 `dZ/L` 全部 = 1.000 → **完全正确**。

### 4.2 判据（全部相对各自绳长）

| 编号 | 判据 | 阈值 | 级别 | 物理含义 |
|---|---|---|---|---|
| J1 | 超伸 | `dZ_i − L_i > 5% L_i` | FAIL | 绳被拉长 / 穿绳 / 锚点取错 |
| J2 | 同步 | 未绷紧窗口内速度偏差 > 25% WARN / > 50% FAIL | 见左 | 是否平行上移 |
| J3 | 拍打 | 窗口内偏离线性趋势 > 3 mm | WARN | 抖动 |
| J4 | 漂移 | `dXY > max(10 mm, 5% 行程)` | WARN | 被斜拉；点爆后鼓包推凸台属正常 |
| J5 | 回落 | 单调性回撤 > 2 mm | WARN | 绷紧超调（6~9 mm 属正常） |
| J6 | 锁死 | 到 0.98L 后波动 < 0.5 mm | OK | **正常现象，不要当故障** |

### 4.3 J2 的窗口怎么取（关键实现细节）

不能把"已锁死"和"还在上升"的锚点放在一起比速度——必然 100% 散差。

```python
# 窗口上限 = 第一个锚点达到 0.5*L 的时刻（此前所有绳都还没绷紧）
t_lim = min(TT[np.where(DZ[:, i] >= 0.5 * L[i])[0][0]] for i in range(n))
win = TT <= t_lim
v = np.polyfit(TT[win], DZ[win, :], 1)[0]     # 每根锚点的斜率 mm/ms
dev = np.abs(v - np.median(v)) / np.median(v)
```

用**线性拟合斜率**而不是逐帧差分：差分受单帧噪声影响，拟合稳定得多。

### 4.4 输出契约
```json
{"verdict": "PASS|WARN|FAIL",
 "fails": ["J2 不同步 ..."], "warns": ["J3 疑似拍打 ..."], "oks": [...],
 "t": [...], "dz": [[...]], "dxy": [[...]], "L": [...], "names": [...]}
```

`watch_run.py` 读 `verdict` 决定是否 kill。**旧格式（纯 list）仍兼容**。

---

## 5. 阈值必须用参考模型标定（否则天天误报）

### 做法
```sh
mkdir ref5 && cp <参考 deck 全部文件> ref5/
# 只改两处：ENDTIM 200 -> 5.0 ；*DATABASE_BINARY_D3PLOT 2.5 -> 0.25
lsdyna_mpp_sp_msmpi.exe i=main.key ncpu=2 memory=200000000   # 注意 ncpu=，不是 n=
```

### 标定结果（本轮）
| t (ms) | 本模型 SPR | 参考 SPR | 偏差 |
|---|---|---|---|
| 0.4 | 1.609E-03 | 1.529E-03 | 5.2% |
| 0.8 | 1.308E-02 | 1.277E-02 | **2.4%** |
| 1.2 | 4.432E-02 | 4.301E-02 | 3.1% |

→ 拟合出 `SPR ≈ 0.025·t³`（J，t in ms），取 20 倍作为告警上限。

### ⚠️ 标定前必须确认参考算例包含同一套构造
```sh
grep -n "INCLUDE" ref-Output/Model_update/main.key
# 本轮踩过：该算例只 include 气帘，不含 Vehicle.k / Spring_move.k，
# 它的 spring_and_damper_energy 恒为 6.4E-19 —— 拿它当标尺会推出完全错误的结论。
```

---

## 6. 看门狗自身的三个失效模式（必须防）

| 失效 | 表现 | 防法 |
|---|---|---|
| **漏传 `--json`** | 一直读上次的旧 json，报"太早不判"报了 40 分钟 | 显式传 `--json`，跑前删旧文件，跑后校验 mtime |
| **阈值过严** | 上升初期行程 2 mm 就判散差超限，误 kill 正常算例 | 加绝对容差（0.5 mm）；行程 < 30 mm 只记不判 |
| **判据本身错** | 用"彼此散差"判不同步，177 mm 假 FAIL | 改用绳长归一化 dZ/L + 上升窗口内比斜率 |

自查方法（每次重启监控后做一次）：
```sh
tail -5 <deck>/monitor.log          # 时间戳里的 t 是否跟 main.log 的一致？
```
如果不一致 → json 陈旧 → 监控等于没开。

---

## 7. 重启决策树（发现异常时改什么）

```
FATAL 触发
├─ T2 质量缩放 > 3%
│   └─ 查最短绳长。L < 95 mm → 提高 MIN_ROPE，往 Z 更高处重投影（P-S73）
├─ T1 dt 崩塌
│   └─ 同上；另查是否有 <1 mm 的退化单元（网格阶段遗留）
├─ T9 SPR 跑带（> 20×0.025t³）
│   └─ 算 C_crit = 2m/dt。C > C_crit → 补锚点质量（P-S50/P-S74，每次 1 g）
├─ J1 超伸 > 5%L
│   └─ 锚点取错位置（取到凸台根部/布带中部）→ 重取顶面（P-S68）
├─ J2 不同步 > 50%
│   └─ 判据窗口取错（把锁死点算进来）→ 先修判据，再谈模型
├─ T3 报错 / T4 停滞
│   └─ 看 log 尾部；停滞多为 I/O 或许可掉线
└─ J3/J4/J5 仅 WARN
    └─ 出形态图肉眼确认。抖动幅度 < 10 mm 且不扩散 → 可继续跑，记录在案
```

**原则**：只有 FATAL 才 kill。WARN 一律先出图确认，避免"判据过敏"把好算例杀掉重来。

---

## 8. 参数与命令速查

```sh
# 无人值守主命令
python scripts/watch_run.py E:/work/.../s5_final main.log --interval 60 --stall-min 45

# 手动体检（全帧）
<lasso-python> scripts/check_tethers.py E:/work/.../s5_final/d3plot \
               --json E:/work/.../s5_final/tether_sync.json

# 形态图
python scripts/plot_d3plot.py <d3plot> <img_dir> --views=xz

# 若 ALERT.txt 出现
cat <deck>/ALERT.txt          # 含触发时刻、判据、当时的 t
tail -30 <deck>/monitor.log   # 触发前的趋势
```

`watch_run.py` 退出码：`0` 正常结束/被监视终止，`1` 触发告警并已 kill，`2` 参数错误。

---

## 9. 部署到新项目时只改三个地方

| 位置 | 内容 | 说明 |
|---|---|---|
| `watch_run.py: LSPP_PY` | 含 lasso 的 python 路径 | 本机：`~/.workbuddy/binaries/python/envs/lspp-mcp/Scripts/python.exe` |
| `check_tethers.py` 的 deck 文件名 | `Spring_swap.k` / `cab2_clean.k` / `BIW_clean.k` | 已支持 `--spring` 显式指定；锚点**自动从 deck 解析**，不写死节点号 |
| `T9` 的 `SPR_BAND` | `0.025` | 换构造（改 F0/C/绳长）必须重新标定，见 §5 |

> `check_tethers.py` 已去掉硬编码节点号：它从 `Spring_swap.k` 的 BEAM/DISCRETE 读
> `(bag, body)` 节点对，从两个网格文件算绳长，并**按节点对去重**
> （同一对节点常被 BEAM + DISCRETE 各定义一次，不去重会数成 20 根）。
