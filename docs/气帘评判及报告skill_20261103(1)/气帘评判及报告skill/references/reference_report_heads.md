# 参考报告头部重心坐标提取与模板结构

## 参考报告
- 文件：`JOB-00061377_IC_Coverage.pptx`（Autoliv GEELY R676 IC Coverage & Volume）
- 共 13 页；风格：蓝白学术风，每页母版带 "Internal" / "Copyright Autoliv Inc." 角标。

## 头部重心（Head Barycenter）坐标表
提取自第 3 页 "Dummy Setup" 表格（车辆坐标系，单位 mm；最后一列 IC 厚度为静态充气
33.8 L @35 kPa 结果，非碰撞 H3D）：

| Order | Dummy Names | X (Hx) | Y (Hy) | Z (Hz) | Angle | IC 厚度 (mm) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1ROW_WS50@60 AEMDB | 3197.2 | −449.4 | 1405.2 | 0.0 | 160.9 |
| 2 | 1ROW_WS50@32 SP2 | 3197.2 | −449.4 | 1396.2 | 0.0 | 159.4 |
| 3 | 2ROW_Q6@60 AEMDB | 3917.0 | 425.7 | 1293.5 | 0.0 | 101.8 |
| 4 | 2ROW_Q3@60 AEMDB | 3554.3 | 351.3 | 1271.4 | 0.0 | 83.4 |
| 5 | 2ROW_Q10@60 AEMDB | 4225.0 | −429.5 | 1364.7 | 0.0 | 128.2 |

> 这些坐标在**车辆全局系**（X 纵向 / Y 横向 / Z 高度）。
> 气帘 `*AIRBAG_REFERENCE_GEOMETRY` 常位于局部/镜像系（Y≈0），**不可直接比较坐标**判定覆盖。
> 本 skill 把 5 个点当作 G.14.3.1.1.2 的评估区域圆心锚点使用。

## 提取方法
```bash
# 用 workbuddy-pptx 的 slidep 把参考报告解析为可读文本
slidep inspect JOB-00061377_IC_Coverage.pptx --out ref_slides.md
# 在 ref_slides.md 中定位 "Dummy Setup" 页的 t1 表格，抄录坐标
```
坐标单位为页面像素时原点在左上；但头部重心表内的数值是模型坐标（mm），直接取用即可。

## 参考报告 13 页结构（作模板蓝本）
1. 封面（GEELY R676 IC Coverage & Volume）
2. CAD Data（IC CAD / Cushion Material）
3. Dummy Setup（头部重心 + IC 厚度表）← 提取坐标来源
4. Result - Standard Requirements
5. Result - Standard Requirements（IC Shape @35kPa, Total Volume 33.8L）
6–7. Result - HPD Location Contour（Map HPD Profile & Head Barycenter to Flat IC）
8–12. Result - IC Thickness @Head Barycenter（逐假人一页，含 Head Barycenter 坐标 + 厚度）
13. 收尾页

### 第 6 页那张 HPD 图怎么读（客户最常引用的证据）
- 原图 = `ppt/media/image14.png`（1531×861），图例 `image15.png`。**直接取原文件**，
  不要截屏，清晰度与配色都对得上母版。
- 上半幅：平展的 flat IC 投影，5 个红点 = 5 个头部重心的落位；蓝色虚线等值线是
  HPD 轮廓（阈值 0 与 2，红 > 2、蓝 0–2、灰不涉及）；外圈灰色是气帘轮廓。
- 下半幅：同一结果叠在装配态三维模型上，用来看与座椅/B 柱/门板的空间关系。
- 这张图回答的只有"落点是否在充气区内"，**不回答** 15 mm、50 mm、触底。
- 它同时说明了正确做法：把 HPD 轮廓与头部重心**映射到 flat IC**，再在平铺图上判——
  这正是"整车系 vs 平铺系"不能直接相减的原因。

## 本 skill 生成的报告（11 页，沿用上述风格）
封面 → 模型/CAD → 头部重心锚点表 → G.14.3 要点 → 评估区域示意图(SVG)
→ 末步展开云图 → 早期展开云图 → IC 厚度覆盖证据 → 评价结论评分卡
→ 限制与下一步 → MCP 联通状态。
