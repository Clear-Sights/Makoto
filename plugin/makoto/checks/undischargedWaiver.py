"""makoto.checks.undischargedWaiver -- gate.undischarged_waiver, register entry
`B9 WAIVER NEVER EXPIRES (+B25)`.

The session introduced a directive that silences a checker, and nothing on or beside it says
when the silence ends. The register states the rule as *"every waiver names a checkable
discharge"* against the fault *"an exemption with no checkable end"*. A waiver with a rationale
but no end is not a carve-out; it is a permanent hole with a sentence attached, and the sentence
is why nobody revisits it.

WHY MAKOTO'S MAP SAID NOT-COUNTABLE, AND WHAT THAT GOT RIGHT. The row read "an exemption's
discharge is not a channel makoto reads", and that is true of the DISCHARGE ITSELF: makoto cannot
tell whether issue #123 closed, whether the date passed, or whether the upstream bug was fixed.
It never needed to. The register's rule is not "the waiver is discharged", it is "the waiver NAMES
a checkable discharge" -- a property of the waiver's own text, and introduced text is a channel
makoto already reads (`kit.introduced_text`, the same one every content precheck uses). The old
verdict answered the harder question nobody asked.

THE PRINCIPLE, WHICH IS ALSO THE NARROWING: a waiver fires only when NOTHING -- neither the
instrument nor the text -- can say when it ends. Three forms are therefore excluded by design,
because the instrument itself discharges them:

  * `@ts-expect-error` -- the compiler errors when the suppressed error disappears.
  * `@pytest.mark.xfail` -- the runner reports an XPASS when the test starts passing.
  * `@pytest.mark.skipif(<cond>)` -- the condition is re-evaluated on every run.

Their undischargeable counterparts (`@ts-ignore`, a bare `@pytest.mark.skip`) do fire. That
asymmetry is the whole check: it is not a lexicon of "bad words", it is the difference between a
waiver that ends on its own and one that cannot.

WHAT COUNTS AS NAMING AN END (`_DISCHARGE_RX`, read over the directive's own line and the line
directly above it -- where a rationale conventionally sits): a tracked item (`#123`, `GH-7`,
`ADR-42`, a `PROJ-123` key), a date or month (`2026-10-01`, `2026-10`), or an explicit temporal
clause (`until ...`, `once ...`, `pending ...`, `remove when ...`, `expires ...`). Scope is one
line above and the directive's own line, NOT the whole content: `checks/integritySuppressionFlag.py`
already measured whole-content scope as a laundering token -- one unrelated `ADR-0` anywhere in the
payload disarmed that check silently.

RECALL BOUNDS, named rather than hidden:
  * The discharge vocabulary is deliberately GENEROUS, because a miss here is a silent gate and a
    miss there is noise. A character-set name shaped like a tracked-item key satisfies the
    `PROJ-123` branch, so a directive whose trailing comment happens to mention one reads as
    discharged. That is the accepted direction of the error.
  * Only Write/Edit/MultiEdit/NotebookEdit are read. A waiver written through `sed -i` or a
    heredoc is not seen. Bash was tried and REFUSED: `introduced_text` hands back the command
    verbatim, so a grep FOR a commented lint directive carries a comment opener and the keyword
    on one line and would be advised as an introduction. A false advisory on looking for waivers
    is worse than missing one written through a stream editor. Measured, not supposed: with Bash
    included, such a grep is reported.
  * PostToolUse rows only. A PreToolUse row is a call that may never have landed, and a waiver
    that was denied introduced nothing.

MAKOTO'S OWN SUITE IS STRICTER THAN THIS GATE, not softer: `tests/_skipGuard.py` refuses a skipped
test outright, so a bare skip cannot reach this tree at all. The gate advises on the agent's
introduced waivers in whatever repository it is working in, which is a different subject.

SELF-REFERENCE, AND WHY THE ANCHOR IS THE ANSWER. A check that spells its own trigger words is
this ecosystem's standing lesson (scour refused to run on its own tree over a literal
`scour-allow` in a test). The comment-opener anchor settles it structurally rather than by an
exemption marker: a directive matches only when a comment opener precedes it ON THE SAME LINE, so
the bare keywords below -- laid out one per line inside a verbose pattern -- do not match this
module's own source. No `makoto-allow:` path exists here and none is wanted: a Stop-tier
`GateContext` carries no `conn`, so an exemption could not be recorded, and an exemption that
leaves no audit row is the laundering token this package refuses everywhere else. That is
`B34 LAW EXEMPTS ITS INSTRUMENT` answered by construction instead of by a carve-out.

ADVISORY TIER, NEVER BLOCK: a deliberately permanent waiver is a real and common thing -- a
vendored file's lint exclusion, a directive on a shape the checker genuinely gets wrong -- and it
looks identical here. No corpus-measured false-positive rate exists, so this gate advises.
"""
from __future__ import annotations

import re
from typing import Optional

from makoto.kit import decode_history_event, introduced_text
from makoto.vocab import Finding

# Only the tools that carry introduced FILE content. Bash is deliberately absent -- see the
# docstring's recall bounds for the measurement that refused it.
_MUTATION_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})

