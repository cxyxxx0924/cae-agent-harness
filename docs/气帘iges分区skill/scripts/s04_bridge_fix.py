"""S4 桥接修正: 复刻 p03_bridge_scan 的平滑搭接判定, 对【非 BELT】曲线,
若其两端都平滑接到同一个其它类 B, 则判定为 B 的环碎片, 重分类为 B。
BELT(外缘) 不参与重分类(用户已确认外缘正确)。
输出: out/classify_final.json (= 修正后种子)
"""
import os, json
from collections import defaultdict

BASE = os.environ.get("WORKDIR", os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out")

feat = {}
for ln in open(os.path.join(OUT, "geom_features.txt"), encoding="utf-8"):
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

src = os.environ.get("SRC", "classify_prev.json")
cls = json.load(open(os.path.join(OUT, src), encoding="utf-8"))["line_comp"]
CLS = {int(k): v for k, v in cls.items()}

TOL = 8.0
def smooth(lid, end, o, oe):
    e = feat[lid][end]; p = feat[o][oe]
    if abs(e[0]-p[0]) > TOL or abs(e[1]-p[1]) > TOL:
        return False
    mine = feat[lid]["ts"] if end == "sp" else feat[lid]["te"]
    tt = feat[o]["ts"] if oe == "sp" else feat[o]["te"]
    dot = mine[0]*tt[0] + mine[1]*tt[1]
    expect = 1.0 if (end == "ep") != (oe == "ep") else -1.0
    return abs(dot - expect) < 0.02

nbr = defaultdict(list)
for lid in feat:
    for end in ("sp", "ep"):
        for o in feat:
            if o == lid:
                continue
            for oe in ("sp", "ep"):
                if smooth(lid, end, o, oe):
                    nbr[lid].append((end, o, oe))

fixed = []
for lid in sorted(feat):
    a = CLS.get(lid)
    if a == "BELT":
        continue
    ends = {}
    for end, o, oe in nbr[lid]:
        b = CLS.get(o)
        if b and b != a:
            ends.setdefault(end, []).append(b)
    if len(ends) == 2:
        bs = {b for v in ends.values() for b in v}
        if len(bs) == 1:
            b = bs.pop()
            # 硬约束: 涉及 BELT 的桥接跳过(外缘已确认, 嵌套边界本身含糊, 不自动改)
            if b == "BELT" or a == "BELT":
                continue
            # TETHER 护栏: 仅当自身为小尺寸(最大维度 < 30mm)才允许被桥接判为 TETHER,
            # 防止顶部长横线/大弧段经端点邻接被错误扩散成 TETHER
            if b == "TETHER":
                f0 = feat[lid]
                dx = abs(f0["sp"][0]-f0["ep"][0]); dy = abs(f0["sp"][1]-f0["ep"][1])
                if max(dx, dy) > 30.0:
                    continue
            if b != a:
                CLS[lid] = b
                fixed.append((lid, a, b, feat[lid]["L"]))

# 写回
json.dump({"line_comp": {str(k): v for k, v in CLS.items()}},
          open(os.path.join(OUT, "classify_final.json"), "w"), ensure_ascii=False, indent=0)

from collections import Counter
cnt = Counter(CLS.values())
print("修正后分类: BELT=%d CAVITY=%d SEAM=%d TETHER=%d (合计 %d)" %
      (cnt.get("BELT",0), cnt.get("CAVITY",0), cnt.get("SEAM",0), cnt.get("TETHER",0), len(CLS)))
print("桥接修正 %d 条:" % len(fixed))
for lid, a, b, L in fixed:
    print("  L%d %s -> %s  (L=%.2f)" % (lid, a, b, L))
