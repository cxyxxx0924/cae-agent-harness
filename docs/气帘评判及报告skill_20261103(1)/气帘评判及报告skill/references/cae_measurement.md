# CAE 测量：从 d3plot / H3D 取到可判的量

> 全部命令在本机实测过（2026-11，R676 气帘算例）。参数值因模型而异，但读法、算法与坑是通用的。

## 一、两条读取通道

| 通道 | 适合 | 限制 |
| --- | --- | --- |
| `lasso.dyna.D3plot`（Python 库，装在 lspp-mcp 环境） | 全状态节点坐标、单元连接、部件、能量 | 需要 d3plot；H3D 不支持 |
| HyperWorks live bridge（`scripts/hw_bridge.py`，MCP `hw.hv`） | 云图/截图/动画帧 | 沙箱路径限制；200 MB+ 易掉线 |

```bash
# lasso 解释器（系统 python 没有这个包）
PY="C:/Users/hekie/.workbuddy/binaries/python/envs/lspp-mcp/Scripts/python.exe"
```

常用数组：

| 名字 | 含义 | 备注 |
| --- | --- | --- |
| `node_coordinates` | 初始（未变形）坐标 `(n,3)` | **只有初始态**，没有每步坐标 |
| `node_displacement` | 每步位移 `(states,n,3)` | 变形坐标 = `c0 + disp[s]` |
| `global_timesteps` | 每步时间（ms） | 与 state 一一对应 |
| `element_shell_node_indexes` | 壳单元连接（0-based, 进 nodes 数组） | 直接索引 `c0[conn]` 需注意 offset |
| `element_shell_part_indexes` | 壳单元的部件**索引**（0..nparts-1） | 不是 part id |
| `part_ids` / `part_titles` | 索引 → part id / 名称 | 两个数组同序，名称按 ASCII 排序展示但**与 part_ids 对齐** |

## 二、部件定位（不要写死索引）

```python
titles = [t.decode().strip() for t in db.arrays[at.part_titles]]
idx = next(i for i, t in enumerate(titles) if "CAVITY" in t.upper())
```

某算例实测：8 个壳部件，`CAB1_BELT=pid 2 / CAVITY=3 / SEAM=4 / TETHER=5`，在 part 列表里的**索引**分别是 4/5/6/7（因为前面还有 4 个非气帘部件）。写死 `pidx == 3` 会静默取错部件，务必先打印索引表核对。

## 三、厚度算法（关键）

气帘是**双层壳**：面向乘员一张、面向车门一张。同一材料点在初始态两张壳的 (x,z) 相同、y 相差一层间隙。

1. 取 CAVITY 部件的节点，按 `round((x,z),2)` 排序配对；
2. 配对成功的判据：初始态 `|Δy|` 应是**一个常数**（本例全部 1.0 mm）。出现大范围分布 → 配对错了（可能有多层、或部件选错）；
3. 变形后厚度 = `|y_a(s) − y_b(s)|`，其中 `y = c0[:,1] + disp[s,:,1]`。

实测规模：CAVITY 35k 单元 / 69,762 节点 → 配对 33,702 个材料点（配对率 48.3%，剩余的是边缘自由节点）。

**为什么不能直接在变形后配 (x,z)**：鼓起后两张壳的投影不再重合，按变形坐标配对会错位。

某算例结果（82 状态 / 0–200 ms / 2.5 ms）：初始 1.0 mm，110 ms 峰值 191.4 mm，160 ms 全场 max 168.6 / p95 142.6 / 中位 61.2 mm。

## 四、点位采样

- 用**反距离加权取最近 k=3~4 个材料点**，不要取单点（网格 5 mm 量级，单点噪声大）。
- 同时输出 `gap_to_mesh`（到最近节点距离）。> 20–25 mm 说明这个点根本不在袋面上，数值无意义。
- 时程曲线逐状态算厚度再采样，别用两点插值。

