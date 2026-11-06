# v9_render.py — v9 问题区域特写渲染（按类别着色 + 全 id 标注）
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

BASE = os.environ.get("WORKDIR", ".") + "/out/"

pts = {}
for ln in open(BASE + "lines_pts.txt", encoding="utf-8"):
    if not ln.startswith("L "):
        continue
    head, _, tail = ln.strip().partition("|")
    lid = int(head.split()[1])
    pl = [(float(s.split()[0]), float(s.split()[1])) for s in tail.strip().split(";") if s.strip()]
    pts[lid] = pl

cls = json.load(open(BASE + "classify_final.json", encoding="utf-8"))["line_comp"]
CLS = {int(k): v for k, v in cls.items()}
COL = {"BELT": "red", "CAVITY": "blue", "SEAM": "green", "TETHER": "orange"}

def render(x0, x1, y0, y1, title, fname, figsize=(16, 11), annsize=7):
    fig, ax = plt.subplots(figsize=figsize)
    for c, col in COL.items():
        segs = []
        for lid, pl in pts.items():
            if CLS.get(lid) != c:
                continue
            for i in range(len(pl) - 1):
                if x0 <= pl[i][0] <= x1 and y0 <= pl[i][1] <= y1:
                    segs.append((pl[i], pl[i + 1]))
        ax.add_collection(LineCollection(segs, colors=col, linewidths=1.6, label=c))
    # id labels on every line whose any point is in range
    for lid, pl in pts.items():
        if not any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pl):
            continue
        mx = sum(p[0] for p in pl) / len(pl); my = sum(p[1] for p in pl) / len(pl)
        ax.annotate(str(lid), (mx, my), fontsize=annsize, color=COL[CLS.get(lid, "TETHER")],
                    xytext=(2, 2), textcoords="offset points")
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_aspect("equal"); ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=10)
    ax.set_title(title)
    fig.tight_layout(); fig.savefig(BASE + fname, dpi=115)
    plt.close(fig)
    print("saved", fname)

# 口部全景
render(430, 970, 320, 520, "PORT region x[430,970] y[320,520] — find outer contour vs inner junk", "v_v9_port.png", (18, 12), 6.5)
# 右上区域（布带顶边断链 + 右缘）
render(1380, 1700, 290, 500, "RIGHT-TOP x[1380,1700] y[290,500] — belt top-edge gap + right edge", "v_v9_righttop.png", (16, 10), 7)
# 缝线气道缝区域
render(520, 910, 230, 350, "SEAM gas-channel x[520,910] y[230,350] — junk to remove", "v_v9_seamgas.png", (16, 8), 7)
# 左下排气口
render(-280, 20, -80, 20, "LEFT-BOTTOM x[-280,20] y[-80,20] — exhaust circles", "v_v9_exhaust.png", (12, 9), 8)
