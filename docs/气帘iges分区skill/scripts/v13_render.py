# v13_render.py — 渲染 v13 端口区域 (带线号+坐标), 供用户目检确认
# 配色: 蓝=CAVITY(原有) 绿粗=v13新增(编号链L168-170-172+封口段L188/L196)
#       红=BELT 灰=未归档 橙虚=L161(v13已移出气腔)
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

BASE = os.environ.get("WORKDIR", ".") + "/out/"
feat = {}
for ln in open(BASE + "geom_features.txt", encoding="utf-8"):
    if not ln.startswith("LINE "):
        continue
    p = ln.split("|"); f = p[0].split()
    feat[int(f[1])] = dict(sp=tuple(map(float, p[1].split()[:2])),
                           ep=tuple(map(float, p[2].split()[:2])))
cls = json.load(open(BASE + "classify_v13.json", encoding="utf-8"))["line_comp"]
C = {int(k): v for k, v in cls.items()}

V13_ADD = {168, 169, 170, 172, 188, 196}   # v13 新并入 CAVITY
V13_OUT = {161}                             # v13 移出 CAVITY

def inport(l, x0, x1, y0, y1):
    d = feat[l]
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in (d["sp"], d["ep"]))

def draw(ax, ids, color, lw, z=3):
    for l in ids:
        if l not in feat:
            continue
        s, e = feat[l]["sp"], feat[l]["ep"]
        ax.plot([s[0], e[0]], [s[1], e[1]], color=color, lw=lw, zorder=z)

def shannon(ax, title, xlim, ylim, fname):
    port = [l for l in feat if inport(l, xlim[0], xlim[1], ylim[0], ylim[1])]
    cav = {l for l in port if C.get(l) == "CAVITY" and l not in V13_ADD}
    add = {l for l in port if l in V13_ADD and C.get(l) == "CAVITY"}
    belt = {l for l in port if C.get(l) == "BELT"}
    out = {l for l in port if l in V13_OUT}
    oth = {l for l in port if l not in cav | add | belt | out}
    draw(ax, cav, "#1f6fff", 2.0)
    draw(ax, belt, "#d11f1f", 1.6)
    draw(ax, oth, "#999999", 1.0)
    draw(ax, add, "#00aa44", 3.2, z=5)          # v13 新增(编号链+封口段)
    draw(ax, out, "#ff8800", 2.4, z=5)          # L161 已移出
    for l in port:
        s, e = feat[l]["sp"], feat[l]["ep"]
        if l in add:
            col = "#00aa44"
        elif l in out:
            col = "#ff8800"
        elif C.get(l) == "CAVITY":
            col = "#1f6fff"
        elif C.get(l) == "BELT":
            col = "#d11f1f"
        else:
            col = "#666666"
        mx, my = (s[0] + e[0]) / 2, (s[1] + e[1]) / 2
        ax.text(mx, my + 0.9, f"L{l}", color=col, fontsize=7, ha="center", va="bottom",
                fontweight="bold" if (l in add or l in out) else "normal",
                bbox=dict(boxstyle="round,pad=0.1", fc="white", ec=col, lw=0.4, alpha=0.9))
    for nm, pt, col in [("wedge_top", (834.9, 497.4), "magenta"),
                        ("L196_end(seal)", (841.0, 485.9), "#00aa44"),
                        ("L167_rbranch", (836.0, 350.3), "#1f6fff"),
                        ("L172_end", (875.26, 421.44), "#00aa44"),
                        ("L161_removed", (531.8, 335.1), "#ff8800")]:
        ax.scatter([pt[0]], [pt[1]], color=col, s=28, zorder=6)
        ax.annotate(nm, pt, xytext=(pt[0] + 9, pt[1] + 7), fontsize=7.5, color=col, fontweight="bold")
    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_aspect("equal")
    ax.grid(True, ls=":", alpha=.4); ax.set_xlabel("X"); ax.set_ylabel("Y")
    ax.set_title(title, fontsize=11)
    ax.legend(handles=[
        Line2D([0], [0], color="#1f6fff", lw=2, label="CAVITY (existing)"),
        Line2D([0], [0], color="#00aa44", lw=3, label="v13 NEW -> CAVITY"),
        Line2D([0], [0], color="#d11f1f", lw=2, label="BELT"),
        Line2D([0], [0], color="#ff8800", lw=2, ls="--", label="L161 removed fr CAVITY"),
        Line2D([0], [0], color="#999999", lw=1.2, label="unclassified"),
    ], loc="lower right", fontsize=7)

fig, ax = plt.subplots(figsize=(14, 10))
shannon(ax, "v13 Port Overview (X-large=Right): numbered chain L167-172 + seal L188/L196 now CAVITY",
        (495, 1005), (320, 520), None)
plt.tight_layout(); plt.savefig(BASE + "v13_port_overview_v13.png", dpi=130)
print("saved", BASE + "v13_port_overview_v13.png")

fig, ax = plt.subplots(figsize=(11, 13))
shannon(ax, "v13 Right Strip Zoom (decision area)", (810, 890), (345, 500), None)
plt.tight_layout(); plt.savefig(BASE + "v13_port_strip_v13.png", dpi=140)
print("saved", BASE + "v13_port_strip_v13.png")
