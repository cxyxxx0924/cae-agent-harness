# -*- coding: utf-8 -*-
"""AUTO_PARTITION — 气帘 CAD 曲线四分区自动识别 (视觉/功能/连贯性 先验模块)
=====================================================================
输入: <WORKDIR>/out/lines_pts.txt  (S0-S2 导出的全量采样点)
输出: <WORKDIR>/out/classify_final.json  ({line_comp:{id:CLASS}})  仅 BELT/CAVITY/SEAM/TETHER
      lines0 (未分区) 的线不写入，留在原 comp。

方法:
  - 自动判定坐标平面 (X-Y / X-Z)
  - 端点焊接(8mm) -> 连通分量 -> 连贯性/切线连续度
  - 逐线几何+视觉+功能特征 (长度/径向壳层/凸包距离/长宽比/位置/分量大小...)
  - 应用"从金标准(newcab v14)监督学得的决策树" 做四分类 (tree_model.json)
  - 全程无需人工确认, 可对任意同类气帘 IGS 通用.

依赖: 仅 numpy + 标准库 (树以 JSON 序列化, 零 sklearn 运行时依赖)
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import featurize

HERE = os.path.dirname(os.path.abspath(__file__))
TREE_PATH = os.environ.get("TREE_MODEL", os.path.join(HERE, "tree_model.json"))

def load_tree(path):
    m = json.load(open(path))
    return m["feature_order"], m["classes"], m["nodes"]

def predict(fo, classes, nodes, feat_vec):
    i = 0
    while not nodes[i]["leaf"]:
        fid = nodes[i]["fid"]
        thr = nodes[i]["thr"]
        v = feat_vec[fid]
        i = nodes[i]["left"] if v <= thr else nodes[i]["right"]
    dist = nodes[i]["dist"]
    return classes[int(np.argmax(dist))]

def main():
    workdir = os.environ.get("WORKDIR")
    if not workdir:
        # default: this script's own dir (for quick tests)
        workdir = os.path.dirname(os.path.abspath(__file__))
    workdir = workdir.rstrip("/\\")
    out = workdir + "/out"
    if not os.path.exists(out + "/lines_pts.txt"):
        # try parent/out
        alt = os.path.dirname(workdir) + "/out"
        if os.path.exists(alt + "/lines_pts.txt"):
            out = alt
        else:
            raise FileNotFoundError(out + "/lines_pts.txt (run S0-S2 first)")

    fo, classes, nodes = load_tree(TREE_PATH)
    meta, feats = featurize.compute_features(workdir)
    print("[auto_partition] plane:", "X-Z" if meta["use_z"] else "X-Y",
          "lines:", meta["n_lines"], "tree nodes:", len(nodes))

    line_comp = {}
    counts = {"BELT": 0, "CAVITY": 0, "SEAM": 0, "TETHER": 0, "lines0": 0}
    for lid, f in feats.items():
        vec = [f[k] for k in fo]
        cls = predict(fo, classes, nodes, vec)
        counts[cls] += 1
        if cls in ("BELT", "CAVITY", "SEAM", "TETHER"):
            line_comp[str(lid)] = cls
        # lines0 -> 不写入 (留在原 comp, 不参与分区)

    out_json = {"version": "auto", "line_comp": line_comp}
    with open(out + "/classify_final.json", "w") as fp:
        json.dump(out_json, fp, indent=0)
    print("[auto_partition] counts:", counts)
    print("[auto_partition] classified (4 groups):",
          sum(counts[c] for c in ("BELT", "CAVITY", "SEAM", "TETHER")))
    print("[auto_partition] wrote", out + "/classify_final.json")

if __name__ == "__main__":
    main()
