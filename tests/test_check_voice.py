"""SPEC-C item 5 (one voice): a row's retry_hint/description is a MODULE-LEVEL string constant of
its own shape module, `<key>_RETRY_HINT` / `<key>_DESCRIPTION`, never an inline literal buried
inside the `Check(...)` call -- what makes the hint/detector-mismatch class this session found
and fixed TWICE (gate.named_test's quoted-retraction FP, canon.timeout's retry_hint over-promise)
structurally hard to recreate. A name and a literal cannot silently drift apart; two literals can.

Stop rows that build several finding kinds (hollowTest's _KIND_MESSAGE, the canon primitives'
tuples) co-locate each kind's text in one table instead and declare no retry_hint on the row.
"""
from __future__ import annotations
import ast

from tests._rows import rows


def _voice_violations(key: str, call: ast.Call, binds: dict) -> list:
    out = []
    for keyword in ("retry_hint", "description"):
        value = next((kw.value for kw in call.keywords if kw.arg == keyword), None)
        if value is None:
            continue
        constant = f"{key}_{keyword.upper()}"
        if not (isinstance(value, ast.Name) and value.id == constant
                and isinstance(binds.get(constant), ast.Constant) and isinstance(binds[constant].value, str)):
            out.append(f"{key}: {keyword}= is not the module-level string constant {constant}")
    return out


def test_every_row_voices_through_its_own_module_level_constants():
    found = list(rows().values())
    assert any(r.call.keywords for r in found), "no rows read; the law is vacuous"
    violations = [v for r in found for v in _voice_violations(r.key, r.call, r.binds)]
    assert not violations, violations


def test_voice_law_catches_a_second_literal():
    tree = ast.parse('x_RETRY_HINT = "a"\nx_CHECK = Check(retry_hint="a")\n')
    binds = {s.targets[0].id: s.value for s in tree.body}
    assert _voice_violations("x", binds["x_CHECK"], binds)
    good = ast.parse('x_RETRY_HINT = "a"\nx_CHECK = Check(retry_hint=x_RETRY_HINT)\n')
    binds = {s.targets[0].id: s.value for s in good.body}
    assert not _voice_violations("x", binds["x_CHECK"], binds)
