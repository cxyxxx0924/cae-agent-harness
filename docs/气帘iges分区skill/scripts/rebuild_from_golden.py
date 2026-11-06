# -*- coding: utf-8 -*-
"""自包含校验：只用手册里的 golden/<name>/ 数据，离线复算特征并与存档比对。

证明三件事（不依赖 HyperMesh、不依赖任何外部工作区）：
  1. `golden/<name>/lines_pts.txt` 足以重算全部 v2 特征（featurize2 的唯一输入）；
  2. 复算结果与 `golden/<name>/features2.json` 数值一致（容差 1e-9）；
  3. `golden_line_comp.json` 的线号与特征线号完全对齐（标签与特征同一 id 空间）。

用法:
  python scripts/rebuild_from_golden.py            # 校验三图
  python scripts/rebuild_from_golden.py cab2       # 只校验一张
"""
import os, sys, json, shutil, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.normpath(os.path.join(HERE, ".."))
GOLDEN = os.path.join(SKILL, "golden")
sys.path.insert(0, HERE)
import featurize2  # noqa: E402

DRAWS = ["cab1", "cab2", "cab3"]
TOL = 1e-9


def check(name):
    g = os.path.join(GOLDEN, name)
    pts = os.path.join(g, "lines_pts.txt")
    ref_p = os.path.join(g, "features2.json")
    for p in (pts, ref_p):
        if not os.path.exists(p):
            print("[SKIP] %-5s 缺少 %s" % (name, os.path.basename(p)))
            return None

    tmp = tempfile.mkdtemp(prefix="rebuild_%s_" % name)
    try:
        os.makedirs(os.path.join(tmp, "out"), exist_ok=True)
        shutil.copy(pts, os.path.join(tmp, "out", "lines_pts.txt"))
        meta, feats = featurize2.compute_features(tmp, verbose=False)
        ref = json.load(open(ref_p, encoding="utf-8"))

        # 1) 线号空间
        a = set(int(k) for k in feats)
        b = set(int(k) for k in ref["features"])
        if a != b:
            print("[FAIL] %-5s 线号空间不一致：仅复算 %d / 仅存档 %d" % (name, len(a - b), len(b - a)))
            return False

        # 2) 元数据（平面/线数/图幅）
        rm = ref["__meta__"]
        meta_bad = []
        for k in ("use_z", "n_lines"):
            if rm.get(k) != meta.get(k):
                meta_bad.append("%s: %r→%r" % (k, rm.get(k), meta.get(k)))
        for k in ("diag", "med_len"):
            if abs(float(rm.get(k, 0)) - float(meta.get(k, 0))) > 1e-6:
                meta_bad.append("%s: %.6f→%.6f" % (k, rm.get(k, 0), meta.get(k, 0)))
        if meta_bad:
            print("[FAIL] %-5s 元数据不一致：%s" % (name, "; ".join(meta_bad)))
            return False

        # 3) 逐特征数值
        order = ref["__meta__"]["feature_order"]
        if order != meta["feature_order"]:
            print("[FAIL] %-5s feature_order 变了（模型需要重训）" % name)
            return False
        ids = sorted(a)
        X = np.array([[feats[i][k] for k in order] for i in ids], float)
        Y = np.array([[ref["features"][str(i)][k] for k in order] for i in ids], float)
        d = np.abs(X - Y)
        worst = float(d.max()) if d.size else 0.0
        bad = np.argwhere(d > TOL)
        if bad.size:
            j = bad[0][1]
            print("[FAIL] %-5s 特征不一致：%d 个单元超差，最大 %.3e（首例 %s 线 %d）"
                  % (name, bad.shape[0], worst, order[j], ids[bad[0][0]]))
            return False

        # 4) 标签对齐
        gold = json.load(open(os.path.join(g, "golden_line_comp.json"), encoding="utf-8"))["line_comp"]
        if set(int(k) for k in gold) != a:
            print("[FAIL] %-5s 金标签与特征线号不齐" % name)
            return False

        print("[OK]   %-5s %d 线 × %d 特征，离线复算与存档完全一致（max|Δ|=%.1e）；标签对齐"
              % (name, len(ids), len(order), worst))
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    names = [sys.argv[1]] if len(sys.argv) > 1 else DRAWS
    res = [check(n) for n in names]
    ok = all(r for r in res if r is not None)
    print("---- 自包含校验：%s ----" % ("全部通过" if ok else "存在失败项"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
