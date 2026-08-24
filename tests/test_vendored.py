"""Fence locally vendored contracts without reading any other repository.

These copies are correct duplication, not an oversight: each plugin installs alone and none
inherits the others' coverage, so extracting a shared module would break the independence the
marketplace advertises.  What correct duplication cannot survive is silent drift -- if one copy
of `is_cert_none` stops matching, that plugin quietly stops catching a TLS bypass the other
still catches, and nothing says so.

Every vendored symbol therefore pins a digest, and this suite recomputes it.  Three properties
the digest must have, each learned from a case that was watched failing:

* A reworded docstring is not drift.  The copies already differ in their docstrings and are
  correct, so the digest strips the leading docstring; treating prose as drift would make the
  fence noise, and a noisy fence gets deleted.
* A changed constant IS drift, and it touches no function body.  `jwt_decode_callee_chain`
  merely *references* `JWT_CALLEE_RX`; dropping `pyjwt` from that regex blinds this plugin to a
  library the owner still catches while every function body stays byte-identical.  Digesting
  bodies alone let that through -- measured, not supposed -- so a row may name a module-level
  constant, and every in-repository constant a fenced body reads must itself carry a row.
* A symbol that has vanished is drift, not a pass.  An absent symbol fails; it never silently
  digests nothing.

The limit, stated rather than papered over: a repository may not read another repository's
tree, so this fence compares each copy against its own pinned digest, never against the owner's
live source.  It reports "this copy changed since it was last reconciled" and requires a human
to re-pin deliberately.  It cannot report "these two copies now disagree".  Cross-repository
comparison would need one engine reading every tree, which the estate has ruled against.
Functions a fenced body calls are also outside the digest: they are visible in the body and
carry their own tests, whereas a constant's value is invisible at the call site.
"""

import ast
import csv
import hashlib
import pathlib
import shutil
import tempfile

import pytest


ROOT = pathlib.Path(__file__).resolve().parent.parent
HEADER = ("SYMBOL", "LOCAL-PATH", "OWNER-REPO", "OWNER-PATH", "DIGEST", "WHY")


# `ast.dump` is not a stable serialization: Python 3.13 stopped emitting optional fields that
# held their empty default (`keywords=[]`, `orelse=[]`, `finalbody=[]`), so identical source
# digested differently on 3.12 and 3.13 and the fence reported drift on a Python upgrade. A gate
# that fires on lookalikes gets disabled, and disabling it destroys the coverage it did have, so
# the serialization is spelled here instead of inherited from the interpreter: every field is
# emitted, always, and the fields that exist only on some versions are named and skipped.
_VERSION_VARYING_FIELDS = frozenset({"type_comment", "type_params", "kind"})


def _canonical(node):
    if isinstance(node, ast.AST):
        fields = ", ".join(f"{name}={_canonical(getattr(node, name, None))}"
                           for name in node._fields if name not in _VERSION_VARYING_FIELDS)
        return f"{type(node).__name__}({fields})"
    if isinstance(node, list):
        return "[" + ", ".join(_canonical(item) for item in node) + "]"
    return repr(node)


def _parse(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _definition(tree, symbol):
    """The single module-level definition of `symbol`: a function, or a constant assignment."""
    found = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
            found.append(node)
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == symbol for t in node.targets):
                found.append(node)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == symbol:
                found.append(node)
    return found


def _contract(path, symbol, root):
    """The normalised text whose digest is the contract, or None if the symbol is absent."""
    relative = path.relative_to(root)
    found = _definition(_parse(path), symbol)
    if not found:
        return None, f"vendored symbol absent: {symbol} ({relative})"
    if len(found) > 1:
        return None, f"vendored symbol defined {len(found)} times: {symbol} ({relative})"
    node = found[0]
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        # A constant: its value is the whole contract.  The target name is already the row key.
        return _canonical(node.value), None
    body = list(node.body)
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body.pop(0)                      # the docstring, and only the docstring
    arguments = [arg.arg for arg in
                 node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
    if node.args.vararg:
        arguments.append("*" + node.args.vararg.arg)
    if node.args.kwarg:
        arguments.append("**" + node.args.kwarg.arg)
    return repr(arguments) + "\n" + "\n".join(
        _canonical(statement) for statement in body), None


def digest(path, symbol, root):
    text, problem = _contract(path, symbol, root)
    if problem is not None:
        return None, problem
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), None


def _module_file(module, root):
    relative = module.replace(".", "/") + ".py"
    matches = [p for p in root.rglob("*.py") if str(p).endswith("/" + relative)]
    return matches[0] if len(matches) == 1 else None


def _resolve_constant(name, path, root, seen=None):
    """Where `name` is defined as a module-level constant inside this repository, else None."""
    seen = seen or set()
    if path in seen or not path.is_file():
        return None
    seen.add(path)
    tree = _parse(path)
    for node in _definition(tree, name):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return path                  # a constant, defined right here
        return None                      # a function: visible at the call site, not fenced
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                if (alias.asname or alias.name) == name:
                    target = _module_file(node.module, root)
                    if target is None:
                        return None
                    return _resolve_constant(alias.name, target, root, seen)
    return None


