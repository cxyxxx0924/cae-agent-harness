# v9_recon.py — NEW_CAB 四问题侦察：把每个问题的候选线全部找出来
# P1 BELT: 顶部独立小竖线 / 右上方断链缺口 / 充气口内部线
# P2 CAVITY: 口部区域所有线（找靠内平行闭合候选）
# P3 SEAM: 气道缝（x>500, y>240 的非哑铃线）
# P4 TETHER: 左下方排气口圆圈 + 与 BELT 主环搭接的碎片
import json, os
from collections import defaultdict

BASE = os.environ.get("WORKDIR", ".") + "/out/"

feat = {}
for ln in open(BASE + "geom_features.txt", encoding="utf-8"):
    if not ln.startswith("LINE "):
        continue
    p = ln.split("|")
    f = p[0].split()
    lid = int(f[1])
    feat[lid] = dict(
        L=float(f[2]),
        sp=tuple(map(float, p[1].split()[:2])),
        ep=tuple(map(float, p[2].split()[:2])),
        ts=tuple(map(float, p[3].split()[:2])),
        te=tuple(map(float, p[4].split()[:2])),
    )

cls = json.load(open(BASE + "classify_final.json", encoding="utf-8"))["line_comp"]
CLS = {int(k): v for k, v in cls.items()}

def seg_in(lid, x0, x1, y0, y1):
    d = feat[lid]
    return (x0 <= d["sp"][0] <= x1 and y0 <= d["sp"][1] <= y1) or \
           (x0 <= d["ep"][0] <= x1 and y0 <= d["ep"][1] <= y1)

print("=" * 70)
print("P1a BELT 顶部独立小竖线候选（BELT 中 length<40 且端点在布带顶边 y[355,400] 一带）")
for lid in sorted(feat):
    if CLS.get(lid) != "BELT":
        continue
    d = feat[lid]
    if d["L"] < 40 and (355 <= max(d["sp"][1], d["ep"][1]) <= 400):
        print(f"  L{lid:<4d} L={d['L']:6.2f} sp({d['sp'][0]:8.2f},{d['sp'][1]:7.2f}) ep({d['ep'][0]:8.2f},{d['ep'][1]:7.2f})")

print()
print("P1b BELT 主环顶边 dangling 短头（y≈382.56, x 900-1500）")
for lid in sorted(feat):
    if CLS.get(lid) != "BELT":
        continue
    d = feat[lid]
    for end, pt in (("sp", d["sp"]), ("ep", d["ep"])):
        if 900 <= pt[0] <= 1500 and 380 <= pt[1] <= 385:
            print(f"  L{lid:<4d}.{end} ({pt[0]:8.2f},{pt[1]:7.2f}) L={d['L']:7.2f}")

print()
print("P1c 布带右缘/右上区域 TETHER 线（可能该还 BELT, x[1400,1700] y[300,500]）")
for lid in sorted(feat):
    if CLS.get(lid) != "TETHER":
        continue
    if seg_in(lid, 1400, 1700, 300, 500):
        d = feat[lid]
        print(f"  L{lid:<4d} L={d['L']:7.2f} sp({d['sp'][0]:8.2f},{d['sp'][1]:7.2f}) ep({d['ep'][0]:8.2f},{d['ep'][1]:7.2f})")

print()
print("P1d 充气口区域 BELT 线全景（x[430,970] y[330,520]）— 区分最外轮廓 vs 内部")
for lid in sorted(feat):
    if CLS.get(lid) != "BELT":
        continue
    if seg_in(lid, 430, 970, 330, 520):
        d = feat[lid]
        print(f"  L{lid:<4d} L={d['L']:7.2f} sp({d['sp'][0]:8.2f},{d['sp'][1]:7.2f}) ep({d['ep'][0]:8.2f},{d['ep'][1]:7.2f})")

print()
print("=" * 70)
print("P2 充气口区域全部线（各分类，x[430,970] y[330,520]）— 找靠内平行闭合候选")
for lid in sorted(feat):
    if seg_in(lid, 430, 970, 330, 520):
        d = feat[lid]
        print(f"  L{lid:<4d} [{CLS.get(lid):7s}] L={d['L']:7.2f} sp({d['sp'][0]:8.2f},{d['sp'][1]:7.2f}) ep({d['ep'][0]:8.2f},{d['ep'][1]:7.2f})")

print()
print("=" * 70)
print("P3 SEAM 气道缝候选（SEAM 中 y>230 的线，即非 4 哑铃主体）")
for lid in sorted(feat):
    if CLS.get(lid) != "SEAM":
        continue
    d = feat[lid]
    if max(d["sp"][1], d["ep"][1]) > 230:
        print(f"  L{lid:<4d} L={d['L']:7.2f} sp({d['sp'][0]:8.2f},{d['sp'][1]:7.2f}) ep({d['ep'][0]:8.2f},{d['ep'][1]:7.2f})")

print()
print("=" * 70)
print("P4 左下方区域全部线（x[-350,50] y[-150,60]）— 排气口圆圈定位")
for lid in sorted(feat):
    if seg_in(lid, -350, 50, -150, 60):
        d = feat[lid]
        xs = [d["sp"][0], d["ep"][0]]; ys = [d["sp"][1], d["ep"][1]]
        print(f"  L{lid:<4d} [{CLS.get(lid):7s}] L={d['L']:7.2f} sp({d['sp'][0]:8.2f},{d['sp'][1]:7.2f}) ep({d['ep'][0]:8.2f},{d['ep'][1]:7.2f})")
