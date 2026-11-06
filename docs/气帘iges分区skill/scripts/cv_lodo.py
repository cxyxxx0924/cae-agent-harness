# -*- coding: utf-8 -*-
"""留一图交叉验证（LODO, leave-one-drawing-out）

对每张图：用其余图训练决策树，预测本图；输出
  - 全类准确率（含 lines0）与"仅已分类线"准确率
  - 逐类 precision / recall / F1
  - 混淆矩阵
  - 每类 top 错分去向（含特征统计，便于定位）
同时给出 naive 基线（全部预测为训练集多数类）作参照。

用法:
  python cv_lodo.py                     # 默认 train3 三图
  python cv_lodo.py --depth 12          # 固定树深
  python cv_lodo.py --auto              # 以 100% 训练拟合为准则自动选深度（同 train_joint）
  python cv_lodo.py --save model.json   # 用全部三图训练并导出模型
"""
import os, sys, json
import numpy as np
from collections import Counter, defaultdict
from sklearn.tree import DecisionTreeClassifier

CLASSES = ["BELT", "CAVITY", "SEAM", "TETHER", "lines0"]
CIDX = {c: i for i, c in enumerate(CLASSES)}
BASE = "E:/work/AI_CAB/onekey/work/train3"

DRAWS = [
    ("cab1", BASE + "/cab1"),
    ("cab2", BASE + "/cab2"),
    ("cab3", BASE + "/cab3"),
]


def load(wd):
    d = json.load(open(wd + "/out/features.json"))
    gold = json.load(open(wd + "/out/golden_line_comp.json"))["line_comp"]
    order = d["__meta__"]["feature_order"]
    feats = d["features"]
    ids = sorted(feats, key=lambda s: int(s))
    X = np.array([[feats[i][k] for k in order] for i in ids], dtype=float)
    y = np.array([CIDX[gold.get(str(i), "lines0")] for i in ids])
    return X, y, ids, order, feats, gold


def metrics(y, p):
    n = len(y)
    acc = float((y == p).sum()) / n
    per = {}
    for c, i in CIDX.items():
        tp = int(((p == i) & (y == i)).sum())
        fp = int(((p == i) & (y != i)).sum())
        fn = int(((p != i) & (y == i)).sum())
        sup = int((y == i).sum())
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        per[c] = dict(tp=tp, fp=fp, fn=fn, support=sup, prec=pr, rec=rc, f1=f1)
    cls_mask = y != CIDX["lines0"]
    acc_cls = float((y[cls_mask] == p[cls_mask]).sum()) / max(1, int(cls_mask.sum()))
    return acc, acc_cls, per


def show(name, y, p, feats, ids, gold):
    acc, acc_cls, per = metrics(y, p)
    print("\n--- %s ---" % name)
    print("  overall acc (incl lines0) = %.4f | classified-only acc = %.4f" % (acc, acc_cls))
    print("  %-7s %5s %5s %5s  %6s %6s %6s" % ("class", "tp", "fp", "fn", "prec", "rec", "f1"))
    for c in CLASSES:
        m = per[c]
        print("  %-7s %5d %5d %5d  %6.3f %6.3f %6.3f" % (
            c, m["tp"], m["fp"], m["fn"], m["prec"], m["rec"], m["f1"]))
    print("  confusion (row=true, col=pred):")
    print("  %-8s" % "" + "".join("%9s" % c for c in CLASSES))
    for c, i in CIDX.items():
        row = [int(((y == i) & (p == j)).sum()) for j in range(len(CLASSES))]
        print("  %-8s" % c + "".join("%9d" % v for v in row))
    # 错分明细（top 组合）
    pairs = defaultdict(int)
    for k in range(len(y)):
        if y[k] != p[k]:
            pairs[(CLASSES[y[k]], CLASSES[p[k]])] += 1
    if pairs:
        print("  top confusions:")
        for (a, b), n in sorted(pairs.items(), key=lambda t: -t[1])[:6]:
            print("     %s -> %s : %d" % (a, b, n))


def fit(X, y, depth, auto=False):
    if not auto:
        clf = DecisionTreeClassifier(max_depth=depth, min_samples_leaf=1, random_state=0)
        clf.fit(X, y)
        return clf
    for d in (8, 10, 12, 14, 16, 20, 24, 30):
        clf = DecisionTreeClassifier(max_depth=d, min_samples_leaf=1, random_state=0)
        clf.fit(X, y)
        if clf.score(X, y) >= 0.9999:
            return clf
    return clf


def main():
    depth = 12
    auto = False
    save = None
    for i, a in enumerate(sys.argv[1:]):
        if a == "--depth":
            depth = int(sys.argv[i + 2])
        elif a == "--auto":
            auto = True
        elif a == "--save":
            save = sys.argv[i + 2]

    data = {}
    order = None
    for name, wd in DRAWS:
        X, y, ids, o, feats, gold = load(wd)
        assert order is None or order == o, "feature_order mismatch: " + name
        order = o
        data[name] = (X, y, ids, feats, gold)
        print("%s: %d lines, class counts=%s" % (
            name, len(y), {c: int((y == CIDX[c]).sum()) for c in CLASSES}))

    if save:
        Xs = np.vstack([data[n][0] for n, _ in DRAWS])
        ys = np.concatenate([data[n][1] for n, _ in DRAWS])
        clf = fit(Xs, ys, depth, auto)
        T = clf.tree_
        nodes = [{"fid": int(T.feature[i]) if T.feature[i] >= 0 else -1,
                  "thr": float(T.threshold[i]),
                  "left": int(T.children_left[i]), "right": int(T.children_right[i]),
                  "leaf": bool(T.feature[i] < 0),
                  "dist": [int(v) for v in T.value[i][0]]} for i in range(T.node_count)]
        json.dump({"feature_order": order, "classes": CLASSES, "nodes": nodes,
                   "trained_on": [n for n, _ in DRAWS]}, open(save, "w"), indent=0)
        print("saved %s  nodes=%d  train_acc=%.4f" % (save, len(nodes), clf.score(Xs, ys)))
        return

    print("\n================ LEAVE-ONE-DRAWING-OUT ================")
    for held, wd in DRAWS:
        tr = [n for n, _ in DRAWS if n != held]
        Xtr = np.vstack([data[n][0] for n in tr])
        ytr = np.concatenate([data[n][1] for n in tr])
        clf = fit(Xtr, ytr, depth, auto)
        Xte, yte, ids, feats, gold = data[held]
        p = clf.predict(Xte)
        show("%s  (train on %s, depth=%s)" % (held, "+".join(tr),
                                              "auto:%d" % clf.get_depth() if auto else depth),
             yte, p, feats, ids, gold)
        # naive baseline
        maj = Counter(ytr).most_common(1)[0][0]
        pn = np.full_like(yte, maj)
        print("  [naive all=%s] acc_cls=%.4f" % (CLASSES[maj], metrics(yte, pn)[1]))


if __name__ == "__main__":
    main()
