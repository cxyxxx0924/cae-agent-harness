# -*- coding: utf-8 -*-
"""render_anchor_summary.py — 锚固区 2×2 汇总图（两处凸台 × v3/v4）"""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from render_anchor_side import draw

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

v3, v4 = sys.argv[1], sys.argv[2]
blocks = [(978.4, 382.6, 24.0, "凸台 blk6（X≈978）"),
          (1477.9, 383.4, 26.0, "凸台 blk4（X≈1478，v3 最差处）")]
lab3 = sys.argv[4] if len(sys.argv) > 4 else "v3 硬吸附"
lab4 = sys.argv[5] if len(sys.argv) > 5 else "v4 三刀切"
fig, axs = plt.subplots(2, 2, figsize=(13.5, 8.2), sharey=True)
for i, (cx, cy, half, name) in enumerate(blocks):
    draw(axs[i][0], v3, cx, cy, half, f"{lab3} — {name}", 8)
    draw(axs[i][1], v4, cx, cy, half, f"{lab4} — {name}", 8)
fig.suptitle(f"拉带锚固排：{lab3} vs {lab4}（侧视，Z 落差 1mm 已纵向放大）\n"
             "灰=布带 Z=0  蓝=拉带本体 Z=−1  橙红=跨 Z 过渡排", fontsize=11)
fig.tight_layout()
fig.savefig(sys.argv[3], dpi=150, bbox_inches="tight")
print("写出", sys.argv[3])
