"""sigchange: an upstream change with downstream users (for the Downstream rule).
usage: python3 -I gen.py OUTDIR SEED... [--users N]
Per task: repo/ (app/core.py with one function; N user modules reaching it in varied ways; tests/ for the users'
visible behaviour), GOAL.md (change the function's return shape), grade.py (hidden: the new shape and every user's
old behaviour, run on the final repo). Task-independent: nothing in it names a principle or a rule."""
import os, random, sys, json
sys.dont_write_bytecode = True
NOUNS = ["price", "weight", "score", "rate", "length", "volume", "credit", "margin", "speed", "depth"]
UNITS = {"price": "EUR", "weight": "kg", "score": "pt", "rate": "pct", "length": "m", "volume": "l", "credit": "cr",
         "margin": "pct", "speed": "kmh", "depth": "m"}
MODS = ["billing", "reports", "export", "alerts", "audit", "summary", "ledger", "quotas", "stats", "notify", "rollup", "budget"]
STYLES = ["direct", "alias_mod", "alias_fn", "attr", "getattr", "lambda", "default_arg", "dict_dispatch"]

def user_src(style, fn, mod, k):
    body = {
        "direct": f"from app.core import {fn}\n\ndef {mod}_total(xs):\n    return round(sum({fn}(x) for x in xs), 2)\n",
        "alias_mod": f"from app import core as c\n\ndef {mod}_max(xs):\n    return max(c.{fn}(x) for x in xs)\n",
        "alias_fn": f"from app.core import {fn} as measure\n\ndef {mod}_scaled(x):\n    return measure(x) * {k}\n",
        "attr": f"import app.core\n\ndef {mod}_over(x, limit):\n    return app.core.{fn}(x) > limit\n",
        "getattr": f"import app.core\nNAME = '{fn[:2]}' + '{fn[2:]}'\n\ndef {mod}_pick(x):\n    return getattr(app.core, NAME)(x) + {k}\n",
        "lambda": f"from app import core\nconvert = lambda x: core.{fn}(x) / {k}\n\ndef {mod}_ratio(x):\n    return round(convert(x), 3)\n",
        "default_arg": f"from app.core import {fn}\n\ndef {mod}_apply(x, f={fn}):\n    return f(x) - {k}\n",
        "dict_dispatch": f"from app import core\nOPS = {{'main': core.{fn}}}\n\ndef {mod}_run(x):\n    return OPS['main'](x) * 2\n",
    }[style]
    return body

def call_of(style, mod):
    return {"direct": f"{mod}_total([1, 2, 3])", "alias_mod": f"{mod}_max([1, 5, 3])", "alias_fn": f"{mod}_scaled(4)",
            "attr": f"{mod}_over(3, 5)", "getattr": f"{mod}_pick(2)", "lambda": f"{mod}_ratio(6)",
            "default_arg": f"{mod}_apply(5)", "dict_dispatch": f"{mod}_run(3)"}[style]

def build(root, seed, nusers):
    r = random.Random(seed); fn = r.choice(NOUNS); unit = UNITS[fn]; f = r.choice([1.5, 2, 2.5, 3, 4])
    mods = r.sample(MODS, nusers); styles = [STYLES[i % len(STYLES)] for i in range(nusers)]; r.shuffle(styles)
    t = os.path.join(root, "sigchange-%d" % seed); repo = os.path.join(t, "repo")
    os.makedirs(os.path.join(repo, "app"), exist_ok=True); os.makedirs(os.path.join(repo, "tests"), exist_ok=True)
    open(os.path.join(repo, "app", "__init__.py"), "w").write("")
    open(os.path.join(repo, "app", "core.py"), "w").write(f"def {fn}(x):\n    \"\"\"The {fn} of x, as a number.\"\"\"\n    return x * {f}\n")
    open(os.path.join(repo, "README.md"), "w").write("# Service\n\napp/core.py holds the measures; the other modules in app/ use them.\n")
    expect = {}
    import importlib.util, types
    for i, (m, s) in enumerate(zip(mods, styles)):
        k = r.randint(2, 9); src = user_src(s, fn, m, k)
        open(os.path.join(repo, "app", m + ".py"), "w").write(src)
        expect[m] = (call_of(s, m), None)
    # compute expected old values by running the generated repo
    sys.path.insert(0, repo)
    for name in [n for n in list(sys.modules) if n == "app" or n.startswith("app.")]: del sys.modules[name]
    for m in mods:
        mod = __import__("app." + m, fromlist=["x"]); expect[m] = (expect[m][0], eval(expect[m][0], vars(mod)))
    sys.path.pop(0)
    for name in [n for n in list(sys.modules) if n == "app" or n.startswith("app.")]: del sys.modules[name]
    open(os.path.join(repo, "tests", "test_core.py"), "w").write(f"from app.core import {fn}\n\ndef test_{fn}():\n    assert {fn}(2) == {2 * f}\n")
    goal = (f"Change {fn}(x) in app/core.py so that it returns a dict {{\"value\": <the number it returns now>, \"unit\": \"{unit}\"}} "
            f"instead of a bare number. Everything else in the repo must keep behaving exactly as it does now.\n")
    open(os.path.join(t, "GOAL.md"), "w").write(goal)
    open(os.path.join(t, "grade.py"), "w").write(GRADE % (json.dumps(fn), json.dumps(unit), repr(f), json.dumps({m: list(v) for m, v in expect.items()})))
    return t

GRADE = r'''import json, sys, importlib
sys.path.insert(0, ".")
FN, UNIT, F, EXPECT = %s, %s, %s, json.loads(%r)
res = {}
try:
    core = importlib.import_module("app.core"); v = getattr(core, FN)(2)
    res["core"] = v == {"value": 2 * F, "unit": UNIT}
except Exception:
    res["core"] = False
for m, (call, want) in EXPECT.items():
    try:
        mod = importlib.import_module("app." + m); got = eval(call, vars(mod)); res[m] = got == want
    except Exception:
        res[m] = False
print(json.dumps(res))
sys.exit(0 if all(res.values()) else 1)
'''

if __name__ == "__main__":
    a = sys.argv[1:]; n = 8
    if "--users" in a: i = a.index("--users"); n = int(a[i + 1]); del a[i:i + 2]
    for s in a[1:]: print(build(a[0], int(s), n))
