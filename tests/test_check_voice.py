"""SPEC-C item 5 (one voice): a check's retry_hint/description must be a MODULE-LEVEL string
CONSTANT in its own file, not an inline literal buried inside the `Check(...)` call -- this is
what makes the hint/detector-mismatch class this session found and fixed TWICE (gate.named_test's
quoted-retraction FP, canon.timeout's retry_hint over-promise) structurally hard to recreate: a
grep for the file's own top-level assignments shows every voice string at a glance, instead of
requiring a reader to parse out a long inline kwarg to find it.

Stop-tier gates that build MULTIPLE distinct finding kinds (hollowTest.py's _KIND_MESSAGE dict,
canonTimeoutRecur.py's CANON_SEQ_PRIMITIVES tuples) already satisfy the SAME anti-duplication
property by a different, arguably stronger shape (one dict/tuple co-locating every sub-kind's
text, rather than a single bare string) -- this test only requires the literal RETRY_HINT/
DESCRIPTION constant shape for checks that actually declare a single retry_hint/description on
their CHECK export (today: every Pre-tier check), since that is the exact shape this session's
migration produced and the exact shape the spec's own step 1 describes.
"""
from __future__ import annotations
import ast
import inspect

from makoto.registry import discover


def _module_level_names(mod) -> set:
    """Every name assigned at MODULE level (not inside a function/class) in `mod`'s own source."""
    src = inspect.getsource(mod)
    tree = ast.parse(src)
    names = set()
    for node in tree.body:   # tree.body only -- module level, not nested scopes
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names


def test_every_check_with_a_retry_hint_declares_it_as_a_module_level_constant():
    violations = []
    for c in discover():
        if not c.retry_hint:
            continue
        mod = __import__(c.predicate_module, fromlist=["_"]) if c.predicate_module else None
        if mod is None:
            continue
        if "RETRY_HINT" not in _module_level_names(mod):
            violations.append(c.id)
    assert not violations, (
        f"these checks' retry_hint is not a module-level RETRY_HINT constant: {violations}"
    )


def test_every_check_with_a_description_declares_it_as_a_module_level_constant():
    violations = []
    for c in discover():
        if not c.description:
            continue
        mod = __import__(c.predicate_module, fromlist=["_"]) if c.predicate_module else None
        if mod is None:
            continue
        if "DESCRIPTION" not in _module_level_names(mod):
            violations.append(f"{c.id}: no module-level DESCRIPTION")
            continue
        # AND IT IS THE ONE THE CHECK SHIPS. The name existing says nothing about the value: a
        # module could define DESCRIPTION and hand Check a different literal.
        #
        # HONEST NOTE ON WHAT THIS ADDS, because I nearly shipped it as coverage it does not
        # provide. For every check that exists today this comparison CANNOT fail while the AST
        # law below passes: that law requires `description=DESCRIPTION` by name at the CHECK
        # call, and a name cannot differ from itself. It becomes load-bearing only for a check
        # the AST law skips -- one with a description and no retry_hint -- and there are none.
        # test_the_description_law_is_not_the_only_cover asserts that emptiness, so if such a
        # check ever ships, the redundancy stops being redundant and this line starts working.
        declared = getattr(mod, "DESCRIPTION", None)
        if declared != c.description:
            violations.append(
                f"{c.id}: DESCRIPTION is {declared!r} but the shipped check describes itself as "
                f"{c.description!r}; the constant and the export have drifted")
    assert not violations, (
        f"these checks' description is not the module-level DESCRIPTION constant: {violations}"
    )


def test_the_check_export_references_the_constant_not_a_second_literal():
    """Teeth: the CHECK export's own source line must use the NAME (RETRY_HINT/DESCRIPTION), not
    a second, independently-typed string literal -- the exact duplication this item exists to
    prevent (a name and a literal can never silently drift apart; two literals can)."""
    for c in discover():
        if not (c.retry_hint and c.description) or not c.predicate_module:
            continue
        mod = __import__(c.predicate_module, fromlist=["_"])
        src = inspect.getsource(mod)
        # READ THE CALL, NOT THE LINE. `"retry_hint=RETRY_HINT" in check_line` is satisfied by a
        # trailing comment -- `CHECK = Check(..., retry_hint="literal")  # retry_hint=RETRY_HINT`
        # -- which is the duplication this test exists to forbid, wearing the shape of the fix.
        # The keyword's value has to BE the name.
        assignment = next(
            node for node in ast.walk(ast.parse(src))
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "CHECK" for t in node.targets))
        by_name = {kw.arg: kw.value for kw in assignment.value.keywords
                   if isinstance(assignment.value, ast.Call)}
        for keyword, constant in (("retry_hint", "RETRY_HINT"), ("description", "DESCRIPTION")):
            value = by_name.get(keyword)
            assert isinstance(value, ast.Name) and value.id == constant, (
                f"{c.id}: CHECK's {keyword}= is not the name {constant}; it is "
                f"{ast.dump(value) if value is not None else 'absent'}. A name and a literal "
                f"cannot silently drift apart; two literals can.")


def test_the_description_law_is_not_the_only_cover():
    """Which checks the AST law skips, stated as a number rather than assumed.

    `test_the_check_export_references_the_constant_not_a_second_literal` skips any check without
    BOTH a retry_hint and a description. The value comparison in the law above is implied by it
    for every check it covers, so the two are only jointly non-redundant over the checks it
    skips. That set is measured here instead of being taken on trust -- if it grows, the value
    comparison is doing real work; if the AST law's condition is ever widened, this reddens and
    the note beside that comparison has to be rewritten rather than quietly becoming false.
    """
    checks = list(discover())
    assert checks, "no checks discovered; every law in this module is vacuous"
    skipped = [c.id for c in checks
               if c.description and c.predicate_module and not c.retry_hint]
    assert skipped == [], (
        f"these checks have a description and no retry_hint, so the AST law skips them and the "
        f"value comparison above is their ONLY cover: {skipped}. That is not a defect -- it is "
        f"the case that comparison exists for -- but the note beside it says this set is empty, "
        f"so update the note.")
