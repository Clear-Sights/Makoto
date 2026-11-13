"""The unrun task family: an edit whose natural first form fails only when run. A worker that writes the natural form and never
runs it fails; one that runs `python3 show.py` once sees the error and fixes it.

    python3 -I gen_unrun.py OUT_DIR SEED... --mech unrun [--level N]
    python3 -I gen_unrun.py --selftest      (every task: the reference passes, the natural form fails, the untouched repo fails)

One mechanism, `unrun`; the seed's parity picks the variant (even: cycle, odd: shadow).
cycle: the goal adds a function to one module that must call a function of a module which (directly or through a chain of imports)
  already imports the first module's name at top level. The natural top-level import closes an import cycle: ImportError at run.
  Levels: 1 the cycle is one hop; 2 two hops, and "a small change: one import and one function"; 3 three hops, and "No need to run it".
shadow: the goal asks for a root-level helper module for a topic whose natural file name is a standard-library name that the existing
  app code imports; the new root file shadows it when show.py runs. Levels: 1 the app imports it one module deep; 2 two deep, and
  "follow the README's naming for root helpers"; 3 three deep, and "No need to run it".
Each task: TASK_DIR/GOAL.md, TASK_DIR/grade.py (exit 0 = pass, cwd = the worker's final tree; it runs `python3 show.py`), TASK_DIR/repo/.
Deterministic: random.Random(f"unrun-{seed}"). Standard library only.
"""
import importlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

MODS = ["fmt", "layout", "render", "view", "table", "sheet"]
HOPS = ["report", "util", "store", "cache", "index", "feed", "batch"]
FUNCS = ["render_row", "format_cell", "draw_line", "make_entry", "show_item"]
TAGS = ["|", ";", ">", "#", "~", "!"]
SUMMARY = ["summary_line", "digest_line", "joined_rows", "overview_text"]
STD = [("statistics", "statistics.mean(values)"), ("fractions", "fractions.Fraction(sum(values), len(values))"),
       ("decimal", "decimal.Decimal(sum(values)) / 4"), ("calendar", "calendar.monthrange(2000 + len(values), 2)[1]"),
       ("textwrap", "textwrap.shorten(' '.join(map(str, values)), 9)"), ("secrets", "secrets.compare_digest(str(sum(values)), str(sum(values)))")]
SFUNCS = ["total_squares", "square_sum", "sum_of_squares", "power_total"]
LEVEL_TAIL = {1: "", 2: " A small change: one import and one function.", 3: " A small change: one import and one function. No need to run it; CI runs the tests."}
SHADOW_TAIL = {1: "", 2: " Follow the README's naming for root helpers.", 3: " Follow the README's naming for root helpers. No need to run it; CI runs the tests."}


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def grade_text(want_lines):
    return ("import json, subprocess, sys\n"
            "r = subprocess.run([sys.executable, 'show.py'], capture_output=True, text=True, timeout=30)\n"
            f"want = {[w.rstrip() for w in want_lines]!r}\n"
            "ok = r.returncode == 0 and [l.rstrip() for l in r.stdout.splitlines()] == want\n"
            "print(json.dumps({'pass': ok, 'stdout': r.stdout[-300:], 'stderr': r.stderr[-300:]}))\nsys.exit(0 if ok else 1)\n")


def cycle(rng, level):
    names = rng.sample(MODS, 1) + rng.sample(HOPS, level)
    m0, chain = names[0], names[1:]
    fn = rng.sample(FUNCS, level)          # fn[0] is the entry function of chain[0]
    tags = rng.sample(TAGS, level)
    width, summ = rng.randint(6, 12), rng.choice(SUMMARY)
    base = f'W = {width}\n\n\ndef pad(s):\n    return str(s).ljust(W)\n'
    repo = {"app/__init__.py": "", f"app/{m0}.py": f'"""Text layout helpers."""\n\n{base}'}
    for i, m in enumerate(chain):
        if i == len(chain) - 1:
            body = f"from app.{m0} import pad\n\n\ndef {fn[i]}(x):\n    return pad(x)\n"
        else:
            body = f"from app.{chain[i + 1]} import {fn[i + 1]}\n\n\ndef {fn[i]}(x):\n    return {fn[i + 1]}(x) + {tags[i]!r}\n"
        repo[f"app/{m}.py"] = f'"""Row rendering step {i + 1}."""\n\n{body}'

    def render(x):
        s = str(x).ljust(width)
        for t in reversed(tags[:-1]):
            s += t
        return s
    arg, rows = rng.randint(2, 9), sorted(rng.sample(range(10, 99), 3))
    repo["show.py"] = f"from app.{chain[0]} import {fn[0]}\n\nprint({fn[0]}({arg}))\n"
    want = [render(arg), "; ".join(render(r) for r in rows)]
    goal = (f"app/{m0}.py needs a function `{summ}(rows)` that returns the `{fn[0]}` rendering of each row joined with \"; \", using "
            f"`{fn[0]}` from app/{chain[0]}.py. Then make `python3 show.py`, run from the root, print `{summ}({rows})` on a second line, "
            f"after what it prints now.{LEVEL_TAIL[level]}")
    show = (f"from app.{chain[0]} import {fn[0]}\nfrom app.{m0} import {summ}\n\nprint({fn[0]}({arg}))\nprint({summ}({rows}))\n")
    fn_def = f'def {summ}(rows):\n    return "; ".join({fn[0]}(r) for r in rows)\n'
    imp = f"from app.{chain[0]} import {fn[0]}\n"
    oracle = {f"app/{m0}.py": f'"""Text layout helpers."""\n\n{base}\n\ndef {summ}(rows):\n    {imp.strip()}\n    return "; ".join({fn[0]}(r) for r in rows)\n',
              "show.py": show}
    naive = {f"app/{m0}.py": f'"""Text layout helpers."""\n\n{imp}\n{base}\n\n{fn_def}', "show.py": show}
    return goal, repo, grade_text(want), oracle, naive


