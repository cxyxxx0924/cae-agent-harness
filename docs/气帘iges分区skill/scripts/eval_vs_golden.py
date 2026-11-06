# -*- coding: utf-8 -*-
"""逐线比对「自动分类结果」与「人工金标准」，并打印混淆明细与规则命中情况。

用法
----
  python eval_vs_golden.py                                   # 用默认工作根比 golden/ 三图
  python eval_vs_golden.py --pred-root D:/cases/v2_          # 预测结果在 <root><name>/out/classify_final.json
  python eval_vs_golden.py --draws cab2                      # 只比一张
  python eval_vs_golden.py --name cabX --pred <path>/classify_final.json   # 单张显式路径

口径（与 train_v2.py 的 LODO 一致）
----------------------------------
1. 只有金标准里标了具体类别的线参与"一致率"；金标准 `lines0` 是人工"选择忽略"的桶，不计入分母。
   自动结果把 lines0 也判了类，是设计如此（v2 不产出残线），不扣分，只单独统计"覆盖数"。
2. 比对前**显式验证两侧 id 空间完全相等**——历史上因 int/str 键与不同 id 空间产出过大批假差异。
3. 同时报物理兜底规则的命中分布（`ch_dep>0.055 且 ch_len<0.90 → SEAM`），便于判断误伤来自规则还是模型。
"""
import os, sys, json, argparse
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.normpath(os.path.join(HERE, ".."))
GOLDEN = os.path.join(SKILL, "golden")
DEFAULT_ROOT = os.environ.get("PRED_ROOT", "E:/work/AI_CAB/onekey/work/v2_")
SEAM_CH_DEP, SEAM_CH_LEN = 0.055, 0.90


def find_pred(name, root=None):
    """按优先级找预测文件；返回 (path, 来源说明)。

    顺序：外部工作根下的 v2_<name>/ → 技能自带 cases/ → 外部工作根下的旧目录 <name>/
    （最后一档最容易串到 v1 旧结果，命中时会在输出里显式标注）
    """
    cands = []
    if root:
        r = root if root.endswith(("/", "\\")) else root + "/"
        cands.append((os.path.join(r, "v2_" + name, "out", "classify_final.json"), "外部 %sv2_%s（v2 结果）" % (r, name)))
        cands.append((os.path.join(r, "cases", "v2_" + name, "classify_final.json"), "外部 %scases/v2_%s" % (r, name)))
        cands.append((os.path.join(r, name, "out", "classify_final.json"), "外部 %s%s（旧目录，可能是 v1 结果！）" % (r, name)))
    else:
        cands.append((os.path.join(SKILL, "cases", "v2_" + name, "classify_final.json"), "技能自带 cases/v2_%s" % name))
    cands.append((os.path.join(DEFAULT_ROOT + name, "out", "classify_final.json"), "默认工作根 %s%s" % (DEFAULT_ROOT, name)))
    for p, src in cands:
        if os.path.exists(p):
            return p, src
    return None, None


def load(d):
    return {int(k): v for k, v in json.load(open(d, encoding="utf-8"))["line_comp"].items()}


def eval_one(name, pred_path, src=None):
    gold = load(os.path.join(GOLDEN, name, "golden_line_comp.json"))
    pred = load(pred_path)

    if set(gold) != set(pred):
        only_g = set(gold) - set(pred)
        only_p = set(pred) - set(gold)
        print("[FAIL] %s id 空间不一致：仅金标准 %d 条，仅预测 %d 条（例 %s / %s）"
              % (name, len(only_g), len(only_p), sorted(only_g)[:5], sorted(only_p)[:5]))
        return None

    cls_only = [i for i, v in gold.items() if v != "lines0"]
    n0 = len(gold) - len(cls_only)
    agree = sum(1 for i in cls_only if pred[i] == gold[i])
    conf = Counter((gold[i], pred[i]) for i in cls_only if pred[i] != gold[i])
    cover = sum(1 for i in gold if gold[i] == "lines0" and pred[i] != "lines0")

    acc = agree / max(1, len(cls_only))
    print("%-5s 一致 %4d/%4d = %.3f | 金标准 lines0 被赋类 %3d/%3d | 结构互换 %2d"
          % (name, agree, len(cls_only), acc, cover, n0, sum(conf.values())))
    if src:
        print("      预测来源: %s" % src)
    if conf:
        print("      差异(金标准→预测): " + ", ".join("%s→%s×%d" % (a, b, n) for (a, b), n in conf.most_common()))

    # 规则命中分布（与模型无关，只看特征）
    fp = os.path.join(GOLDEN, name, "features2.json")
    if os.path.exists(fp):
        feats = json.load(open(fp, encoding="utf-8"))["features"]
        hit = [k for k, v in feats.items() if v["ch_dep"] > SEAM_CH_DEP and v["ch_len"] < SEAM_CH_LEN]
        dist = Counter(gold.get(int(k), "?") for k in hit)
        print("      兜底规则命中 %2d 条，金标准分布 %s" % (len(hit), dict(dist)))
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred-root", default=None,
                    help="外部工作根；实际读 <root>/cases/v2_<name>/ 或 <root><name>/out/。"
                         "不传则优先用技能自带 cases/（默认 %s）" % DEFAULT_ROOT)
    ap.add_argument("--draws", default="cab1,cab2,cab3")
    ap.add_argument("--name")
    ap.add_argument("--pred")
    a = ap.parse_args()

    if a.name and a.pred:
        eval_one(a.name, a.pred)
        return

    accs = []
    for name in [s.strip() for s in a.draws.split(",") if s.strip()]:
        p, src = find_pred(name, a.pred_root)
        if not p:
            print("[SKIP] %s 找不到 classify_final.json（可用 --pred-root 指定工作根）" % name)
            continue
        acc = eval_one(name, p, src)
        if acc is not None:
            accs.append(acc)
    if accs:
        print("---- 平均一致率 %.3f（仅统计已分类金标准线）----" % (sum(accs) / len(accs)))


if __name__ == "__main__":
    main()
