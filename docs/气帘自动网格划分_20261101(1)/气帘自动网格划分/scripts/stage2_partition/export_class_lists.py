# -*- coding: utf-8 -*-
"""Export newcab_classify8.json -> Tcl id lists for make_comps.tcl."""
import json
BASE = "./newcab/out/"
cls = json.load(open(BASE + "newcab_classify8.json"))["line_comp"]

groups = {"BELT": [], "CAVITY": [], "SEAM": [], "TETHER": []}
for lid, c in cls.items():
    groups[c].append(int(lid))

# verify total
tot = sum(len(v) for v in groups.values())
print("counts:", {k: len(v) for k, v in groups.items()}, "total:", tot)
assert tot == 828, "total != 828"
# check all ids unique and in 1..828
allids = sorted(i for v in groups.values() for i in v)
assert allids == list(range(1, 829)), "id set mismatch"

with open(BASE + "newcab_class_lists.tcl", "w", encoding="utf-8") as f:
    for k in ("BELT", "CAVITY", "SEAM", "TETHER"):
        ids = sorted(groups[k])
        f.write("set %s_IDS {%s}\n" % (k, " ".join(str(i) for i in ids)))
        f.write("set %s_N %d\n" % (k, len(ids)))
print("wrote", BASE + "newcab_class_lists.tcl")
