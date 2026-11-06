# -*- coding: utf-8 -*-
"""Export classify_final.json -> Tcl id lists for t07_make_comps.tcl."""
import json, os
BASE = os.environ.get("WORKDIR", ".") + "/out/"
cls = json.load(open(BASE + "classify_final.json"))["line_comp"]

groups = {"BELT": [], "CAVITY": [], "SEAM": [], "TETHER": []}
for lid, c in cls.items():
    assert c in groups, "unknown class: %s (L%s)" % (c, lid)
    groups[c].append(int(lid))

# verify: ids unique, and cover exactly the json key set (no 828-style hardcode)
tot = sum(len(v) for v in groups.values())
print("counts:", {k: len(v) for k, v in groups.items()}, "total:", tot)
allids = sorted(i for v in groups.values() for i in v)
assert len(allids) == len(set(allids)), "duplicate ids"
assert allids == sorted(int(k) for k in cls), "id set mismatch vs json"

with open(BASE + "class_lists.tcl", "w", encoding="utf-8") as f:
    for k in ("BELT", "CAVITY", "SEAM", "TETHER"):
        ids = sorted(groups[k])
        f.write("set %s_IDS {%s}\n" % (k, " ".join(str(i) for i in ids)))
        f.write("set %s_N %d\n" % (k, len(ids)))
print("wrote", BASE + "class_lists.tcl")
