"""S3 种子分类生成器（区域规则版，无掩膜/无找洞）。

输入: WORKDIR/out/lines_pts.txt
输出: WORKDIR/out/<SEED>.json  = {"line_comp": {"<id>": "BELT|CAVITY|SEAM|TETHER", ...}}

判据（用户四原则 2026-10-23, 适用 cab3 及同类展开图）:
  BELT    = 整个宏观视图的外轮廓 (凸包边界曲线, 与坐标轴无关, 通用锚点)
  CAVITY  = 贴近布带环的内部大环(基本靠在布带环内侧)
            -> 实现: 非外缘 且 到外轮廓距离 d_belt < CAVITY_D
  SEAM    = 气腔环内的细线/哑铃状封闭曲线(宏观封闭意义), 一定在气腔环内部
            -> 实现: 非外缘 且 d_belt >= CAVITY_D (更靠内)
  TETHER  = 顶部那一排挂钩/凸台 + 右侧长条状
            -> 实现: boss = 顶部带内"高圆度小尺寸的连通分量"(凸台符号核心是小圆+竖腿);
                     右侧长条 = cx > xmax-RIGHT_W 且细长

与坐标无关的稳健锚点:
  - BELT 用凸包边界(非 bbox 边), 可处理圆角/充气口凸出等不规则外轮廓
  - TETHER 凸台用"圆度+尺寸+顶部带"的连通分量, 不靠"顶部+闭合+小"这种会误吞环段的脆弱规则

所有阈值环境变量可覆盖(换图纸不改脚本):
  AP_BELT_TOL / AP_BELT_FRAC / AP_CAVITY_D / AP_BOSS_Y
  AP_BOSS_CIRC / AP_BOSS_DMIN / AP_BOSS_DMAX
  AP_RIGHT_W / AP_RIGHT_ASP / AP_RIGHT_LEN
"""
import os, math, json
from collections import defaultdict
import numpy as np
from scipy.spatial import ConvexHull

