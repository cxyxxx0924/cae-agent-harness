# CAB Iter04 source package

本目录集成当前选定的侧气帘算例源文件、头型网格、法规参考和客户参考报告。当前分析基线为带车身与移动弹簧的 Iter04 `5P-BAG_005`。

## 纳入基线

- `Model_update_Move_Iter04/Model_update_Move_Iter04/main.key`：主 deck，按相对路径 include 同目录的 `03_Control_card.k`、`5P-BAG_005.key`、`6P_CAB_update2.k`、`MAT.K`、`Vehicle.k` 和 `Spring_move.k`。
- `head_area/main_dummy.key`：当前头型评估 deck，引用 Iter04 模型、`Protect_Area.k` 和以下四个头型网格：`HIII_5F_Head.key`、`HIII_5F_Head_Rear.key`、`HIII_95M_Head.key`、`HIII_95M_Head_Rear.key`。
- `附录G可变形移动壁障侧面碰撞测试评价规程.pdf`：法规参考文本。
- `JOB-00061377_IC_Coverage.pptx`：客户提供的覆盖参考报告；作为参考资料，不视为已验证的本项目结果。

客户报告为 Autoliv GEELY R676 IC Coverage & Volume，共 13 页。其第 3 页记录 5 个假人头部重心及静态 IC 厚度，坐标表已摘录到 `docs/气帘评判及报告skill_20261103(1)/气帘评判及报告skill/references/reference_report_heads.md`。该表属于客户参考车型的全局坐标，不能直接替代当前 Iter04/HIII 布置坐标或碰撞结果。

模型 deck、头型网格和 PPTX 使用 Git LFS 管理。运行生成型分析前，应将临时结果放到 `evidence/`；该目录默认不纳入版本控制。

## 当前不纳入

- `Model_update/` 下的 `5P-BAG_004` 及其配套文件属于旧模型版本，不是 Iter04 基线。
- `head_area/main_dummy.key` 不再引用 WorldSID；本轮范围只包含四个 HIII 网格。WorldSID 既非当前评估所需，也未随本批资料提供。
- `docs/file_for_CAB/Vehicle.k` 是目录顶层的独立副本，不属于 Iter04 主 deck 的 include 闭包；主 deck 使用其自身目录下的 `Vehicle.k`。
- `evidence/nodes_last.json` 等求解/HyperView 导出物不是源资料；头型与气帘几何证据脚本需要本地提供相应状态导出后才可完整运行。

## 评估注意事项

- 求解资料中记录的曲线 21 为压力-时间曲线 `0 -> 0, 100 -> 1e-5, 200 -> 1e-5 MPa`，压力幅值全程近零；现有求解复盘指出气囊压力由 CV 气体状态驱动，曲线 21 不能单独作为可靠的气帘展开时序依据。
- 几何对照脚本按四个 HIII 网格和 `main_dummy.key` 中的平移布置生成证据。图形/间隙数值用于几何检查，不替代法规判定或求解结果审查。

相关方法记录：`docs/气帘计算求解skill_20261102(1)/气帘计算求解skill/references/07_pitfalls_index.md`、`docs/气帘评判及报告skill_20261103(1)/气帘评判及报告skill/references/head_curtain_evidence.md`。
