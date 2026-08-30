"""Defensiveness/convention artifact: a small JSON fixture corpus for gate.hollow_test, matching the
convention set by `tests/predicates/regex_file_cases.json` (fires / silent-legitimate-equality-check /
silent-real-assertion-with-similar-shape / silent-off-file buckets). NOT a replacement for the much
more thorough `test_hollow_test_analyzer.py` / `test_hollow_test_fp.py` -- this is additive and small.

Unlike the regex-based PreCheck predicates that `regex_file_cases.json` protects against, an AST-based
check like this one is safe with inline Python string literals as fixtures (a fixture source string
embedded as a string literal in THIS file is never itself parsed as a real top-level FunctionDef of
this file, so it can't self-trigger the very pattern it's testing) -- see hollow_test.py's own module
docstring and test_hollow_test_analyzer.py/test_hollow_test_fp.py, which already use inline literals
with zero JSON corpus, exactly like gate.liveness's own tests. This JSON corpus exists because the
mission spec explicitly asks for the artifact, not because inline literals were unsafe.
"""
from __future__ import annotations
import json
from pathlib import Path

from makoto.checks.hollowTest import analyze_file

CASES_PATH = Path(__file__).resolve().parent / "hollow_test_cases.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_cases_file_is_well_formed():
    assert isinstance(CASES, list) and len(CASES) > 0
    required = {"id", "source", "path", "expect_fire", "note"}
    for case in CASES:
        assert required <= set(case), f"case missing required key(s): {case.get('id', case)}"
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)), "duplicate case ids"


def test_every_shipped_sub_pattern_has_a_fires_case():
    """Coverage measured from what the cases FIRE, not from what they are named.

    This compared fixture `id` strings against a hard-coded set, so a case called
    `fires-tautology` that actually exercises `no_assertion` satisfied it and the tautology
    sub-pattern went uncovered under a name claiming otherwise. The ids are still required to
    match -- a case whose name lies about its subject is its own defect -- but the coverage
    claim is now derived by running each case and reading the `kind` of what came back.
    """
    named = {c["id"] for c in CASES if c["bucket"] == "fires"}
    expected_ids = {
        "fires-no_assertion", "fires-tautology", "fires-swallowed_failure",
        "fires-uncollectable_nested", "fires-uncollectable_always_skip",
    }
    assert named == expected_ids

    fired = {}
    for case in CASES:
        if case["bucket"] != "fires":
            continue
        kinds = {finding.get("kind") for finding in analyze_file(case["source"], case["path"])}
        assert kinds, f"{case['id']}: a fires-case fired nothing, so it covers no sub-pattern"
        fired[case["id"]] = kinds

    # Each case must fire the sub-pattern its NAME claims. `fires-swallowed_failure` also fires
    # no_assertion -- a swallowed failure is an assertion-less body by construction -- so the
    # named kind must be PRESENT, not the only one.
    for case_id, kinds in sorted(fired.items()):
        claimed = case_id.split("-", 1)[1]
        assert claimed in kinds, (
            f"{case_id} is named for {claimed!r} and fires {sorted(kinds)}; the coverage this "
            f"test reports would be about a sub-pattern nothing here exercises")

    covered = set().union(*fired.values())
    assert {cid.split("-", 1)[1] for cid in expected_ids} <= covered, (
        f"a shipped sub-pattern has no case that fires it: covered {sorted(covered)}")


def test_json_fixture_cases_fire_as_expected():
    mismatched = []
    for case in CASES:
        findings = analyze_file(case["source"], case["path"])
        fired = bool(findings)
        if fired != case["expect_fire"]:
            mismatched.append((case["id"], case["expect_fire"], fired, findings))
    assert mismatched == [], f"case(s) did not match expect_fire: {mismatched}"
