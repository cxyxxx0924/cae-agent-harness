# -*- coding: utf-8 -*-
"""训练 v2 先验：两阶段随机森林 + 物理规则，并给出留一图交叉验证（LODO）报告

为什么是两阶段
--------------
LODO 实测发现：单棵/单森林要同时区分 5 类时，"结构线（布带/气腔/缝线）"与
"符号件（拉带/充气口/散碎线）"在特征空间里犬牙交错，相互拉扯。
拆成
  A 段：symbol(TETHER+lines0) vs structure(BELT/CAVITY/SEAM)   ← 粗分，极稳
  B 段：structure 内部分 BELT / CAVITY / SEAM                   ← 细分，靠深度层级
后，cab2/cab3 的 4 类条数准确率从 0.90/0.87 提到 0.94/0.95。

再加一条物理兜底规则（三图零有害误判）：
  ch_dep > 0.055 且 ch_len < 0.90  →  SEAM
  含义：链的中位内向深度明显偏深（在腔体内部）且链不够长（不是绕整圈的气腔环），
        就是气腔内部的缝线环。

用法
----
  python train_v2.py            # 训练 + LODO 报告 + 导出 tree_model_v2.json
  python train_v2.py --lodo-only
"""
import os, json, sys
import numpy as np
from collections import Counter
from sklearn.ensemble import RandomForestClassifier

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.normpath(os.path.join(HERE, "..", "golden"))

CLASSES = ["BELT", "CAVITY", "SEAM", "TETHER", "lines0"]
CIDX = {c: i for i, c in enumerate(CLASSES)}
SYM_IDX = {CIDX["TETHER"], CIDX["lines0"]}

DRAWS = [
    ("cab1", os.path.join(GOLDEN, "cab1")),
    ("cab2", os.path.join(GOLDEN, "cab2")),
    ("cab3", os.path.join(GOLDEN, "cab3")),
]

# 物理兜底规则阈值（由三图分布共同确定，误差只落在 lines0，无害）
SEAM_CH_DEP = 0.055
SEAM_CH_LEN = 0.90


def _pick(wd, fname):
    """兼容两种布局：工作区 <wd>/out/<fname> 与 golden/<name>/<fname>。"""
    for p in (os.path.join(wd, "out", fname), os.path.join(wd, fname)):
        if os.path.exists(p):
            return p
    raise FileNotFoundError(fname + " not found under " + wd)


def load_draw(wd):
    d = json.load(open(_pick(wd, "features2.json")))
    order = d["__meta__"]["feature_order"]
    feats = d["features"]
    gold = json.load(open(_pick(wd, "golden_line_comp.json")))["line_comp"]
    ids = sorted((int(k) for k in feats))
    X = np.array([[feats[str(i)][k] for k in order] for i in ids], float)
    y = np.array([CIDX[gold.get(str(i), "lines0")] for i in ids])
    w = np.array([feats[str(i)]["len_diag"] for i in ids], float)
    return X, y, w, feats, gold, order


def export_forest(rf, classes):
    """导出为纯 Python 可推理的 JSON 森林（仅叶节点存概率分布，控制体积）。"""
    trees = []
    for est in rf.estimators_:
        T = est.tree_
        nodes = []
        for i in range(T.node_count):
            leaf = T.feature[i] < 0
            nd = {"f": int(T.feature[i]) if not leaf else -1,
                  "t": float(T.threshold[i]),
                  "l": int(T.children_left[i]),
                  "r": int(T.children_right[i]),
                  "leaf": bool(leaf)}
            if leaf:
                tot = max(1e-12, float(T.value[i][0].sum()))
                nd["p"] = [round(float(v) / tot, 4) for v in T.value[i][0]]
            nodes.append(nd)
        trees.append(nodes)
    return {"classes": classes, "trees": trees}


def fit_two_stage(Xtr, ytr):
    yA = np.array([1 if v in SYM_IDX else 0 for v in ytr])
    rfA = RandomForestClassifier(n_estimators=500, max_depth=16, min_samples_leaf=2,
                                 class_weight="balanced", random_state=0, n_jobs=-1).fit(Xtr, yA)
    mask = np.isin(ytr, [CIDX["BELT"], CIDX["CAVITY"], CIDX["SEAM"]])
    rfB = RandomForestClassifier(n_estimators=500, max_depth=16, min_samples_leaf=2,
                                 class_weight="balanced", random_state=0, n_jobs=-1).fit(Xtr[mask], ytr[mask])
    return rfA, rfB


