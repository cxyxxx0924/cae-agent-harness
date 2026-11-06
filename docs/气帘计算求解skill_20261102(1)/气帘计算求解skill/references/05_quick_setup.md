# 05 · 快速设置清单（Quick Setup）

> 换项目 / 新机器第一件事：把下面路径核对一遍，全部从环境变量或本文件取，**禁止项目里硬编码**。

## 1. 环境一键核对

```bash
# Python（带 numpy / matplotlib，已注册中文字体 msyh.ttc）
export PY="C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
$PY -c "import numpy, matplotlib; print('ok', numpy.__version__)"

# 求解器（本机 R10.1.0，不是 R13！）
ls "D:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_sp.exe"

# LSPP 4.6（可选）
ls "D:/Program Files/LSTC/LS-PrePost 4.6/lsprepost4.6_x64.exe"

# MCP（lspp-mcp，solver profile = ansys_smp_sp）
cat E:/work/lspp-mcp-server/config.yaml | grep -A3 solver_profiles
```

## 2. 典型命令序列（从 K 交付到交付图，一条龙）

```bash
PY="C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
WS=E:/work/lsdyna-agent/newcab_trial
cd $WS

# ① K 衔接门禁（镜像自 CURVEtoMESH 技能）
$PY <技能目录>/scripts/qa_kfile_strict.py newcab_calc.k
$PY <技能目录>/scripts/geom_match_check.py --workdir $WS
$PY <技能目录>/scripts/tether_conn_check.py --workdir $WS

# ② 求解（MCP run_lsdyna_solver profile=ansys_smp_sp，或本机直跑）
"D:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_sp.exe" \
    i=newcab_calc.k ncpu=4 memory=2000m 2>&1 | tee solve.log

# ③ 健康门禁
$PY <技能目录>/scripts/k_health_gate.py --glstat glstat --matsum matsum --abstat abstat \
    --total-mass 0.70067

# ④ 固定节点校验 + 几何提取
$PY <技能目录>/scripts/d3plot_reader.py --geom d3plot --state d3plot09 \
    --deck newcab_calc.k --out /tmp/d3p09

# ⑤ 渲染交付
$PY <技能目录>/scripts/render_deploy.py --d3dir $WS --deck newcab_calc.k --glstat glstat --out render
```

## 3. 路径常量（换项目只改这些）

| 项 | 值 |
|---|---|
| 求解器 | `D:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_sp.exe` |
| solver profile | `ansys_smp_sp`（SMP, ncpu=4） |
| LSPP | `D:/Program Files/LSTC/LS-PrePost 4.6/lsprepost4.6_x64.exe` |
| Python venv | `C:/Users/hekie/.workbuddy/binaries/python/envs/default/Scripts/python.exe` |
| 中文字体 | `C:\Windows\Fonts\msyh.ttc`（脚本自动注册） |
| 参考模型 | `E:\work\AI_CAB\ref-Output\Model_update` 与 `Model_from_AI_07` |
| 上游网格技能 | `E:\work\skill\hypermesh2026_CURVEtoMESH_skill` |
| 上游分区技能 | `E:\work\skill\气帘iges分区skill` |

## 4. 易错快速核对

- [ ] R10.1.0 不是 R13 → R11+ 关键字会被拒（先核对关键字年代）
- [ ] DT2MS 负值（目标最小步长），**禁止置 0 裸跑**
- [ ] solver profile 必须显式填 `ansys_smp_sp`（否则 `profile not found: ""`）
- [ ] MCP 长跑后掉线 → 直接 numpy 读 d3plot，不依赖后处理工具
- [ ] d3plot 单元连接区按 **int32** 读（float32 读出 1e-41 误判全零）
- [ ] 整数头字段（NUMNOD/NUMEL）用 **int32** 视图取
- [ ] 固定判据 = d3plot 当前坐标逐位==初始坐标（max|Δ|=0.0），别信 spcforc
- [ ] 中文字体脚本自动注册，图里出现方框说明字体未加载
