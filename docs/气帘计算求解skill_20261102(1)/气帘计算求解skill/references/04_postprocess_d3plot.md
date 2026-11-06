# 04 · 后处理：d3plot 二进制逆向 + 健康门禁 + 漂移诊断

> **本会话最大成果**：本机 d3plot 二进制布局已逆向破解，numpy 直接可读，**不依赖 LSPP / HyperView / MCP**。
> MCP 长跑后易掉线，这套逆向是兜底的"硬核后处理"手段。

## 1. d3plot 二进制布局（本机 LS-DYNA R10.1.0 实测，numpy 直读）

### 主 d3plot（纯几何文件，无状态数据）
| 段 | 位置 | 说明 |
|---|---|---|
| 标题 | word 0–9 | 10 词 |
| 控制块 | word 10–63 | **54 词**；整数头字段用 **int32** 视图读：`word16`=NUMNOD，`word31`=NUMEL |
| 节点坐标 | **@word 64** | 3 float32/节点，共 3·NUMNOD 词；节点 i → word `64+3·(i-1)` |
| 单元连接 | **@word(64+3·N)** | **int32**，每单元 5 词 = `n1,n2,n3,n4,part索引`（PID2→1 / PID3→2 / PID4→3 / PID5→4） |
| 目录 | @连接区尾 | 16 词 int32（含 -1，按 float 读成 NaN） |
| 节点ID表 / 单元ID表 | 目录后 | NUMNOD / NUMEL 词 |

★ **致命坑**：单元连接区按 **int32** 读！按 float32 读会得到 1e-41 级小数，误判为"全零"导致后续面积/体积全崩。
★ 整数头字段（NUMNOD/NUMEL）也必须用 **int32** 视图取（float32 视图下位模式错位成 0.0）。

### 状态文件 d3plotNN（状态数据）
| 段 | 位置 | 说明 |
|---|---|---|
| 头部 | word 0–139 | **140 词** |
| 坐标(当前) | **@word 140** | 3 float32/节点，节点序 = 节点 ID 序 |
| 速度 | **@word(140+3·N)** | 3 float32/节点（实测 |v|mean≈3.2，与 glstat KE 自洽） |
| 加速度 | **@word(140+2·3·N)** | 3 float32/节点（应变值不物理，确认是加速度非位移） |

- **固定节点判据**：当前坐标与初始坐标**逐位相等**（max|Δ|=0.0）。本会话用此判据在全文件搜索，
  命中固定节点三元组 @word 11342 等，确认状态文件坐标块在 **word 140、ID 序**。
- **位移数组位置**：本模型 d3plot 未单独写位移数组（LS-DYNA 通常 d3plot 只写坐标+速度+加速度）；
  位移 = 当前坐标 − 初始坐标（从主 d3plot 取初始）。

## 2. 时刻标定（状态文件头部不直接含可读时间）

速度 RMS → `KE_est = ½·M·vRMS²` → 与 glstat 的 kinetic energy 序列匹配。
- NEW_CAB 实测：d3plot03≈**4.4ms** / 05≈**9.4ms** / 08≈**17ms** / 09–10≈**20ms**。
- ⚠️ 旧会话曾把 d3plot08 当 20ms（有误）；务必用 RMS↔KE 标定，不要看文件名猜。

## 3. 健康门禁判读（脚本 `k_health_gate.py`）

读 `glstat` / `matsum` / `abstat`，自动判 6 道门禁（对照规范 1.1）：
```
python k_health_gate.py --glstat glstat --matsum matsum --abstat abstat \
    --total-mass 0.70067        # 织物总质量(kg)，不给则只报 added mass 绝对值
```
| 门禁 | 判据 | NEW_CAB 实测 |
|---|---|---|
| 质量增加 | added/total < 3% | **0.0002%** PASS |
| 沙漏能 | hg/(IE+KE) < 3% | **0** PASS |
| 能量比 | (IE+KE)/EW ≈ 1.0 | **1.00001** PASS |
| 0 单元触底 | added nodes / interface 异常 | **0** PASS |
| 时间步 | 最小 dt ≈ \|DT2MS\| 且非退化 | 4.95e-4（受控）PASS |
| 充气自洽 | P ≈ m·R·T/V (R=287) | V=35.2L, P=1.028bar, m=16.07g@760K, 比值≈1.0 PASS |

退出码 0=全 PASS，1=有 FAIL。

## 4. 漂移诊断（matsum + abstat + 锚点分布）

- **matsum 各 part 动量**比 d3plot 直接得多。提取 `mat.#= 3`（气腔）的 `x-mom/y-mom/z-mom` 时序。
- NEW_CAB 实测：气腔 z-mom 10ms 后**线性增长**（0.075→1.70）；新跑 global z-v=**2.48 m/s**，旧跑（未固定）仅 0.023。
- x 漂移两轮都有（旧 1.22 / 新 1.76）→ 属固有行为，用户已认可；**z 漂移是固定拉带后新出现**。
- **机理**：拉带端钉死 → 持续 +z 净力 → 袋体拉向固定端。根因=锚系只箍右端+两条拉带线、质心未完全约束。
- **abstat 充气自洽**：0.92L→35.2L、1.028 bar、16.07g@760K，P=mRT/V 完全吻合；4.3ms 起充至 60ms。

## 5. 状态文件读取器（脚本 `d3plot_reader.py`）

```bash
PY="C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
$PY scripts/d3plot_reader.py --geom d3plot --state d3plot09 \
    --deck newcab_calc.k --mass 0.70067 --out /tmp/d3p09
```
输出：节点数/单元数、part 分布、固定节点校验(max|Δ|)、各 part 平均位移、腔体包络体积、速度 RMS↔KE，
并写 `<out>.npz`（coords/velocity/accel/initial/partid）供下游渲染。

## 6. 渲染交付（脚本 `render_deploy.py`）

```bash
$PY scripts/render_deploy.py --d3dir E:/work/lsdyna-agent/newcab_trial \
    --deck newcab_calc.k --glstat glstat --out render
```
自动发现 d3plotNN → 用速度 RMS↔KE 标定时刻 → 输出：
- `render_process.png`：部署过程（平铺→4.4ms→9.4ms→20ms，X-Z 顶视，固定节点标注）
- `render_t20_detail.png`：终态四视图（X-Z 分区 / Y-Z 侧视袋体展开 / X-Y 平铺面 / 位移模长云图）

★ 中文字体：脚本自动注册 `C:\Windows\Fonts\msyh.ttc`（Microsoft YaHei），无需手动配置。

## 7. 健康门禁示例报告（NEW_CAB 终态）

```
[PASS] 质量增加                   实测=0.0002%      门禁=< 3%
       └ added_mass=... total=... 
[PASS] 沙漏能占比                 实测=0.0000%      门禁=< 3%
       └ hg=0.0 ie=4.96e+00 ke=7.90e+00
[PASS] 能量比 (IE+KE)/EW          实测=1.00001      门禁=≈ 1.0
[PASS] 最小时间步                 实测=4.95e-04     门禁=受 DT2MS 控制
[PASS] 充气气体定律 P/(mRT/V)     实测=1.003        门禁=≈ 1.0
       └ V=35.2L P=1.028e-04 m=0.0161kg T=760K
结果：6/6 项 PASS
```
