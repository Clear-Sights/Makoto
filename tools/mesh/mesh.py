"""Makoto spirit mesh: every row a root; a fire counts only if the agent sees it (hook output), every root gated by catch / reworded / let-through cases.

usage: python3 mesh.py            -> runs every case in mesh.tsv against MAKOTO_ROOT (default: the
                                    installed plugin), prints each red case and `distance N` (red
                                    cases); distance 0 = met.
       python3 mesh.py FILE.tsv   -> the same over another case table (e.g. proposed.tsv)
       python3 mesh.py build      -> (re)builds mesh.tsv from */results.tsv
A plant is the unfixed install: a case added for a fix must read red there.
"""
import csv, json, os, sys, pathlib
from concurrent.futures import ThreadPoolExecutor
import harness

W = pathlib.Path(__file__).parent
EXCLUDED = {"gate.stale_establisher": "removed: second runner for H2 (stale_pass fills it)",
            "gate.relative_path_citation": "removed: fits no register entry",
            "gate.undeclared_falsifiable": "reads the installed catalog, no input can drive it",
            "gate.self_wired": "the installed manifest is always wired; unwired needs a second plugin root"}


def ids_by_short():
    sys.path.insert(0, harness.ROOT)
    from makoto.checks import spec, otherPoint, switch, lineage
    out = {}
    for m in (spec, otherPoint, switch, lineage):
        for k, v in vars(m).items():
            if k.endswith("_CHECK") and hasattr(v, "id"):
                out[k] = out[k[:-6]] = v.id
                out[v.id] = v.id
    out["fp.canon_fingerprints"] = "gate.canon_fingerprints"
    return out


def build():
    names = ids_by_short()
    rows = []
    for f in sorted(W.glob("*/results.tsv")):
        for r in csv.DictReader(open(f), delimiter="\t"):
            rid = names.get(r["row"])
            if rid is None or rid in EXCLUDED:
                continue
            exp = r["expected"] if r["expected"] in ("FIRE", "ALLOW") else "ALLOW"
            p = pathlib.Path(r["case_file"])
            if not p.is_absolute():
                p = (W / p) if (W / p).exists() else (f.parent / p)
            rows.append((rid, r["case"], exp, str(p.relative_to(W)), r["what_it_shows"]))
    with open(W / "mesh.tsv", "w") as out:
        out.write("root\tcase\texpect\tfile\tshows\n")
        for r in rows:
            out.write("\t".join(r) + "\n")
    print(f"{len(rows)} cases, {len({r[0] for r in rows})} roots")


def one(r):
    _, ids = harness.verdict(harness.run(harness.load(W / r["file"])))
    got = "FIRE" if r["root"] in ids else "ALLOW"
    return r, got


def main(table="mesh.tsv"):
    rows = list(csv.DictReader(open(W / table), delimiter="\t"))
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(one, rows))
    red = [(r, g) for r, g in res if g != r["expect"]]
    for r, g in red:
        print(f"RED {r['root']}\t{r['case']}\texpect {r['expect']} got {g}\t{r['file']}\t{r['shows']}")
    print(f"cases {len(rows)} roots {len({r['root'] for r in rows})} distance {len(red)}")


if __name__ == "__main__":
    build() if sys.argv[1:] == ["build"] else main(*sys.argv[1:])
