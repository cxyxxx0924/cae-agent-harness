# -*- coding: utf-8 -*-
"""Joint supervised fit on THREE goldens: NEW_CAB v14 + cab1 (5P-BAG manual) + cab3 (6P manual).
Learns a shared geometric->class judgment across drawings to strengthen generalization
(esp. the BELT-vs-hardware boundary and the TETHER dense-web signature).
Writes tree_model_joint.json (does NOT overwrite the shipped default until validated).
"""
import os, json, sys
import numpy as np
from sklearn.tree import DecisionTreeClassifier, export_text

# 训练集全部沉淀在技能目录 golden/ 下（自包含：整体复制技能文件夹即带走全部能力）
HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.normpath(os.path.join(HERE, "..", "golden"))

CLASSES = ["BELT", "CAVITY", "SEAM", "TETHER", "lines0"]
cidx = {c: i for i, c in enumerate(CLASSES)}

DRAWS = [
    # (label, features.json, golden line_comp json) —— 均在 golden/ 内
    ("newcab", os.path.join(GOLDEN, "newcab", "features.json"),
               os.path.join(GOLDEN, "newcab", "classify_v14.json")),
    ("cab1",   os.path.join(GOLDEN, "cab1", "features.json"),
               os.path.join(GOLDEN, "cab1", "golden_line_comp.json")),
    ("cab3",   os.path.join(GOLDEN, "cab3", "features.json"),
               os.path.join(GOLDEN, "cab3", "golden_line_comp.json")),
]

X_all, y_all, meta_order = [], [], None
per_draw = {}
for label, fpath, gpath in DRAWS:
    d = json.load(open(fpath))
    meta = d["__meta__"]
    feats = d["features"]
    forder = meta["feature_order"]
    if meta_order is None:
        meta_order = forder
    assert meta_order == forder, "%s feature_order mismatch" % label
    gold = json.load(open(gpath))["line_comp"]
    Xd, yd = [], []
    for lid, fv in feats.items():
        Xd.append([fv[k] for k in forder])
        yd.append(cidx[gold.get(str(lid), "lines0")])
    per_draw[label] = (np.array(Xd), np.array(yd))
    X_all.extend(Xd); y_all.extend(yd)
    print("%s: %d samples, class counts=%s" % (label, len(yd),
          {c: int((np.array(yd) == i).sum()) for i, c in enumerate(CLASSES)}))

X = np.array(X_all, dtype=float)
y = np.array(y_all)
print("POOLED total:", len(y))

best = None
for depth in (8, 10, 12, 14, 16, 20, 24):
    clf = DecisionTreeClassifier(max_depth=depth, min_samples_leaf=1, random_state=0)
    clf.fit(X, y)
    acc = clf.score(X, y)
    print("depth=%d  train_acc=%.4f" % (depth, acc))
    if acc >= 0.9999 and best is None:
        best = (depth, clf)
if best is None:
    clf = DecisionTreeClassifier(max_depth=24, min_samples_leaf=1, random_state=0)
    clf.fit(X, y); best = (24, clf)
depth, clf = best
print("FINAL depth=%d train_acc=%.4f" % (depth, clf.score(X, y)))

# per-drawing accuracy (both are in-training, should be ~100%)
for label, (Xd, yd) in per_draw.items():
    print("%s hold-in acc=%.4f" % (label, clf.score(Xd, yd)))

print("\n=== LEARNED RULES (depth<=10) ===")
print(export_text(clf, feature_names=meta_order, max_depth=10))

T = clf.tree_
nodes = []
for i in range(T.node_count):
    nodes.append({
        "fid": int(T.feature[i]) if T.feature[i] >= 0 else -1,
        "thr": float(T.threshold[i]),
        "left": int(T.children_left[i]),
        "right": int(T.children_right[i]),
        "leaf": bool(T.feature[i] < 0),
        "dist": [int(v) for v in T.value[i][0]],
    })
out = {"feature_order": meta_order, "classes": CLASSES, "nodes": nodes,
       "trained_on": [d[0] for d in DRAWS]}
json.dump(out, open(os.path.dirname(os.path.abspath(__file__)) + "/tree_model_joint.json", "w"), indent=0)
print("\nsaved tree_model_joint.json with", len(nodes), "nodes")
