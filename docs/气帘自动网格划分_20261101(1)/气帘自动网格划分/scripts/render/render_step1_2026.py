"""渲染 2026 第一步网格验证图: 全局分区 / 缝环贴合 zoom / L3 界面 zoom"""
import collections, math, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly

P = pathlib.Path(r"./out")
mesh = P / "step1_mesh_2026.txt"
nodes, elems = {}, collections.defaultdict(list)
for line in open(mesh, encoding="utf-8"):
    f = line.replace("{", " ").replace("}", " ").split()
    if not f:
        continue
    if f[0] == "N":
        nodes[int(f[1])] = (float(f[2]), float(f[4]))   # X-Z
    elif f[0] == "S":
        elems[f[1]].append([int(x) for x in f[3:]])

# --- CAD 曲线基准 (lines_pts.txt: TAG LID LEN spx spz epx epz | "x z";...) ---
cad = {}
for raw in open(P / "lines_pts.txt", encoding="utf-8"):
    head, _, tail = raw.strip().partition("|")
    ff = head.split()
    pts = [tuple(map(float, s.split())) for s in tail.strip().split(";") if s.strip()]
    cad[int(ff[1])] = pts

COLOR = {"belt": "#4C72B0", "cav": "#55A868", "seam0": "#C44E52", "seam1": "#8172B2",
         "seam2": "#CCB974", "seam3": "#64B5CD", "seam4": "#E17C05"}

def draw_group(ax, tag, lw=0.25):
    for ns in elems[tag]:
        u = list(dict.fromkeys(ns))
        xy = [nodes[n] for n in u]
        ax.add_patch(MplPoly(xy, closed=True, facecolor="none",
                             edgecolor=COLOR.get(tag, "#999"), lw=lw))

# ---------- 图1: 全局 ----------
fig, ax = plt.subplots(figsize=(15, 7), dpi=110)
for tag in ["belt", "cav"] + [f"seam{i}" for i in range(5)]:
    draw_group(ax, tag, lw=0.2)
for lid in (138, 76):
    if lid in cad:
        ax.plot([p[0] for p in cad[lid]], [p[1] for p in cad[lid]], "-", color="k", lw=1.0, label="L3(气腔轮廓)" if lid == 138 else None)
ax.set_aspect("equal"); ax.grid(alpha=0.25)
ax.set_title("2026 Step1: 布带(PID2,蓝) / 气腔(PID3,绿) / 5缝环(PID4,暖色)  黑线=L3 CAD轮廓")
ax.set_xlabel("X (mm)"); ax.set_ylabel("Z (mm)")
handles = [plt.Line2D([], [], color=c, label=t) for t, c in COLOR.items()]
handles.append(plt.Line2D([], [], color="k", label="L3 CAD"))
ax.legend(handles=handles, fontsize=8, loc="upper right")
plt.tight_layout(); plt.savefig(P / "v2026_step1_all.png"); plt.close()

# ---------- 图2: 缝环 zoom (网格 vs CAD 曲线) ----------
ring_cad = {"seam0": [337], "seam1": [336], "seam2": [193],
            "seam3": [157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169],
            "seam4": [140, 141, 142, 144, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155]}
fig, axes = plt.subplots(2, 3, figsize=(16, 8), dpi=110)
for i, tag in enumerate([f"seam{j}" for j in range(5)]):
    ax = axes[i // 3][i % 3]
    draw_group(ax, tag, lw=0.5)
    for lid in ring_cad[tag]:
        if lid in cad:
            ax.plot([p[0] for p in cad[lid]], [p[1] for p in cad[lid]], "-", color="k", lw=1.6, alpha=0.85)
    xs = [nodes[n][0] for ns in elems[tag] for n in ns]
    zs = [nodes[n][1] for ns in elems[tag] for n in ns]
    ax.set_xlim(min(xs) - 25, max(xs) + 25); ax.set_ylim(min(zs) - 25, max(zs) + 25)
    ax.set_aspect("equal"); ax.grid(alpha=0.25)
    ax.set_title(f"{tag}: {len(elems[tag])} elems  黑=CAD缝线曲线", fontsize=9)
    ax.tick_params(labelsize=7)
# 第6格放说明
axes[1][2].axis("off")
axes[1][2].text(0.05, 0.6,
                "判读: 网格外边界应压在黑线上\n"
                "(面由缝线曲线 spline 生成, 边界天然贴合)\n\n"
                "seam0/1/2: 单线自闭合窄带环\n"
                "seam3: 拆 157 往返线取单程 + 补 6.9mm 桥\n"
                "seam4: 14 线长条带 + 两端小圆结",
                fontsize=10, va="top")
plt.tight_layout(); plt.savefig(P / "v2026_seam_zoom.png"); plt.close()

# ---------- 图3: belt/cav 界面 zoom ----------
fig, ax = plt.subplots(figsize=(12, 6), dpi=110)
draw_group(ax, "belt", lw=0.4)
draw_group(ax, "cav", lw=0.3)
ax.set_aspect("equal"); ax.grid(alpha=0.25)
ax.set_title("布带(蓝) / 气腔(绿) 界面 —— 一次裁切共享 topo edge, 共节点 1280")
# 取 belt/cav 交界附近放大
bn = set()
for ns in elems["belt"]:
    bn.update(ns)
cn = set()
for ns in elems["cav"]:
    cn.update(ns)
shared = bn & cn
if shared:
    xs = [nodes[n][0] for n in shared]; zs = [nodes[n][1] for n in shared]
    cx, cz = sum(xs) / len(xs), sum(zs) / len(zs)
    ax.set_xlim(cx - 260, cx + 260); ax.set_ylim(cz - 160, cz + 160)
    ax.scatter(xs, zs, s=3, c="red", zorder=5)
    ax.set_title(f"界面 zoom: 共节点 {len(shared)} (红点)")
plt.tight_layout(); plt.savefig(P / "v2026_interface.png"); plt.close()

print("saved: v2026_step1_all.png / v2026_seam_zoom.png / v2026_interface.png")
