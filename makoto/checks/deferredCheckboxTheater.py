"""content.deferred_checkbox_theater predicate — DEFERRED checkbox theater on a 'completed' T-item.

Fires when PreToolUse writes docs/pristine-baseline.md with a checked-off
DEFERRED line — '[x] DEFERRED' is checkbox theater: the item isn't actually
done, just deferred. Either complete or leave unchecked.
Scaffold extracted to substrate.factories.regex_file_predicate (1.0.3 R1).
Knight-Leveson: stdlib re only.
"""
# See docs/adr/0035-jscpd-clone-flag-verifications.md for why this module's jscpd clone flag
# against verifierPredicateWeakened.py was verified and dismissed (both already reuse the one
# shared regex_file_predicate factory; the matched span is call-site syntax, not shared logic).
# tests/test_no_alpha_duplicate_functions.py is the package's real duplicate-logic gate.
from __future__ import annotations
import re
from makoto.kit import regex_file_predicate


predicate = regex_file_predicate(
    target_rx=re.compile(r"docs/pristine-baseline\.md$"),
    body_rx=re.compile(r"\[\s*x\s*\]\s+DEFERRED|\[\s*x\s*\]\s+deferred"),
)


from makoto.registry import Check as _Check
RETRY_HINT = "Open T-items use '[ ]'; completed use '[x]'. The literal text 'DEFERRED' on a completed checkbox is theater. Either complete the task or leave the box unchecked."
DESCRIPTION = 'DEFERRED checkbox theater on open T-item'

CHECK = _Check(id='content.deferred_checkbox_theater', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('DEFERRED', 'deferred'), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="PATTERN_MATCH")
