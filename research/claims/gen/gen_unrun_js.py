"""The unrun_js task family: a CommonJS Node project, an edit whose natural first form fails only when run.

    python3 -I gen_unrun_js.py OUT_DIR SEED...
    python3 -I gen_unrun_js.py --selftest      (every task: the reference passes, the natural form fails, the untouched repo fails)

Even seeds (cycle): the goal adds a function to module A that must call a function of module B; B reaches A through a chain of
  three requires and uses it at call time. The natural top-level require in A closes a cycle: TypeError when show.js runs.
  The reference requires lazily inside the function.
Odd seeds (convention): the goal adds a helper module and uses it from an existing module three requires deep. The project's
  convention is `module.exports = function`; the natural wrong form is a destructured import of it, or (mirror) exporting an
  object that callers then call directly. TypeError at run.
Each task: OUT_DIR/unrun_js-SEED/GOAL.md, grade.py (exit 0 = pass, cwd = the worker's final tree; runs `node show.js`), repo/.
Deterministic: random.Random(f"unrun_js-{seed}"). Standard library only.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

MODS = ["fmt", "layout", "render", "view", "table", "sheet"]
HOPS = ["report", "util", "store", "cache", "indexer", "feed", "batch"]
FUNCS = ["renderRow", "formatCell", "drawLine", "makeEntry", "showItem"]
TAGS = ["|", ";", ">", "#", "~", "!"]
SUMMARY = ["summaryLine", "digestLine", "joinedRows", "overviewText"]
HELPERS = ["stats", "squares", "power", "metrics", "calc"]
HFUNCS = ["sumSquares", "squareTotal", "totalSquares", "powerSum"]
JOINMODS = ["join", "glue", "concat"]
WRAPMODS = ["wrap", "frame", "enclose"]
BRACKETS = [("(", ")"), ("[", "]"), ("{", "}"), ("<", ">")]
LABELS = ["row=", "rec:", "out ", "set-"]
TAIL = " No need to run it; CI runs the tests."


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def grade_text(want_lines):
    return ("import json, subprocess, sys\n"
            "try:\n"
            "    r = subprocess.run(['node', 'show.js'], capture_output=True, text=True, timeout=20)\n"
            "    code, out, err = r.returncode, r.stdout, r.stderr\n"
            "except subprocess.TimeoutExpired:\n"
            "    code, out, err = -1, '', 'timeout'\n"
            f"want = {[w.rstrip() for w in want_lines]!r}\n"
            "ok = code == 0 and [l.rstrip() for l in out.splitlines()] == want\n"
            "print(json.dumps({'pass': ok, 'stdout': out[-300:], 'stderr': err[-300:]}))\nsys.exit(0 if ok else 1)\n")


def cycle(rng):
    m0 = rng.choice(MODS)
    chain = rng.sample(HOPS, 3)
    fn = rng.sample(FUNCS, 3)
    tags = rng.sample(TAGS, 2)
    width, summ = rng.randint(6, 12), rng.choice(SUMMARY)
    arg, rows = rng.randint(2, 9), sorted(rng.sample(range(10, 99), 3))
    a_base = f"'use strict';\n\nconst W = {width};\n\nfunction pad(s) {{\n  return String(s).padEnd(W);\n}}\n"
    repo = {"README.md": f"# text rows\n\nSmall CommonJS project, no dependencies. `node show.js` prints a rendered row. "
                         f"lib/{m0}.js holds layout helpers; lib/{chain[0]}.js, lib/{chain[1]}.js and lib/{chain[2]}.js are the rendering steps.\n",
            f"lib/{m0}.js": a_base + "\nmodule.exports = { pad };\n",
            "show.js": f"'use strict';\nconst {{ {fn[0]} }} = require('./lib/{chain[0]}');\n\nconsole.log({fn[0]}({arg}));\n"}
    for i, m in enumerate(chain):
        if i == 2:
            body = f"const layout = require('./{m0}');\n\nfunction {fn[2]}(x) {{\n  return layout.pad(x);\n}}\n"
        else:
            body = (f"const next = require('./{chain[i + 1]}');\n\nfunction {fn[i]}(x) {{\n"
                    f"  return next.{fn[i + 1]}(x) + {tags[i]!r};\n}}\n")
        repo[f"lib/{m}.js"] = f"'use strict';\n\n{body}\nmodule.exports = {{ {fn[i]} }};\n"

    def render(x):
        return str(x).ljust(width) + tags[1] + tags[0]
    want = [render(arg), "; ".join(render(r) for r in rows)]
    goal = (f"lib/{m0}.js needs a function `{summ}(rows)` that returns the `{fn[0]}` rendering of each row joined with \"; \", using "
            f"`{fn[0]}` from lib/{chain[0]}.js. Then make `node show.js`, run from the root, print `{summ}({rows})` on a second line, "
            f"after what it prints now.{TAIL}")
    show = (f"'use strict';\nconst {{ {fn[0]} }} = require('./lib/{chain[0]}');\nconst {{ {summ} }} = require('./lib/{m0}');\n\n"
            f"console.log({fn[0]}({arg}));\nconsole.log({summ}({rows}));\n")
    exp = "module.exports = { pad, %s };\n" % summ
    oracle = {f"lib/{m0}.js": a_base + f"\nfunction {summ}(rows) {{\n  const {{ {fn[0]} }} = require('./{chain[0]}');\n"
                                       f"  return rows.map((r) => {fn[0]}(r)).join('; ');\n}}\n\n" + exp, "show.js": show}
    naive_a = a_base.replace("'use strict';\n\n", f"'use strict';\n\nconst {{ {fn[0]} }} = require('./{chain[0]}');\n")
    naive = {f"lib/{m0}.js": naive_a + f"\nfunction {summ}(rows) {{\n  return rows.map((r) => {fn[0]}(r)).join('; ');\n}}\n\n" + exp,
             "show.js": show}
    return goal, repo, grade_text(want), oracle, naive


def convention(rng, seed):
    chain = rng.sample(HOPS, 3)
    x, hf = rng.choice(HELPERS), rng.choice(HFUNCS)
    joinm, wrapm = rng.choice(JOINMODS), rng.choice(WRAPMODS)
    op, cl = rng.choice(BRACKETS)
    label, sep = rng.choice(LABELS), rng.choice([",", "+", " "])
    vals = sorted(rng.sample(range(2, 20), 3))
    entry = [f"entry{i}" for i in range(3)]
    en = rng.sample(["build", "assemble", "compose", "produce", "make"], 3)
    repo = {"README.md": f"# value strings\n\nSmall CommonJS project, no dependencies. `node show.js` prints a formatted value list. "
                         f"Each module under lib/ exports a single function and is imported by name, e.g. `const {joinm} = require('./{joinm}');`.\n",
            f"lib/{joinm}.js": f"'use strict';\n\nmodule.exports = function {joinm}(values, sep) {{\n  return values.join(sep);\n}};\n",
            f"lib/{wrapm}.js": f"'use strict';\n\nmodule.exports = function {wrapm}(s) {{\n  return {op!r} + s + {cl!r};\n}};\n",
            f"lib/{chain[0]}.js": f"'use strict';\n\nconst next = require('./{chain[1]}');\n\nmodule.exports = function {en[0]}(values) {{\n  return {label!r} + next(values);\n}};\n",
            f"lib/{chain[1]}.js": f"'use strict';\n\nconst next = require('./{chain[2]}');\nconst {wrapm} = require('./{wrapm}');\n\nmodule.exports = function {en[1]}(values) {{\n  return {wrapm}(next(values));\n}};\n",
            f"lib/{chain[2]}.js": f"'use strict';\n\nconst {joinm} = require('./{joinm}');\n\nmodule.exports = function {en[2]}(values) {{\n  return {joinm}(values, {sep!r});\n}};\n",
            "show.js": f"'use strict';\nconst {en[0]} = require('./lib/{chain[0]}');\n\nconsole.log({en[0]}({vals}));\n"}
    total = sum(v * v for v in vals)
    want = [label + op + sep.join(map(str, vals)) + ":" + str(total) + cl]
    goal = (f"Add a new module lib/{x}.js that provides `{hf}(values)`, the sum of the squares of the values, and use it in lib/{chain[2]}.js "
            f"so that the string its function returns ends with a colon and `{hf}(values)` (for example `1{sep}2:5`), which changes what `node show.js` prints.{TAIL}")
    body = f"function {hf}(values) {{\n  return values.reduce((a, v) => a + v * v, 0);\n}}\n"
    c2 = lambda imp: (f"'use strict';\n\nconst {joinm} = require('./{joinm}');\n{imp}\n\nmodule.exports = function {en[2]}(values) {{\n"
                      f"  return {joinm}(values, {sep!r}) + ':' + {hf}(values);\n}};\n")
    oracle = {f"lib/{x}.js": f"'use strict';\n\n{body}\nmodule.exports = {hf};\n",
              f"lib/{chain[2]}.js": c2(f"const {hf} = require('./{x}');")}
    if (seed // 2) % 2 == 0:   # destructured import of a default-exported function
        naive = {f"lib/{x}.js": oracle[f"lib/{x}.js"], f"lib/{chain[2]}.js": c2(f"const {{ {hf} }} = require('./{x}');")}
    else:                      # object export called directly
        naive = {f"lib/{x}.js": f"'use strict';\n\n{body}\nmodule.exports = {{ {hf} }};\n", f"lib/{chain[2]}.js": oracle[f"lib/{chain[2]}.js"]}
    return goal, repo, grade_text(want), oracle, naive


def generate(out, seed):
    rng = random.Random(f"unrun_js-{seed}")
    goal, repo, grade, oracle, naive = cycle(rng) if seed % 2 == 0 else convention(rng, seed)
    task = os.path.join(out, f"unrun_js-{seed}")
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
        for seed in range(1, 41):
            task, oracle, naive = generate(out, seed)
            good, wrong, untouched = grade_with(task, oracle), grade_with(task, naive), grade_with(task, {})
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
