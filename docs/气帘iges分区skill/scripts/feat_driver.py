# -*- coding: utf-8 -*-
"""Generic featurize driver: featurize any workdir -> <workdir>/out/features.json.
Usage: python feat_driver.py <workdir>
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import featurize as F
wd = sys.argv[1].rstrip("/\\")
meta, feats = F.compute_features(wd)
out = os.path.join(wd, "out")
os.makedirs(out, exist_ok=True)
json.dump({"__meta__": meta, "features": {str(k): v for k, v in feats.items()}},
          open(os.path.join(out, "features.json"), "w"))
print("featurized", wd, "| lines", meta["n_lines"], "| plane",
      "X-Z" if meta["use_z"] else "X-Y", "| feature_order", meta["feature_order"])
