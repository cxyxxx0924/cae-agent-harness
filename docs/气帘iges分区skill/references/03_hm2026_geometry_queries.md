# 03 · HyperMesh 2026 原生几何查询命令集

> 2026 hmbatch 实测（2026-10-21）。用于"结合 HyperMesh 里的 line/curve 几何功能
> 辅助判断"——几何判据尽量用 HM 原生函数拿真值，不靠 Python 侧重新近似。

## 1. 可用（实测返回正确值）

| 命令 | 用途 |
|---|---|
| `hm_linelength <id>` | 线长 |
| `hm_getlinestartpoint <id>` / `hm_getlineendpoint <id>` | 起/终点（返回 xyz 列表） |
| `hm_getlinetgstartpoint <id>` / `hm_getlinetgendpoint <id>` | 起/终点切线 |
| `hm_getlinetangentatcoordinate <id> <u> 0 0` | 参数 u∈[0,1] 处点+切线 |
| `hm_getlinelineangle <id1> <id2> <x> <y> <z>` | 两线在给定交点处的夹角 |
| `hm_getcoordinatesofpointsonline <id> <u>` | 线上参数点采样（渲染底图用） |
| `hm_findcirclefromthreepoints x1 y1 x2 y2 x3 y3` | 三点圆拟合（半径/圆心；弧判定） |
| `hm_getboundingbox` / `hm_getgeometrybox` | bbox |
| `hm_getdistance` | 距离 |
| `hm_checklineliesonline` | 共线检查 |
| `*createmark lines 1 "by id" {*}$chunk` + `hm_getmark lines 1` | 按 id 取集合 |
| `*createmark lines 1 "by collector name" <comp名>` | 按 comp 名取集合（校验用） |
| `*createentity comps name=X` | 新建 component |
| `*movemark lines 1 <comp名>` | 搬线进 comp（第三参是**名称**，P35） |
| `hm_getvalue comps id=<cid> dataname=name` | comp 名查询 |
| `hm_info templatefilename` | 当前模板文件名（loaduserprofile 验证） |

## 2. 不可用 / 行为异常（2026.0.0.27 实测）

| 命令 | 状况 |
|---|---|
| `hm_getentityvalue` 4 参 | 返回**错误值**，勿信 |
| `hm_entityinfo` / `hm_entitycount` | 不存在 |
| `*curvedistance` / `hm_getlinesinfo` / `hm_getcompsinfo` | 不存在 |
| `*renamecollectorbyid` | 改名失败且 comp 名变成 "11"——**勿用**（P35） |
| `*writefile` 目标已存在 | 弹 Overwrite? 交互 = 不可 catch FatalError；先 `file delete -force`（P35） |
| `*readfile` 目标不存在 | hmbatch 整体中止 exit 1，报告文件不生成（P39） |

## 3. hmbatch 运行要点

```bash
export WORKDIR="E:/work/AI_CAB/onekey/work"   # 脚本内 $::env(WORKDIR) 读取
"D:/Program Files/Altair/2026/hwdesktop/hm/bin/win64/hmbatch.exe" -tcl <脚本.tcl>
```

- Tcl 开头必须 `hm_framework loaduserprofile LsDyna Keyword971_R16.0`
  （2026 不写会报 `No user profile or template file loaded` / `data-name "pid" is not valid`；
  只写 `loaduserprofile LsDyna` 不够——要给全模板文件名）
- **`-tcl` 中文路径可正常 source**（2026.0.0.27 实测，P40；旧结论"必挂"作废）
- stdout 会出现 "prohibited." 等噪音，无视；**以报告文件 + exit code 为准**
- Tcl 引号内 `[` `]` 是命令替换；`puts` 不格式化 → 一律 `format`（P41）

## 4. 本技能脚本对 HM 命令的依赖

| 脚本 | 用到的 HM 命令 |
|---|---|
| t01_export_geom.tcl | hm_linelength / hm_getline*point / hm_getlinetg* / hm_getlinelineangle / hm_findcirclefromthreepoints |
| t02_export_pts.tcl | hm_getcoordinatesofpointsonline / hm_getlinestartpoint / hm_linelength |
| t07_make_comps.tcl | *createentity comps / *createmark+hm_getmark / *movemark / *writefile |
| t08_verify_partitioned.tcl | hm_getvalue / hm_getmark / hm_getline*point / hm_linelength / *createmark |