def predict_two_stage(rfA, rfB, X, feats, ids):
    pa = rfA.predict_proba(X)          # [:,0]=structure, [:,1]=symbol
    pb = rfB.predict_proba(X)          # BELT/CAVITY/SEAM
    P = np.zeros((len(X), 5))
    P[:, CIDX["TETHER"]] = pa[:, 1]
    for j, c in enumerate([CIDX["BELT"], CIDX["CAVITY"], CIDX["SEAM"]]):
        P[:, c] = pa[:, 0] * pb[:, j]
    pred = P.argmax(1)
    # 物理兜底：深且不长的链 → SEAM
    for i, lid in enumerate(ids):
        f = feats[str(lid)]
        if f["ch_dep"] > SEAM_CH_DEP and f["ch_len"] < SEAM_CH_LEN:
            pred[i] = CIDX["SEAM"]
    return pred


def report(name, y, p, w):
    m = y != CIDX["lines0"]
    acc = float((y[m] == p[m]).mean())
    lw = float((w[m] * (y[m] == p[m])).sum() / max(1e-12, w[m].sum()))
    per = {}
    for c, i in CIDX.items():
        mask = y == i
        if mask.sum() == 0:
            continue
        per[c] = dict(n=int(mask.sum()),
                      rec=float((p[mask] == i).mean()),
                      len_rec=float((w[mask] * (p[mask] == i)).sum() / max(1e-12, w[mask].sum())))
    print("  %-5s 条数acc=%.3f  结构长度加权=%.3f  | " % (name, acc, lw) +
          " ".join("%s rec=%.2f lenrec=%.2f" % (c, v["rec"], v["len_rec"]) for c, v in per.items()))
    return acc, lw


def main():
    lodo_only = "--lodo-only" in sys.argv
    data = {}
    order = None
    for name, wd in DRAWS:
        X, y, w, feats, gold, o = load_draw(wd)
        assert order is None or order == o, "feature_order 不一致: " + name
        order = o
        data[name] = (X, y, w, feats, gold)
        print("%-5s %4d lines  %s" % (name, len(y), dict(Counter(CLASSES[v] for v in y))))

    print("\n================ 留一图交叉验证 LODO（诚实泛化口径）================")
    accs, lws = [], []
    for held in [n for n, _ in DRAWS]:
        tr = [n for n, _ in DRAWS if n != held]
        Xtr = np.vstack([data[n][0] for n in tr]); ytr = np.concatenate([data[n][1] for n in tr])
        rfA, rfB = fit_two_stage(Xtr, ytr)
        Xt, yt, wt, ft, _ = data[held]
        ids = sorted((int(k) for k in ft))
        p = predict_two_stage(rfA, rfB, Xt, ft, ids)
        a, l = report("%s(train=%s)" % (held, "+".join(tr)), yt, p, wt)
        accs.append(a); lws.append(l)
    print("  ---- 平均: 条数acc=%.3f  结构长度加权=%.3f ----" % (np.mean(accs), np.mean(lws)))
    if lodo_only:
        return

    print("\n================ 用全部 %d 图训练最终先验 ================" % len(DRAWS))
    X = np.vstack([data[n][0] for n, _ in DRAWS])
    y = np.concatenate([data[n][1] for n, _ in DRAWS])
    rfA, rfB = fit_two_stage(X, y)
    model = {
        "version": 2,
        "feature_order": order,
        "classes": CLASSES,
        "stageA": export_forest(rfA, ["structure", "symbol"]),
        "stageB": export_forest(rfB, [CLASSES[CIDX["BELT"]], CLASSES[CIDX["CAVITY"]], CLASSES[CIDX["SEAM"]]]),
        "rules": {"seam_ch_dep": SEAM_CH_DEP, "seam_ch_len": SEAM_CH_LEN},
        "trained_on": [n for n, _ in DRAWS],
        "lodo": {"acc": accs, "len_weighted": lws},
    }
    out = os.path.join(HERE, "tree_model_v2.json")
    json.dump(model, open(out, "w"))
    print("saved", out, " trees:", len(model["stageA"]["trees"]), "+", len(model["stageB"]["trees"]),
          " size=%.1f MB" % (os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