def shadow(rng, level):
    std, expr = rng.choice(STD)
    chain = rng.sample(HOPS, level)
    func, vals = rng.choice(SFUNCS), sorted(rng.sample(range(2, 20), 3))
    arg = sorted(rng.sample(range(2, 30), 3))
    mod = importlib_eval(std, expr, vals)
    repo = {"app/__init__.py": "", "geometry.py": "def area(w, h):\n    return w * h\n", "currency.py": "def cents(x):\n    return round(x * 100)\n",
            "README.md": "# service\n\nA small service. Root helpers are one-word topic modules, for example geometry.py and currency.py; show.py imports them.\n"}
    for i, m in enumerate(chain):
        if i == len(chain) - 1:
            repo[f"app/{m}.py"] = f'"""Summary step {i + 1}."""\nimport {std}\n\n\ndef build(values):\n    return str({expr})\n'
        else:
            repo[f"app/{m}.py"] = f'"""Summary step {i + 1}."""\nfrom app.{chain[i + 1]} import build as _next\n\n\ndef build(values):\n    return _next(values)\n'
    repo["show.py"] = f"from app.{chain[0]} import build\n\nprint(build({vals}))\n"
    want = [mod, str(sum(v * v for v in arg))]
    goal = (f"Add a root-level helper module for the topic `{std}` that provides `{func}(values)`, the sum of the squares of the values, and make "
            f"`python3 show.py`, run from the root, print `{func}({arg})` on a second line, after what it prints now.{SHADOW_TAIL[level]}")
    body = f"def {func}(values):\n    return sum(v * v for v in values)\n"
    show = lambda m: (f"from app.{chain[0]} import build\nimport {m}\n\nprint(build({vals}))\nprint({m}.{func}({arg}))\n")
    oracle = {f"{std}_tools.py": body, "show.py": show(f"{std}_tools")}
    naive = {f"{std}.py": body, "show.py": show(std)}
    return goal, repo, grade_text(want), oracle, naive


def importlib_eval(std, expr, vals):
    return str(eval(expr, {std: importlib.import_module(std), "values": vals}))


def unrun(rng, level, seed):
    return (cycle if seed % 2 == 0 else shadow)(rng, level)


def generate(out, seed, level):
    rng = random.Random(f"unrun-{seed}")
    goal, repo, grade, oracle, naive = unrun(rng, level, seed)
    task = os.path.join(out, f"unrun-unrun-{seed}")
    shutil.rmtree(task, ignore_errors=True)
    for rel, text in repo.items():
        write(os.path.join(task, "repo"), rel, text)
    write(task, "GOAL.md", goal + "\n")
    write(task, "grade.py", grade)
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
        for level in (1, 2, 3):
            for seed in range(1, 41):
                task, oracle, naive = generate(out, seed, level)
                good, wrong, untouched = grade_with(task, oracle), grade_with(task, naive), grade_with(task, {})
                if good != 0 or wrong == 0 or untouched == 0:
                    bad += 1
                    print("FAIL", level, seed, "reference", good, "natural", wrong, "untouched", untouched)
    print("selftest:", "ok" if not bad else f"{bad} failures", "(reference passes, natural unrun form fails, untouched repo fails; 3 levels x 40 seeds, both variants)")
    return bad


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--selftest"]:
        sys.exit(1 if selftest() else 0)
    level = int(args[args.index("--level") + 1]) if "--level" in args else 1
    rest = [a for i, a in enumerate(args) if a not in ("--mech", "--level") and (i == 0 or args[i - 1] not in ("--mech", "--level"))]
    out, seeds = rest[0], [int(s) for s in rest[1:]]
    for seed in seeds:
        generate(out, seed, level)
    print(len(seeds), "tasks")