## 五、坐标系：三种情形，三种对策

| 情形 | 表现 | 对策 |
| --- | --- | --- |
| 同一坐标系 | 点位落在气帘包围盒内 | 直接用 |
| 装配平移 | 差值为一个固定向量（如 DY/DZ） | 平移后核对距离；deck 注释里常写 `DY/DZ` |
| 平铺 vs 整车 | 量级差一个数量级（本例 X 3197–4225 vs 911–3117） | **平移无解**，需要"卷开/贴合"映射（HyperView 里 HPD → Flat IC 的那一步） |

第三种情况下能做的只有两件事：
1. 拿到映射规则或已在平铺系下的点位；
2. 用**厚度值反求**一个等价平移（`--solve-translation`），把它明确标成"临时基准"。反求有非唯一解，残差要写进报告。

反求实测：5 点目标 160.9/159.4/101.8/83.4/128.2 → dx≈−1515、dz≈−625，平均残差 33.7 mm，其中 Q6 单点残差 82 mm（落点在腔间带附近，梯度大，本身就敏感）。

## 六、缝线带宽怎么量（三种算法，只有一种能用）

| 算法 | 结果 | 问题 |
| --- | --- | --- |
| 缝线节点 → 最近腔体节点距离 ×2 | 中位 0 mm，p95 24 mm | 缝线与腔体**共节点**，距离恒为 0 |
| 缝线质心 → 两侧腔体质心距离之和 | 中位 18 mm，max 42 mm | 曲面弯折时"对侧"取到远处腔体，虚高 |
| **元素面积 / 长边** | 中位 4.48、p95 4.99、max 5.61 mm | 单排带时等于单元边长，是诚实的"建模宽度" |

第三种是对的，但它同时暴露结论边界：`rows_across = 宽度/单元边长 ≈ 0.85 < 2`，说明缝线被理想化成**一排单元**，带宽是建模时画的，不是 OPW 实际压合宽度。此时 15 mm 判据**不可验证**，只能 INDETERMINATE，真实值回 CAD 平铺图量。

## 七、覆盖率怎么算

1. 由 CoG 建圆角四边形（`g14_common.region_of_g3`，82/82/82/52/r82）；
2. 按 4 mm 网格采样，剔除圆角外的点（矩形近似会高估 2–4 个百分点）；
3. 每个采样点找最近部件（CAVITY/BELT/SEAM/TETHER），>25 mm 记为 OFF_CUSHION；
4. 输出 `CAVITY` 占比即"充气区覆盖率"。

## 八、时刻定格

- 起爆时刻从 `*SENSOR_SWITCH` 读（本例 `TIME > 100.0`），不要假设 0 ms。
- 状态索引 = `argmin(|times − t|)`；`state_index` 是**1-based 显示值**。
- 展开早中期（如起爆后 20–30 ms）是"是否扫到乘员"的关键窗口；后期（120–160 ms）是"是否保住厚度"的关键窗口。报告里两个都要有。

## 九、坑

1. **占位 inflator 曲线**：`(0,0)(100,1e−5)(200,1e−5)` 阶跃常数 → 起爆后 2.5 ms 展到 130 mm，压力恒 0。时序结论全部作废。
2. **压力算不出来**：质量流驱动（`*AIRBAG_...` + 质量流曲线）不写压力列，`abstat` 的压力列可能是 0，别当成"没充气"。
3. **`binout` 没有 nodout**：节点历史用 d3plot 位移自己叠。
4. **`part_titles` 排序**：ASCII 排序后与 `part_ids` 同序，但用 `part_titles_ids` 做偏移索引会错一位。
5. **numpy 标量进 JSON**：`np.int64` 不能直接 `json.dumps`，用 `default=lambda o: o.item()`。
6. **H3D 与 d3plot 不是同一套**：H3D 常常只有 Displacement / Effective plastic strain；厚度要从 d3plot 或静态充气模型来。
