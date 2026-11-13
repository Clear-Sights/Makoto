"""The datachain task family: build.py writes a JSON file that report.py reads. The goal changes only what build.py writes.

    python3 -I gen_datachain.py OUT_DIR SEED...
    python3 -I gen_datachain.py --selftest      (every task: the reference passes, the natural form fails, the untouched repo fails)

Even seeds: a field in the JSON is renamed (natural form: build.py only, report.py then raises KeyError).
Odd seeds: a unit changes, cents to whole units, with the field renamed or kept (natural form: build.py only; KeyError or wrong numbers).
Each task: OUT_DIR/datachain-SEED/GOAL.md, grade.py (exit 0 = pass, cwd = the worker's final tree; runs build.py then report.py),
repo/. Deterministic: random.Random(f"datachain-{seed}"). Standard library only.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

NOUNS = ["order", "invoice", "ticket", "shipment", "booking"]
LABELS = ["alpha", "bravo", "cedar", "delta", "ember", "flint", "grove", "harbor", "iris", "jade"]
OLD = ["total_cents", "amount_cents", "cost_cents", "price_cents"]
NEW = ["grand_cents", "gross_cents", "charge_cents", "sum_cents"]
STEM = ["amount", "total", "cost", "price"]


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def grade_text(want_lines, noun, field, gone, vals):
    return ("import json, shutil, subprocess, sys\n"
            "shutil.rmtree('data', ignore_errors=True)\n"
            "outs = []\n"
            "ok = True\n"
            "for script in ('build.py', 'report.py'):\n"
            "    try:\n"
            "        r = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=30)\n"
            "    except subprocess.TimeoutExpired:\n"
            "        ok = False\n"
            "        outs.append((script, -1, '', 'timeout'))\n"
            "        break\n"
            "    outs.append((script, r.returncode, r.stdout, r.stderr))\n"
            "    if r.returncode != 0:\n"
            "        ok = False\n"
            "        break\n"
            f"want = {[w.rstrip() for w in want_lines]!r}\n"
            "last = outs[-1]\n"
            "ok = ok and last[0] == 'report.py' and [l.rstrip() for l in last[2].splitlines()] == want\n"
            f"try:\n    rows = json.load(open('data/{noun}s.json'))['rows']\n"
            f"    ok = ok and [r.get({field!r}) for r in rows] == {vals!r} and all(k not in r for r in rows for k in {gone!r})\n"
            "except Exception:\n    ok = False\n"
            "print(json.dumps({'pass': ok, 'script': last[0], 'stdout': last[2][-300:], 'stderr': last[3][-300:]}))\nsys.exit(0 if ok else 1)\n")


def money(c):
    return f"{c // 100}.{c % 100:02d}"


def build_py(noun, field, units):
    value = "round(int(r['qty']) * int(r['unit_cents']) / 100, 2)" if units else "int(r['qty']) * int(r['unit_cents'])"
    return ("import csv\nimport json\nimport os\n\n"
            f"with open('input/{noun}s.csv', newline='') as f:\n    rows = list(csv.DictReader(f))\n\n"
            "out = [\n    {\n        'id': int(r['id']),\n        'label': r['label'],\n        'qty': int(r['qty']),\n"
            f"        {field!r}: {value},\n    }}\n    for r in rows\n]\n"
            "os.makedirs('data', exist_ok=True)\n"
            f"with open('data/{noun}s.json', 'w') as f:\n    json.dump({{'rows': out}}, f, indent=2)\n")


def report_py(noun, field, units):
    div = "" if units else " / 100"
    return ("import json\n\n"
            f"with open('data/{noun}s.json') as f:\n    rows = json.load(f)['rows']\n\n"
            f"print('{noun.capitalize()} report')\nfor r in rows:\n    print(f\"{{r['label']}}: {{r[{field!r}]{div}:.2f}}\")\n"
            "print(f\"count: {len(rows)}\")\n"
            f"print(f\"total: {{sum(r[{field!r}] for r in rows){div}:.2f}}\")\n")


def generate(out, seed):
    rng = random.Random(f"datachain-{seed}")
    noun = rng.choice(NOUNS)
    n = rng.randint(4, 7)
    labels = rng.sample(LABELS, n)
    qty = [rng.randint(1, 9) for _ in range(n)]
    unit = [rng.randint(150, 9900) for _ in range(n)]
    totals = [q * u for q, u in zip(qty, unit)]
    if seed % 2 == 0:
        old, new = rng.choice(OLD), rng.choice(NEW)
        goal = (f"Change build.py so that each row it writes to data/{noun}s.json carries the field `{new}` in place of `{old}`, "
                f"holding the same value as before.")
        start_field, units_start, end_field, units_end = old, False, new, False
    elif (seed // 2) % 2 == 0:
        field = rng.choice(STEM)
        goal = (f"Change build.py so that the `{field}` it writes for each row of data/{noun}s.json is in whole currency units "
                f"(for example 12.5) instead of cents.")
        start_field, units_start, end_field, units_end = field, False, field, True
    else:
        old = rng.choice(OLD)
        new = old[:-len("_cents")] + "_units"
        goal = (f"Change build.py so that each row it writes to data/{noun}s.json carries `{new}`, the amount in whole currency units "
                f"(for example 12.5), in place of `{old}` in cents.")
        start_field, units_start, end_field, units_end = old, False, new, True
    rows = "\n".join(f"{i + 1},{l},{q},{u}" for i, (l, q, u) in enumerate(zip(labels, qty, unit)))
    repo = {"README.md": f"# {noun} summaries\n\nA small pipeline, standard library only. `python3 build.py` reads input/{noun}s.csv and writes "
                         f"data/{noun}s.json. `python3 report.py` reads that file and prints a summary. Money in the input is in integer cents.\n",
            f"input/{noun}s.csv": f"id,label,qty,unit_cents\n{rows}\n",
            "build.py": build_py(noun, start_field, units_start), "report.py": report_py(noun, start_field, units_start)}
    want = [f"{noun.capitalize()} report"] + [f"{l}: {money(t)}" for l, t in zip(labels, totals)] + [f"count: {n}", f"total: {money(sum(totals))}"]
    oracle = {"build.py": build_py(noun, end_field, units_end), "report.py": report_py(noun, end_field, units_end)}
    naive = {"build.py": build_py(noun, end_field, units_end)}
    task = os.path.join(out, f"datachain-{seed}")
    shutil.rmtree(task, ignore_errors=True)
    for rel, text in repo.items():
        write(os.path.join(task, "repo"), rel, text)
    write(task, "GOAL.md", goal + "\n")
    vals = [t / 100 if units_end else t for t in totals]
    gone = [start_field] if start_field != end_field else []
    write(task, "grade.py", grade_text(want, noun, end_field, gone, vals))
    return task, oracle, naive


def grade_with(task, files):
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "t")
        shutil.copytree(os.path.join(task, "repo"), tree)
        for rel, text in files.items():
            write(tree, rel, text)
        return subprocess.run([sys.executable, os.path.join(task, "grade.py")], cwd=tree, capture_output=True, timeout=60).returncode


def selftest():
    bad = 0
    with tempfile.TemporaryDirectory() as out:
        for seed in range(1, 41):
            task, oracle, naive = generate(out, seed)
            good, wrong = grade_with(task, oracle), grade_with(task, naive)
            # the untouched repo must fail: the report's output is unchanged, so grade it by the goal's effect on build output
            untouched = grade_with(task, {})
            if good != 0 or wrong == 0 or untouched == 0:
                bad += 1
                print("FAIL", seed, "reference", good, "natural", wrong, "untouched", untouched)
    print("selftest:", "ok" if not bad else f"{bad} failures")
    return bad


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--selftest"]:
        sys.exit(1 if selftest() else 0)
    out, seeds = args[0], [int(s) for s in args[1:]]
    for seed in seeds:
        generate(out, seed)
    print(len(seeds), "tasks")
