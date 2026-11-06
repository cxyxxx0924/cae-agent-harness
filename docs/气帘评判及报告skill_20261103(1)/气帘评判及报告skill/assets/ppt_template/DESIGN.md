# DESIGN.md — 侧面气帘展开性能评估 (C-NCAP 附录G G.14.3)

> 页序与每页要素以 `references/report_structure.md` 的四段式为准，本文件只管视觉约定。
> 沿用客户模板时改用 B 风格（主色 `#005496` / 强调 `#009FE3` / 正文 `#474C4F`），
> 取值见 `references/ppt_workflow.md`。

## 全局视觉约定（蓝白学术风，沿用参考模板）
- 画布 1280×720；内容页结构：顶部深蓝标题条(72px) + 内容区(padding 48) + 底部页脚条(36px)。
- 配色：主色 `#1E4FA8`；强调/警示 `#D9534F`；符合绿 `#2E7D32`；正文 `#1A2230`；辅助灰 `#8B97A8`；底色 `#FFFFFF`；浅底 `#F7F9FC`/`#E8EFF8`；分隔线 `#E5E7EB`。
- 字体：中文 `"Microsoft YaHei", "PingFang SC", sans-serif`；西文/数字 Arial。
- 字号：页主标题 30–32px(bold); 卡片小标 22px; 正文 18–20px; 表格 16–18px; 注释 13–14px。
- 视觉母题：全篇统一深蓝顶条 + 页脚页码，内容页一致。

## 页面清单（11 页，初版）
1. cover — 封面
2. content — 模型与 CAD 信息
3. content — 评估锚点：假人头部重心坐标（表）
4. content — 法规评价要点 G.14.3（三项 + 罚分）
5. content — 评估区域示意图（内联 SVG）
6. content — 气帘展开云图（末步，图）
7. content — 气帘展开早期（第15步，图）
8. content — IC 厚度 @ 头部重心（覆盖证据，表）
9. content — G.14.3 评价结论（评分卡，表）
10. content — 限制与下一步
11. content — HyperWorks / MCP 联通状态

## 配图清单
- `assets/2974_disp_last.png` (末步位移云图) → P6
- `assets/2974_disp_s15.png` (早期展开云图) → P7
- 内联 SVG（评估区域侧视锚点图）→ P5
- `assets/figures/fig_G3_eval_region.png`（515×318，h/w=0.618）→ 评估区域尺寸链页
- `assets/figures/fig_G4_head_cog.png`（431×416，h/w=0.965）→ CoG 定义页
- `out/fig_thk_field.png`（1950×780）、`out/fig_thk_curves.png`（1440×690）→ 厚度结果页

> 本目录下的 `.slide` 为可复制起手模板；`Image src` 相对 deck 路径，
> **必须同时写 width 与 height**，否则会被压扁。
