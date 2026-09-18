"""gate.undischarged_waiver (register B9 WAIVER NEVER EXPIRES) -- the discharge law.

The gate's claim is narrow and it is the whole check: a waiver fires only when NOTHING, neither
the instrument nor the text, can say when it ends. So the tests come in pairs -- the same
directive with and without an end named -- and a third group pins the three forms the INSTRUMENT
discharges (`@ts-expect-error`, `xfail`, `skipif`), which must stay silent however permanent they
look.

Fixture note: every directive below is built by concatenation rather than written as a literal.
The gate reads a comment opener and its keyword on ONE line, and this file is real content to a
grep -- assembling the markers keeps this suite from becoming the thing it tests, which is this
ecosystem's standing lesson (scour refused to run on its own tree over a literal marker in a
test).
"""
from __future__ import annotations

import pytest

from makoto.checks.undischargedWaiver import (
    CHECK, _undischarged_directives, undischarged_waiver_gate,
)

H = "#"          # a comment opener, assembled
SL = "//"


def _mutation_row(new_string: str, file_path: str = "src/parser.py", tool_name: str = "Edit"):
    key = {"Edit": "new_string", "Write": "content"}.get(tool_name, "new_string")
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": tool_name,
                        "tool_input": {"file_path": file_path, key: new_string},
                        "tool_response": {}}}


# ---- the pairs: the same directive, with and without a named end ----------------------------

_DIRECTIVES = [
    f"{H} noqa",
    f"{H} nosec",
    f"{H} type: ignore",
    f"{H} pylint: disable=line-too-long",
    f"{H} pyright: ignore",
    f"{H} pragma: no cover",
    f"{SL} eslint-disable-next-line",
    f"{SL} ts-ignore",
]


@pytest.mark.parametrize("directive", _DIRECTIVES)
def test_every_directive_fires_bare(directive):
    """Undischarged is the firing case, once per directive in the vocabulary."""
    assert _undischarged_directives(f"value = parse(raw)  {directive}"), directive


@pytest.mark.parametrize("directive", _DIRECTIVES)
@pytest.mark.parametrize("end", ["until #123", "ADR-42", "PROJ-77", "2026-11-01",
                                 "remove when the upstream stub lands", "expires 2026-12"])
def test_every_directive_is_silent_once_an_end_is_named(directive, end):
    """...and silent the moment the same line names an end. Both directions, so neither the
    directive vocabulary nor the discharge vocabulary can go dead without this reddening."""
    assert not _undischarged_directives(f"value = parse(raw)  {directive}  {H} {end}")


def test_an_end_on_the_line_above_discharges_it():
    """A rationale conventionally sits above the directive it explains, so the window is the
    directive's own line plus the one directly above."""
    body = f"{H} drop when the vendored parser is upgraded, see ADR-42\nvalue = parse(raw)  {H} noqa"
    assert not _undischarged_directives(body)


def test_an_end_two_lines_above_does_not_discharge_it():
    """The window stops at one line. checks/integritySuppressionFlag.py measured whole-content
    scope as a laundering token: one unrelated reference anywhere in the payload disarmed that
    check silently. A discharge two lines away is not attached to the directive."""
    body = f"{H} remove when the vendored parser is upgraded\n{H} unrelated\nvalue = parse(raw)  {H} noqa"
    assert _undischarged_directives(body)


# ---- the instrument's own discharge: the three excluded forms --------------------------------

def test_ts_expect_error_is_not_a_waiver():
    """The compiler errors when the suppressed error disappears -- the instrument discharges it."""
    assert not _undischarged_directives(f"{SL} @ts-expect-error\nfoo(bar)")


def test_a_bare_skip_fires_but_skipif_does_not():
    """A bare skip has no end; `skipif`'s condition is re-evaluated on every run. The pair is the
    principle stated as a test: the vocabulary is not 'bad words', it is whether an end exists."""
    assert _undischarged_directives("@pytest.mark.skip(reason='flaky')\ndef test_x(): pass")
    assert not _undischarged_directives(
        "@pytest.mark.skipif(sys.platform == 'win32', reason='n/a')\ndef test_x(): pass")


def test_xfail_is_not_a_waiver():
    """The runner reports an XPASS when the test starts passing, so the end is in its output."""
    assert not _undischarged_directives("@pytest.mark.xfail\ndef test_x(): pass")


# ---- the anchor: what keeps a keyword from matching outside a comment ------------------------

def test_a_keyword_in_a_string_literal_does_not_match():
    """The comment-opener anchor is the gate's own self-immunity: a module that spells the
    vocabulary (this one, and the check itself) does not trip it."""
    assert not _undischarged_directives('_RX = re.compile(r"noqa|nosec")')


def test_the_check_module_does_not_fire_on_its_own_source():
    """Measured, not asserted. The lesson this pin exists for is concrete: a literal marker in a
    test made scour refuse to run on its own tree."""
    import makoto.checks.undischargedWaiver as mod
    src = open(mod.__file__, encoding="utf-8").read()
    assert _undischarged_directives(src) == []


# ---- the gate over history -------------------------------------------------------------------

def test_fires_on_a_bare_lint_directive():
    """The scenario tests/test_stop_gate_level_invariant.py names for this gate."""
    finding = undischarged_waiver_gate([_mutation_row(f"value = parse(raw)  {H} noqa")])
    assert finding is not None
    assert finding.pattern_id == "gate.undischarged_waiver"
    assert finding.level == "advisory"
    assert finding.file == "src/parser.py"


def test_silent_on_an_empty_session():
    assert undischarged_waiver_gate([]) is None
    assert undischarged_waiver_gate(None) is None


def test_a_pretooluse_row_introduced_nothing():
    """A PreToolUse row is a call that may never have landed. Only settled mutations count."""
    row = _mutation_row(f"value = parse(raw)  {H} noqa")
    row["payload"]["hook_event_name"] = "PreToolUse"
    assert undischarged_waiver_gate([row]) is None


def test_bash_is_not_read_and_that_is_the_measured_tradeoff():
    """The docstring's recall bound, pinned so it cannot be quietly widened: including Bash would
    advise on a grep FOR waivers, which carries the opener and the keyword on one line. The
    command text below WOULD match the directive scanner -- that is the measurement -- and the
    gate stays silent because Bash is not a mutation tool here."""
    command = f"grep -n '{H} noqa' src/"
    assert _undischarged_directives(command), "the scanner does match it; only the tool gate excludes it"
    row = {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                       "tool_input": {"command": command}, "tool_response": {"stdout": ""}}}
    assert undischarged_waiver_gate([row]) is None


def test_an_undecodable_row_fails_open():
    """A malformed event is no evidence and must never crash a Stop gate."""
    assert undischarged_waiver_gate([object(), None, "not a row"]) is None


def test_several_offenders_are_one_finding_naming_them():
    body = "\n".join([f"a = 1  {H} noqa", f"b = 2  {H} nosec", f"c = 3  {H} type: ignore",
                      f"d = 4  {H} pragma: no cover"])
    finding = undischarged_waiver_gate([_mutation_row(body, tool_name="Write")])
    assert finding is not None
    assert "+1 more" in finding.message


def test_two_directives_on_one_line_are_one_offence():
    """Deduplicated by line, so a line carrying two directives does not inflate the count."""
    assert len(_undischarged_directives(f"a = 1  {H} noqa  {H} nosec")) == 1


def test_the_check_ships_advisory_and_declares_its_shape():
    assert CHECK.posture == "ADVISE"
    assert CHECK.applies_at == "Stop"
    assert CHECK.tests == "PATTERN_MATCH"
    assert CHECK.eats == frozenset({"history"})
