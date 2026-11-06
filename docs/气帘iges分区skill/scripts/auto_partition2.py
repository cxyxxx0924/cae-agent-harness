# -*- coding: utf-8 -*-
"""自动四分区 v2（纯 Python 推理，运行期不依赖 sklearn）

链路：featurize2.compute_features → 两阶段随机森林(JSON) → 物理规则兜底 → (可选)邻域平滑
      → <workdir>/out/classify_final.json

用法:
  python auto_partition2.py <workdir> [--smooth 0.3] [--model path.json] [--no-rule]

与 v1 的差别：特征换成 featurize2（轮廓内向深度 / 切向链 / 局部密集度 / 图内百分位），
模型换成两阶段森林 + SEAM 物理规则；LODO 平均条数准确率 0.957（v1 为 0.71~0.82）。
"""
import os, sys, json, math
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import featurize2 as F2

CLASSES = ["BELT", "CAVITY", "SEAM", "TETHER", "lines0"]
CIDX = {c: i for i, c in enumerate(CLASSES)}
DEFAULT_MODEL = os.path.join(HERE, "tree_model_v2.json")


def load_model(path):
    m = json.load(open(path))
    return m


def forest_proba(forest, x):
    ncls = len(forest["classes"])
    acc = [0.0] * ncls
    trees = forest["trees"]
    for tree in trees:
        i = 0
        while True:
            nd = tree[i]
            if nd["leaf"]:
                p = nd["p"]
                for k in range(ncls):
                    acc[k] += p[k]
                break
            i = nd["l"] if x[nd["f"]] <= nd["t"] else nd["r"]
    n = float(len(trees))
    return [v / n for v in acc]


def build_adjacency(workdir, feats, meta):
    """端点焊接得到线-线邻接（供标签平滑用）。"""
    lines = F2.load_lines(workdir)
    use_z = meta["use_z"]
    tol = max(0.004 * meta["diag"], 1e-6)
    P2 = {l: [F2.project(use_z, p) for p in v["pts"]] for l, v in lines.items()}
    ids = sorted((int(k) for k in feats))
    nodes = {}

    def gn(p):
        for k, v in nodes.items():
            if abs(k[0] - p[0]) < tol and abs(k[1] - p[1]) < tol:
                return v
        v = len(nodes); nodes[p] = v; return v

    nd = defaultdict(list)
    for l in ids:
        if l not in P2:
            continue
        nd[gn(P2[l][0])].append(l)
        nd[gn(P2[l][-1])].append(l)
    adj = defaultdict(set)
    for k, ls in nd.items():
        for i in range(len(ls)):
            for j in range(i + 1, len(ls)):
                adj[ls[i]].add(ls[j]); adj[ls[j]].add(ls[i])
    return ids, adj


def smooth_proba(ids, adj, P, alpha, iters=2):
    pos = {l: i for i, l in enumerate(ids)}
    nbr = [[pos[j] for j in adj[l]] for l in ids]
    cur = [row[:] for row in P]
    for _ in range(iters):
        new = []
        for i, row in enumerate(cur):
            if nbr[i]:
                nb = nbr[i]
                agg = [sum(cur[j][k] for j in nb) / len(nb) for k in range(len(row))]
                r = [row[k] + alpha * agg[k] for k in range(len(row))]
            else:
                r = row[:]
            s = sum(r) or 1.0
            new.append([v / s for v in r])
        cur = new
    return cur


def main():
    wd = sys.argv[1].rstrip("/\\")
    alpha = 0.0
    model_path = DEFAULT_MODEL
    no_rule = "--no-rule" in sys.argv
    for i, a in enumerate(sys.argv[2:]):
        if a == "--smooth":
            alpha = float(sys.argv[i + 3])
        elif a == "--model":
            model_path = sys.argv[i + 3]

    model = load_model(model_path)
    order = model["feature_order"]
    meta, feats = F2.compute_features(wd, verbose=True)
    ids = sorted((int(k) for k in feats))

    # 写入特征，便于复现/调试
    outdir = os.path.join(wd, "out")
    os.makedirs(outdir, exist_ok=True)
    json.dump({"__meta__": meta, "features": {str(k): v for k, v in feats.items()}},
              open(os.path.join(outdir, "features2.json"), "w"))

    X = [[feats[l][k] for k in order] for l in ids]
    P = [[0.0] * 5 for _ in ids]
    for i, x in enumerate(X):
        pa = forest_proba(model["stageA"], x)      # [structure, symbol]
        pb = forest_proba(model["stageB"], x)      # BELT/CAVITY/SEAM
        P[i][CIDX["TETHER"]] = pa[1]
        for j, c in enumerate(["BELT", "CAVITY", "SEAM"]):
            P[i][CIDX[c]] = pa[0] * pb[j]

    if alpha > 0:
        ids2, adj = build_adjacency(wd, feats, meta)
        assert ids2 == ids
        P = smooth_proba(ids, adj, P, alpha)

    pred = {}
    for i, l in enumerate(ids):
        ci = max(range(5), key=lambda k: P[i][k])
        pred[l] = CLASSES[ci]

    # 物理规则兜底：深且不长的链 → SEAM
    if not no_rule:
        r = model.get("rules", {})
        th_dep = r.get("seam_ch_dep", 0.055)
        th_len = r.get("seam_ch_len", 0.90)
        moved = 0
        for l in ids:
            f = feats[l]
            if f["ch_dep"] > th_dep and f["ch_len"] < th_len and pred[l] != "SEAM":
                pred[l] = "SEAM"; moved += 1
        print("[rule] ch_dep>%.3f & ch_len<%.2f → SEAM: %d 条被纠正" % (th_dep, th_len, moved))

    # lines0 不写入契约（与 v1 一致：只登记 4 类）
    lc = {str(l): c for l, c in pred.items() if c != "lines0"}
    payload = {"line_comp": lc}
    json.dump(payload, open(os.path.join(outdir, "classify_final.json"), "w"), indent=1)
    json.dump(payload, open(os.path.join(outdir, "classify_v2.json"), "w"), indent=1)

    from collections import Counter
    cnt = Counter(pred.values())
    print("[auto2] %s  lines=%d  %s" % (wd, len(ids), dict(cnt)))
    print("[auto2] wrote classify_final.json (classified=%d, lines0=%d)" % (len(lc), cnt["lines0"]))
    return pred


if __name__ == "__main__":
    main()
