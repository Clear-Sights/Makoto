"""gate.unclaimed_unit (register H6 FUNCTION DRAWN FROM NO CLAIM) -- the three claims.

The check asks one question -- does this unit answer to anything on the record -- and the record
offers exactly three ways to say yes. So the tests are one group per claim, each showing the same
unit firing without it and silent with it, followed by the two framework exclusions and the
fragment-tolerance the AST substrate supplies.
"""
from __future__ import annotations

import json

import pytest

from makoto.checks.lineage import unclaimed_CHECK as CHECK, _introduced_units, unclaimed_unit_gate

BARE = "def helper(a):\n    return a + 1\n"


def _unit_write(content, path="src/helpers.py", tool_name="Write"):
    key = {"Write": "content", "Edit": "new_string"}.get(tool_name, "content")
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": tool_name,
                        "tool_input": {"file_path": path, key: content},
                        "tool_response": {}}}


# ---- the fault ------------------------------------------------------------------------------

def test_fires_on_a_unit_nothing_reaches():
    """The scenario tests/test_stop_gate_level_invariant.py names for this gate."""
    finding = unclaimed_unit_gate([_unit_write(BARE)])
    assert finding is not None
    assert finding.pattern_id == "gate.unclaimed_unit"
    assert finding.level == "advisory"
    assert "helper" in finding.message, "the finding must name the unit"
    assert finding.file == "src/helpers.py"


def test_a_class_is_a_unit_too():
    assert unclaimed_unit_gate([_unit_write("class Thing:\n    pass\n")]) is not None


def test_an_edit_introduces_a_unit_as_much_as_a_write():
    assert unclaimed_unit_gate([_unit_write(BARE, tool_name="Edit")]) is not None


def test_a_top_level_lambda_assignment_is_a_unit_too():
    """The same unclaimed-surface question under Python's other function-binding form:
    `name = lambda ...: ...` names a unit exactly as a `def` would, and the AST scan must not
    stop at FunctionDef/AsyncFunctionDef/ClassDef."""
    finding = unclaimed_unit_gate([_unit_write("compute_ratio = lambda a, b: a / b\n")])
    assert finding is not None
    assert finding.pattern_id == "gate.unclaimed_unit"
    assert "compute_ratio" in finding.message


# ---- claim 1: something reaches it ----------------------------------------------------------

def test_a_call_in_the_same_write_discharges_it():
    assert unclaimed_unit_gate([_unit_write(BARE + "\nprint(helper(2))\n")]) is None


def test_a_call_in_a_LATER_write_discharges_it():
    """The session's introduced text is read as one body, so an edited call site in another file
    counts. Splitting a unit from its caller across two writes is the normal way to add one."""
    history = [_unit_write(BARE),
               _unit_write("from helpers import helper\nhelper(1)\n", path="src/main.py")]
    assert unclaimed_unit_gate(history) is None


def test_a_call_in_an_EARLIER_write_discharges_it_too():
    """Unlike the obligation gates, this one is not an ORDER law: a unit written to satisfy a
    call site that was edited first answers to that call. Pinned so the distinction from
    gate.report_before_run stays deliberate rather than accidental."""
    history = [_unit_write("from helpers import helper\nhelper(1)\n", path="src/main.py"),
               _unit_write(BARE)]
    assert unclaimed_unit_gate(history) is None


def test_a_mention_inside_a_longer_identifier_does_not_discharge_it():
    """Exact-token matching: `helper_registry` is a different name, so it is not a use of
    `helper`. A substring match here would discharge a unit by accident."""
    assert unclaimed_unit_gate([_unit_write(BARE + "\nhelper_registry = {}\n")]) is not None


# ---- claim 2: the operator named it ---------------------------------------------------------

def _operator_transcript(tmp_path, *texts):
    """A REAL host transcript, read by the real `ledger.user_turn_texts`.

    Written as a file rather than monkeypatched: the first draft patched
    `makoto.state.ledger.user_turn_texts` and passed alone while FAILING in the full suite,
    because the check imports that name at call time and the patch did not reach it under the
    whole run. A fixture that only holds in isolation is worse than no fixture -- and going
    through the real reader also exercises the spoof-resistance this claim rests on, which a
    stub asserts nothing about.
    """
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(
        json.dumps({"type": "user", "message": {"role": "user", "content": t},
                    "timestamp": f"2026-09-18T10:0{i}:00+00:00"})
        for i, t in enumerate(texts)), encoding="utf-8")
    return str(path)