# A checker-silencing directive, COMMENT-ANCHORED: a comment opener, then the keyword, on one
# line. The anchor is what makes this module immune to its own vocabulary (docstring, last
# section) and what keeps a keyword inside a string literal or an identifier from matching.
_DIRECTIVE_RX = re.compile(
    r"""(?x)
    (?:\#|//|/\*|<!--)          # a comment opener ...
    [^\n]*?                     # ... then, later on the SAME line,
    \b(?:
        noqa
      | nosec
      | type:[ \t]*ignore
      | pylint:[ \t]*disable
      | pyright:[ \t]*ignore
      | mypy:[ \t]*disable
      | pragma:[ \t]*no[ \t]*cover
      | eslint-disable(?:-next-line|-line)?
      | ts-ignore
    )\b
    """
)
# A bare test SKIP decorator: the one skip form the runner cannot discharge. `skipif` fails the
# trailing `\b` on its own (the `i` is a word character), and `xfail` is absent by design.
_BARE_SKIP_RX = re.compile(r"(?m)^[ \t]*@(?:pytest\.mark\.)?skip\b")

# An end a reader can go and check. Generous on purpose; the direction of the error is stated in
# the docstring's recall bounds.
_DISCHARGE_RX = re.compile(
    r"""(?x)
      \#\d+                                     # a tracked item: #123
    | \b(?i:gh|adr)[-\ ]\d+                     # GH-7, ADR 42
    | \b[A-Z][A-Z0-9]{1,9}-\d+\b                # a PROJ-123 key
    | \b\d{4}-\d{2}(?:-\d{2})?\b                # 2026-10, 2026-10-01
    | \b(?i:until|once|pending)\b
    | \b(?i:(?:remove|drop|delete|restore|re-?enable|revert)\s+(?:this\s+)?when)\b
    | \b(?i:expir(?:es|y|ation))\b
    """
)
# The rationale's window: the directive's own line plus the one directly above it. NOT the whole
# content -- checks/integritySuppressionFlag.py measured that scope as a laundering token.
_LOOKBACK = 1
# How many offenders the one finding NAMES. A presentation bound, not a detection one: every
# offender is counted, and `+N more` carries the rest. Set here because this is the only layer
# that renders -- checks/relativePathCitation.py makes the same call at 5 for the same reason.
_NAMED = 3


def _undischarged_directives(content: str) -> list:
    """Every silencing directive in `content` whose window names no checkable end.

    Returns `[(line_no, line_text), ...]`, one per offending line, deduplicated by line so a
    line carrying two directives is one offence.
    """
    if not content:
        return []
    lines = content.splitlines()
    offenders, seen = [], set()
    for rx in (_DIRECTIVE_RX, _BARE_SKIP_RX):
        for m in rx.finditer(content):
            line_no = content.count("\n", 0, m.start()) + 1
            if line_no in seen:
                continue
            window = "\n".join(lines[max(0, line_no - 1 - _LOOKBACK):line_no])
            if _DISCHARGE_RX.search(window):
                continue
            seen.add(line_no)
            offenders.append((line_no, lines[line_no - 1].strip()))
    offenders.sort()
    return offenders


def undischarged_waiver_gate(history) -> Optional[Finding]:
    """Fire iff a settled file mutation this session introduced a silencing directive with no
    checkable end named on or above it. One finding for the whole turn, naming the offenders."""
    hits = []
    for row in history or ():
        ev = decode_history_event(row)
        if not isinstance(ev, dict):
            continue                      # fail open: an undecodable row is no evidence
        if ev.get("hook_event_name") != "PostToolUse":
            continue                      # a call that may never have landed introduced nothing
        tool = ev.get("tool_name", "")
        if tool not in _MUTATION_TOOLS:
            continue
        ti = ev.get("tool_input", {}) or {}
        fp = ti.get("file_path", "") if isinstance(ti, dict) else ""
        for _, text in _undischarged_directives(introduced_text(tool, ti)):
            hits.append((fp, text))
    if not hits:
        return None
    named = "; ".join(f"`{t}`" + (f" in {f}" if f else "") for f, t in hits[:_NAMED])
    more = f" (+{len(hits) - _NAMED} more)" if len(hits) > _NAMED else ""
    return Finding(
        pattern_id="gate.undischarged_waiver",
        file=hits[0][0],
        line=0,
        level="advisory",
        message=(
            f"a checker-silencing directive was introduced with no checkable end named on or "
            f"above it: {named}{more}. An exemption with no end is a permanent hole with a "
            f"sentence attached."
        ),
        retry_hint=(
            "Name the discharge beside the directive -- a tracked item (#123, ADR-42), a date, "
            "or a condition (`until ...`, `remove when ...`) -- or use the form the instrument "
            "itself discharges (@ts-expect-error over @ts-ignore, xfail or skipif over a bare "
            "skip), or fix the underlying finding instead of silencing it."
        ),
        snippet=hits[0][1][:200],
    )


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.undischarged_waiver", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="PATTERN_MATCH",
               eats=frozenset({"history"}),
               run=lambda c: undischarged_waiver_gate(c.history))