def constant_dependencies(path, symbol, root):
    """Every in-repository module-level constant the fenced body reads, as (name, relative path)."""
    found = _definition(_parse(path), symbol)
    if len(found) != 1 or not isinstance(found[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return set()
    node = found[0]
    bound = {a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs}
    if node.args.vararg:
        bound.add(node.args.vararg.arg)
    if node.args.kwarg:
        bound.add(node.args.kwarg.arg)
    bound |= {n.id for n in ast.walk(node) if isinstance(n, ast.Name)
              and isinstance(n.ctx, (ast.Store, ast.Del))}
    dependencies = set()
    for reference in {n.id for n in ast.walk(node)
                      if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}:
        if reference in bound:
            continue
        source = _resolve_constant(reference, path, root)
        if source is not None:
            dependencies.add((reference, str(source.relative_to(root))))
    return dependencies


def rows(root):
    ledger = root / "VENDORED.tsv"
    lines = [line for line in ledger.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader(lines, delimiter="\t")
    if tuple(reader.fieldnames or ()) != HEADER:
        raise AssertionError(f"VENDORED.tsv header does not match its contract: {HEADER}")
    return list(reader)


FIXTURE = '''import re

GUARD_RX = re.compile(r"(?i)^(?:alpha|beta)$")


def guarded(value, *, strict=False):
    """One line of prose about the guard."""
    if strict:
        return GUARD_RX.match(value) is not None
    return bool(value)
'''


def _fixture_digest(source, symbol):
    """Digest `symbol` in a throwaway copy, so a plant never touches the real tree."""
    directory = pathlib.Path(tempfile.mkdtemp())
    try:
        path = directory / "vendored_fixture.py"
        path.write_text(source, encoding="utf-8")
        return digest(path, symbol, directory)
    finally:
        shutil.rmtree(directory)


# The fence itself, and the plants that prove each of its rules can fail.

def test_every_row_matches_its_pinned_digest():
    declared = rows(ROOT)
    assert declared, "VENDORED.tsv declares no vendored contracts"
    for row in declared:
        actual, problem = digest(ROOT / row["LOCAL-PATH"], row["SYMBOL"], ROOT)
        assert problem is None, problem
        assert actual == row["DIGEST"], (
            f"vendored symbol drift: {row['SYMBOL']} ({row['LOCAL-PATH']}). "
            "Reconcile against the owner, then re-pin DIGEST deliberately.")


def test_every_constant_a_fenced_body_reads_is_itself_fenced():
    covered = {(row["SYMBOL"], row["LOCAL-PATH"]) for row in rows(ROOT)}
    for symbol, local in sorted(covered):
        for dependency in sorted(constant_dependencies(ROOT / local, symbol, ROOT)):
            assert dependency in covered, (
                f"{symbol} reads {dependency[0]} ({dependency[1]}), which no VENDORED.tsv row "
                "pins: changing it would drift this copy's behaviour without changing any "
                "fenced body.")


def test_a_changed_body_changes_the_digest():
    before, _ = _fixture_digest(FIXTURE, "guarded")
    after, _ = _fixture_digest(
        FIXTURE.replace("return bool(value)", "return not bool(value)"), "guarded")
    assert before != after, "a changed body left the digest unmoved"


def test_a_reworded_docstring_does_not_change_the_digest():
    before, _ = _fixture_digest(FIXTURE, "guarded")
    after, _ = _fixture_digest(
        FIXTURE.replace("One line of prose about the guard.",
                        "Entirely different wording, same meaning."), "guarded")
    assert before == after, "a reworded docstring was reported as drift"


def test_a_changed_constant_escapes_the_body_and_is_caught_by_its_own_row():
    drifted = FIXTURE.replace("(?:alpha|beta)", "(?:alpha)")
    body_before, _ = _fixture_digest(FIXTURE, "guarded")
    body_after, _ = _fixture_digest(drifted, "guarded")
    assert body_before == body_after, (
        "fixture no longer demonstrates why constants need their own row")
    constant_before, _ = _fixture_digest(FIXTURE, "GUARD_RX")
    constant_after, _ = _fixture_digest(drifted, "GUARD_RX")
    assert constant_before != constant_after, "a changed constant left its own digest unmoved"


def test_a_body_reading_a_constant_reports_that_dependency():
    directory = pathlib.Path(tempfile.mkdtemp())
    try:
        path = directory / "vendored_fixture.py"
        path.write_text(FIXTURE, encoding="utf-8")
        assert constant_dependencies(path, "guarded", directory) == {
            ("GUARD_RX", "vendored_fixture.py")}
    finally:
        shutil.rmtree(directory)


def test_an_absent_symbol_fails_rather_than_digesting_nothing():
    actual, problem = _fixture_digest(FIXTURE.replace("def guarded(", "def renamed("), "guarded")
    assert actual is None
    assert "absent" in problem


def test_a_symbol_defined_twice_fails_rather_than_picking_one():
    actual, problem = _fixture_digest(
        FIXTURE + "\n\ndef guarded(value):\n    return None\n", "guarded")
    assert actual is None
    assert "defined 2 times" in problem


def test_a_ledger_with_a_wrong_header_is_refused():
    directory = pathlib.Path(tempfile.mkdtemp())
    try:
        (directory / "VENDORED.tsv").write_text("SYMBOL\tPATH\n", encoding="utf-8")
        with pytest.raises(AssertionError):
            rows(directory)
    finally:
        shutil.rmtree(directory)
