"""Compare an independent HyperMesh readback against the existing K before reuse."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "auto_gate"))
from kio import parse_kfile


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def topology(nodes):
    sequence = tuple(n for n in nodes if n > 0)
    if len(sequence) == 4 and sequence[-1] in (sequence[0], sequence[-2]):
        sequence = sequence[:-1]
    if len(sequence) not in (3, 4) or len(set(sequence)) != len(sequence):
        raise ValueError(f"Invalid shell connectivity: {sequence}")
    return min(sequence[i:] + sequence[:i] for i in range(len(sequence)))


def verify(hm, kfile, readback):
    nodes, elements, element_ids = {}, Counter(), set()
    source, done = None, False
    for line in Path(readback).read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("HM_FILE "):
            source = line[8:]
        elif line == "READBACK_DONE":
            done = True
        elif line.startswith("N "):
            fields = line.split()
            if len(fields) != 5:
                raise ValueError(f"Invalid readback node: {line}")
            nid = int(fields[1])
            if nid in nodes:
                raise ValueError(f"Duplicate readback node: {nid}")
            nodes[nid] = tuple(float(value) for value in fields[2:5])
        elif line.startswith("E "):
            fields = line.split()
            eid = int(fields[1])
            if eid in element_ids:
                raise ValueError(f"Duplicate readback element: {eid}")
            element_ids.add(eid)
            elements[topology(map(int, fields[2:]))] += 1
    k = parse_kfile(kfile)
    failures = []
    if not source or Path(source).resolve() != Path(hm).resolve() or not done:
        failures.append("Missing or mismatched independent HyperMesh readback")
    if not nodes or not elements or set(nodes) != set(k["nodes"]):
        failures.append("Node IDs differ between HM and K")
    elif any(not all(math.isfinite(v) for v in xyz + k["nodes"][nid]) or math.dist(xyz, k["nodes"][nid]) > 0.001 for nid, xyz in nodes.items()):
        failures.append("Node coordinates differ between HM and K")
    expected = Counter(topology(element) for group in k["elems"].values() for element in group)
    if elements != expected:
        failures.append("Shell connectivity differs between HM and K")
    return {
        "schema": "cae.mesh-readback.v1", "overall": "FAIL" if failures else "PASS",
        "hm_file": str(Path(hm).resolve()), "k_file": str(Path(kfile).resolve()),
        "hm_sha256": sha256(hm), "k_sha256": sha256(kfile),
        "readback_file": str(Path(readback).resolve()), "readback_sha256": sha256(readback),
        "nodes": len(nodes), "elements": sum(elements.values()), "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hm", required=True)
    parser.add_argument("--k", required=True)
    parser.add_argument("--readback", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        report = verify(args.hm, args.k, args.readback)
    except (OSError, ValueError, IndexError) as error:
        report = {"schema": "cae.mesh-readback.v1", "overall": "FAIL", "nodes": 0, "elements": 0, "failures": [str(error)]}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Mesh readback: {report['overall']}; nodes={report['nodes']} elements={report['elements']}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
