"""makoto.checks.unclaimedUnit -- gate.unclaimed_unit, register entry
`H6 FUNCTION DRAWN FROM NO CLAIM`.

The session added a unit that answers to nothing. The register states the fault as *"a unit
answering to nothing in the source"* against the rule *"one source claim per unit, or delete
it"*. A function nobody asked for and nothing reaches is not neutral: it is surface that every
later reader has to understand, every later change has to keep working, and no requirement
protects.

WHAT COUNTS AS A CLAIM, and all three are on the record makoto already reads:

  1. THE OPERATOR NAMED IT -- the unit's name appears in a genuine operator turn
     (`ledger.user_turn_texts`, host-written turns only, the same spoof-resistant channel
     gate.claimed_consent_absent and content.unsourced_webfetch read).
  2. SOMETHING REACHES IT -- the name appears somewhere in this session's introduced text other
     than its own definition: a call, an export, a test, an edited call site.
  3. A DECORATOR REGISTERED IT -- `@pytest.fixture`, `@app.route`, `@property`, `@click.command`.
     A decorator IS a claim: it hands the unit to a framework that will call it, and the
     framework is the source that asks for it. This is the exclusion that makes the check
     material rather than noisy, and it generalizes instead of enumerating frameworks.

Absent all three, the unit was drawn from no claim.

TWO EXCLUSIONS BEYOND THE THREE CLAIMS, each for a measured reason:
  * A `test_`-prefixed def is claimed BY COLLECTION. pytest calls it because of its name, so
    nothing needs to reference it and a gate that demanded a reference would fire on every test
    written -- including the ones in this very change. Naming the prefix is naming the framework
    contract, not a carve-out.
  * TOP-LEVEL defs and classes only. A method answers to its class, which is a claim one level
     up, and deciding whether a class needs a given method is a design judgement rather than a
     record read.

RECALL BOUNDS:
  * A public API entry point added for an external caller fires, because no caller exists in this
    repository to reach it. That is the honest ADVISE case: from the record, an unreachable new
    unit and a premature abstraction look the same, and the reader is the one who can tell.
  * The unit must be in text that PARSES as Python. `kit.parse_introduced` is fragment-tolerant
     and degrades to silent, so an unparseable Edit fragment is never a finding -- FN-safe by
     the same construction the AST prechecks rest on.
  * Name matching is by exact token. An operator asking for "a helper that does X" without
    naming it does not discharge the obligation, and the alternative -- reading intent out of
    prose -- is the judgement `F12`'s row declines for this tree.

DISCRIMINANT AGAINST `gate.liveness`, which also analyses written Python: that gate asks whether
a STATEMENT can affect anything (a pure expression whose value is dropped) inside code the
session touched, reading it off DISK by path. This one asks whether a DEFINITION answers to
anything, reading the session's own introduced text out of history, and its finding is a unit
that is perfectly live -- it simply has no claim. A session whose only act is writing one
unreferenced, undecorated function fires this gate and gives gate.liveness nothing: a `def` is
not a dropped pure statement.

ADVISORY TIER, NEVER BLOCK: the recall bounds above are the benign cases and they look identical
from the record, and no corpus-measured false-positive rate exists.
"""
from __future__ import annotations

import ast
import re
from typing import Optional

from makoto.kit import decode_history_event, introduced_text, parse_introduced
from makoto.vocab import Finding

_MUTATION_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})
# Claimed BY COLLECTION: the runner calls it because of its name. See the docstring.
_COLLECTED_PREFIX = "test_"
# How many whole-word occurrences of the unit's name in the session's introduced text mean
# something REACHES it. Set here because this layer is where the definition and its uses are
# one body: the `def`/`class` line contributes the first occurrence, so a second is the
# earliest evidence of a use. It is a property of the counting, not a tunable threshold --
# 1 would let every definition discharge itself and 3 would demand two callers.
_REACHED_AT = 2