def test_an_operator_turn_naming_the_unit_discharges_it(tmp_path):
    """The channel is `ledger.user_turn_texts`, host-written turns only -- the same
    spoof-resistant record gate.claimed_consent_absent rests on, inherited rather than
    re-derived."""
    from makoto.state.ledger import user_turn_texts
    path = _operator_transcript(tmp_path, "please add a helper called helper")
    assert "please add a helper called helper" in user_turn_texts(path), \
        "the fixture must be a transcript the real reader accepts, or it proves nothing"
    assert unclaimed_unit_gate([_unit_write(BARE)], transcript_path=path) is None


def test_an_operator_turn_naming_something_else_does_not_discharge_it(tmp_path):
    path = _operator_transcript(tmp_path, "add a parser")
    assert unclaimed_unit_gate([_unit_write(BARE)], transcript_path=path) is not None


def test_an_ASSISTANT_turn_naming_the_unit_does_not_discharge_it(tmp_path):
    """The spoof-resistance, exercised rather than asserted: the agent naming its own unit is
    not the operator asking for it, and `_is_genuine_user_turn` is what keeps the two apart."""
    path = tmp_path / "assistant.jsonl"
    path.write_text(json.dumps({"type": "assistant",
                                "message": {"role": "assistant",
                                            "content": "I will add a helper called helper"},
                                "timestamp": "2026-09-18T10:00:00+00:00"}), encoding="utf-8")
    assert unclaimed_unit_gate([_unit_write(BARE)], transcript_path=str(path)) is not None


def test_a_missing_transcript_fails_open_to_no_evidence(tmp_path):
    """An unreadable transcript is no evidence, not a discharge: the gate still fires, because
    absence of the operator's word is what it was already assuming."""
    assert unclaimed_unit_gate([_unit_write(BARE)],
                               transcript_path=str(tmp_path / "nope.jsonl")) is not None


def test_no_transcript_path_at_all():
    assert unclaimed_unit_gate([_unit_write(BARE)], transcript_path=None) is not None


# ---- claim 3: a decorator registered it -----------------------------------------------------

@pytest.mark.parametrize("decorator", ["@pytest.fixture", "@app.route('/x')", "@property",
                                       "@click.command()", "@functools.lru_cache"])
def test_any_decorator_is_a_claim(decorator):
    """A decorator hands the unit to a framework that will call it, and the framework is the
    source that asks for it. Generalizing over decorators rather than enumerating frameworks is
    what keeps this from being a list that goes stale."""
    content = f"{decorator}\ndef helper():\n    return 1\n"
    assert unclaimed_unit_gate([_unit_write(content)]) is None, decorator
    assert _introduced_units(content) == [], decorator


# ---- the two framework exclusions -----------------------------------------------------------

def test_a_test_function_is_claimed_by_collection():
    """pytest calls it because of its name. A gate demanding a reference would fire on every
    test written -- including the ones in this very file."""
    assert unclaimed_unit_gate([_unit_write("def test_thing():\n    assert True\n",
                                            path="tests/test_thing.py")]) is None


def test_a_method_is_not_a_top_level_unit():
    """Only the class is judged; deciding whether a class needs a given method is a design
    judgement rather than a record read."""
    assert _introduced_units("class Thing:\n    def helper(self):\n        return 1\n") == ["Thing"]


# ---- what the AST substrate supplies --------------------------------------------------------

def test_an_unparseable_fragment_is_never_a_finding():
    """`kit.parse_introduced` degrades to silent, so an Edit fragment that is not a whole
    statement cannot produce a finding -- FN-safe by the same construction the AST prechecks
    rest on."""
    assert unclaimed_unit_gate([_unit_write('", verify=False)', tool_name="Edit")]) is None


def test_a_docstring_mention_counts_as_a_use_and_that_is_the_scans_looseness():
    """The token scan reads the introduced text as one body, so a name written in a DOCSTRING is
    an occurrence and discharges the unit. That is looseness, not a claim: a docstring is neither
    a call nor an operator turn. It is pinned as BEHAVIOUR rather than left to be discovered,
    because the direction of the error is the safe one for an ADVISE gate -- a unit that merely
    documents itself goes unreported, and no unit is reported for documenting itself.

    The first draft of this test was NAMED for the opposite behaviour ("...still fires") while
    asserting this one. A name that contradicts its assertion is a test that misleads the next
    reader about what holds."""
    assert unclaimed_unit_gate([_unit_write('"""helper does a thing."""\n' + BARE)]) is None


def test_prose_files_carry_no_units():
    assert unclaimed_unit_gate([_unit_write("words about helper", path="NOTES.md")]) is None

def test_a_pretooluse_row_introduced_no_unit():
    row = _unit_write(BARE)
    row["payload"]["hook_event_name"] = "PreToolUse"
    assert unclaimed_unit_gate([row]) is None