BASE = os.environ.get("WORKDIR", os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out")
SEED = os.environ.get("SEED", "cab3_classify_seed.json")

# ---------------- 可调参数 (DEFAULTS) ----------------
BELT_TOL  = float(os.environ.get("AP_BELT_TOL",  "4"))    # 曲线点距凸包边界 < 此(mm) 比例达标 = 外轮廓 BELT
BELT_FRAC = float(os.environ.get("AP_BELT_FRAC", "0.5"))   # 曲线点落在凸包边界 TOL 内的比例阈值
CAVITY_D  = float(os.environ.get("AP_CAVITY_D",  "72"))   # 到外缘距离 < 此(mm) = 贴边大环 CAVITY
BOSS_Y    = float(os.environ.get("AP_BOSS_Y",    "160"))  # 顶部 boss 带 y 下沿(mm)
BOSS_CIRC = float(os.environ.get("AP_BOSS_CIRC", "0.45")) # 凸台分量圆度阈值
BOSS_DMIN = float(os.environ.get("AP_BOSS_DMIN", "3"))    # 凸台分量最大直径下限(mm)
BOSS_DMAX = float(os.environ.get("AP_BOSS_DMAX", "20"))   # 凸台分量最大直径上限(mm)
RIGHT_W   = float(os.environ.get("AP_RIGHT_W",   "45"))   # 右侧长条带宽(mm, 从右缘往左)
RIGHT_ASP = float(os.environ.get("AP_RIGHT_ASP", "3.0"))  # 右侧长条细长比
RIGHT_LEN = float(os.environ.get("AP_RIGHT_LEN", "40"))   # 右侧长条最小长度(mm)

# ---------------- 读点 ----------------
curves = {}
for ln in open(os.path.join(OUT, "lines_pts.txt"), encoding="utf-8"):
    if not ln.startswith("L "):
        continue
    head, _, tail = ln.strip().partition("|")
    lid = int(head.split()[1])
    pl = []
    for s in tail.strip().split(";"):
        s = s.strip()
        if not s:
            continue
        xyz = s.split()
        if len(xyz) >= 2:
            pl.append((float(xyz[0]), float(xyz[1])))
    pl = np.array(pl, float)
    if pl.shape[0] < 2:
        continue
    curves[lid] = pl

allpts = np.vstack(list(curves.values()))
print("N=%d  bbox x[%.1f,%.1f] y[%.1f,%.1f]" %
      (len(curves), allpts[:,0].min(), allpts[:,0].max(), allpts[:,1].min(), allpts[:,1].max()))

# 凸包外轮廓 (通用锚点)
hull = ConvexHull(allpts)
H = np.vstack([allpts[hull.vertices], allpts[hull.vertices][0]])
he = [(H[i], H[i+1]) for i in range(len(H)-1)]
def dist_to_hull(pt):
    best = 1e9
    for a, b in he:
        ab = b - a
        t = np.clip(np.dot(pt - a, ab) / np.dot(ab, ab), 0, 1)
        proj = a + t * ab
        d = math.hypot(pt[0] - proj[0], pt[1] - proj[1])
        if d < best:
            best = d
    return best
def on_hull(p):
    return np.mean([1.0 if dist_to_hull(pt) < BELT_TOL else 0.0 for pt in p]) >= BELT_FRAC

# ---------------- 逐线特征 ----------------
feat = {}
for lid, p in curves.items():
    cx, cy = p[:, 0].mean(), p[:, 1].mean()
    x0, x1 = p[:, 0].min(), p[:, 0].max()
    y0, y1 = p[:, 1].min(), p[:, 1].max()
    w, h = x1 - x0, y1 - y0
    md = max(w, h)
    gl = sum(math.hypot(p[i+1, 0]-p[i, 0], p[i+1, 1]-p[i, 1]) for i in range(len(p)-1))
    on = on_hull(p)
    feat[lid] = dict(cx=cx, cy=cy, w=w, h=h, md=md, gl=gl, on=on,
                     sp=tuple(p[0]), ep=tuple(p[-1]), pts=p)

# ---------------- 连通分量 (端点焊接, 4mm) ----------------
parent = {}
def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb
nonbelt = [l for l in feat if not feat[l]["on"]]
for l in nonbelt:
    parent[l] = l
def key2(pt):
    return (round(pt[0]/4)*4, round(pt[1]/4)*4)
grid = defaultdict(list)
for l in nonbelt:
    for pt in (feat[l]["sp"], feat[l]["ep"]):
        grid[key2(pt)].append(l)
for k, lst in grid.items():
    for i in range(len(lst)):
        for j in range(i+1, len(lst)):
            union(lst[i], lst[j])
comp = defaultdict(list)
for l in nonbelt:
    comp[find(l)].append(l)

def circ_of(mem):
    pts = np.vstack([feat[m]["pts"] for m in mem])
    if len(pts) < 3:
        return 0.0, 0.0
    try:
        hh = ConvexHull(pts)
        hp = pts[hh.vertices]
    except Exception:
        return 0.0, 0.0
    area = hh.volume
    perim = sum(math.hypot(hp[i][0]-hp[(i+1) % len(hp)][0], hp[i][1]-hp[(i+1) % len(hp)][1])
                for i in range(len(hp)))
    if perim < 1e-6:
        return 0.0, 0.0
    circ = 4 * math.pi * area / (perim * perim)
    diam = 0.0
    n = min(len(pts), 30)
    for i in range(n):
        for j in range(i+1, n):
            d = math.hypot(pts[i][0]-pts[j][0], pts[i][1]-pts[j][1])
            if d > diam:
                diam = d
    return circ, diam

# ---------------- TETHER boss: 顶部带内高圆度小分量 ----------------
boss_set = set()
for r, mem in comp.items():
    if len(mem) < 2:
        continue
    cys = [feat[m]["cy"] for m in mem]
    if max(cys) < BOSS_Y:
        continue
    circ, diam = circ_of(mem)
    if circ >= BOSS_CIRC and BOSS_DMIN <= diam <= BOSS_DMAX:
        boss_set.update(mem)

# ---------------- d_belt (以真实外轮廓为基准) ----------------
belt_pts = np.vstack([feat[l]["pts"] for l in feat if feat[l]["on"]])
for lid, f in feat.items():
    if f["on"]:
        f["db"] = 0.0
    else:
        pc = f["pts"]
        f["db"] = float(np.min(np.hypot(
            belt_pts[:, 0][None, :] - pc[:, 0][:, None],
            belt_pts[:, 1][None, :] - pc[:, 1][:, None])))

# ---------------- 分类 ----------------
# 优先级: BELT(凸包外缘) > TETHER(凸台小圆分量) > TETHER(右侧长条) > CAVITY(d_belt<CAVITY_D) > SEAM
line_comp = {}
for lid, f in feat.items():
    if f["on"]:
        cls = "BELT"
    elif lid in boss_set:
        cls = "TETHER"
    elif f["cx"] > allpts[:, 0].max() - RIGHT_W and f["md"] / max(min(f["w"], f["h"]), 1e-6) > RIGHT_ASP and f["gl"] > RIGHT_LEN:
        cls = "TETHER"
    elif f["db"] < CAVITY_D:
        cls = "CAVITY"
    else:
        cls = "SEAM"
    line_comp[str(lid)] = cls

from collections import Counter
cnt = Counter(line_comp.values())
print("种子分类: BELT=%d CAVITY=%d SEAM=%d TETHER=%d (合计 %d)" %
      (cnt.get("BELT", 0), cnt.get("CAVITY", 0), cnt.get("SEAM", 0),
       cnt.get("TETHER", 0), len(line_comp)))
print("  (boss components 命中 %d 条曲线)" % len(boss_set))

json.dump({"line_comp": line_comp}, open(os.path.join(OUT, SEED), "w"), ensure_ascii=False, indent=0)
print("written out/%s" % SEED)