def _introduced_units(text: str) -> list:
    """Top-level `def`/`class` names introduced by `text`, minus the ones a framework claims.

    A DECORATED unit is excluded here rather than discharged later, because the decorator is the
    claim -- there is nothing left to look for once one is present.
    """
    tree, _ = parse_introduced(text)
    if tree is None:
        return []                    # unparseable fragment -> never a finding (FN-safe)
    out = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.decorator_list:
            continue                 # a framework registered it: that IS the claim
        if node.name.startswith(_COLLECTED_PREFIX):
            continue                 # claimed by collection
        out.append(node.name)
    return out


def unclaimed_unit_gate(history, *, transcript_path=None) -> Optional[Finding]:
    """Fire iff this session introduced a top-level unit whose name answers to nothing: no
    operator turn names it, nothing in the session's own introduced text reaches it, and no
    decorator registered it."""
    introduced, defined = [], []
    for row in history or ():
        ev = decode_history_event(row)
        if not isinstance(ev, dict) or ev.get("hook_event_name") != "PostToolUse":
            continue
        tool = ev.get("tool_name", "")
        if tool not in _MUTATION_TOOLS:
            continue
        ti = ev.get("tool_input", {}) or {}
        text = introduced_text(tool, ti) if isinstance(ti, dict) else ""
        if not text:
            continue
        introduced.append(text)
        for name in _introduced_units(text):
            defined.append((name, str(ti.get("file_path", ""))))
    if not defined:
        return None
    # REACHED: the name appears in the session's introduced text beyond its own `def`/`class`
    # line. One occurrence is the definition itself; a second is a use.
    blob = "\n".join(introduced)
    unclaimed = [(n, f) for n, f in defined
                 if _token_count(blob, n) < _REACHED_AT and not _named_by_operator(n, transcript_path)]
    if not unclaimed:
        return None
    name, where = unclaimed[0]
    more = f" (+{len(unclaimed) - 1} more)" if len(unclaimed) > 1 else ""
    return Finding(
        pattern_id="gate.unclaimed_unit",
        file=where,
        line=0,
        level="advisory",
        message=(
            f"`{name}` was added and answers to nothing on the record{more}: no operator turn "
            f"names it, nothing this session wrote reaches it, and no decorator registered it."
        ),
        retry_hint=(
            "Point the unit at its claim -- call it, export it, test it, or decorate it -- or "
            "delete it. A unit no requirement protects is surface every later change has to keep "
            "working."
        ),
        snippet=name[:200],
    )


# Every identifier-shaped token. One expression rather than the hand-rolled character loop this
# started as: that loop was ten lines and a two-branch dispatch with no else, which scour's C5
# probe named -- correctly, even though the missing branch was a genuine no-op. A stdlib call with
# no branches at all cannot have a fallthrough.
_TOKEN_RX = re.compile(r"[A-Za-z0-9_]+")


def _words(blob: str) -> list:
    """The identifier-shaped tokens of `blob`. Exact-token by construction: see the module
    docstring's recall bound on why prose intent is not read."""
    return _TOKEN_RX.findall(blob or "")


def _token_count(blob: str, name: str) -> int:
    """Whole-word occurrences of `name` in `blob`."""
    return sum(1 for tok in _words(blob) if tok == name)


def _named_by_operator(name: str, transcript_path) -> bool:
    """True iff a GENUINE operator turn names the unit. Spoof-resistance is inherited, not
    re-derived: `ledger.user_turn_texts` admits only host-written turns, the same channel
    gate.claimed_consent_absent rests on. Import is call-time for the same reason that check's
    is -- a Stop gate must not carry an import-time edge into the store."""
    if not transcript_path:
        return False
    try:
        from makoto.state.ledger import user_turn_texts
        turns = user_turn_texts(transcript_path)
    except Exception:
        return False                 # fail open: an unreadable transcript is no evidence
    return any(name in _words(t or "") for t in turns or ())


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.unclaimed_unit", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="PATTERN_MATCH",
               eats=frozenset({"history", "transcript_path"}),
               run=lambda c: unclaimed_unit_gate(c.history,
                                                 transcript_path=c.transcript_path))
