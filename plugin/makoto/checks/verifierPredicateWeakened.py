"""content.verifier_predicate_weakened predicate — verifier predicate weakened (loose-comparator shape).

Reads tool_input.content (NOT disk) per the §5.6 semantic-frame correction.
Scaffold extracted to substrate.factories.regex_file_predicate (1.0.3 R1).
Knight-Leveson: stdlib re only.
"""
# See docs/adr/0035-jscpd-clone-flag-verifications.md for why this module's jscpd clone flag
# against deferredCheckboxTheater.py was verified and dismissed (both already reuse the one
# shared regex_file_predicate factory; the matched span is call-site syntax, not shared logic).
# tests/test_no_alpha_duplicate_functions.py is the package's real duplicate-logic gate.
from __future__ import annotations
import re
from makoto.kit import regex_file_predicate


predicate = regex_file_predicate(
    target_rx=re.compile(r"constitution/integrity/checks/[^/]+\.py$"),
    body_rx=re.compile(r"\bstartswith\(|\bendswith\(|\bre\.match\b|\bre\.search\b|\bin\s*\["),
)


from makoto.registry import Check as _Check
RETRY_HINT = "Use '==' for status comparison, not '.startswith()' / '.endswith()' / 're.match'. Loose comparators weaken the verifier per ADR-058 and CLAUDE.md commandment 3."
DESCRIPTION = 'verifier predicate weakened — loose-comparator shape'

CHECK = _Check(id='content.verifier_predicate_weakened', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('startswith(', 'endswith(', 're.match', 're.search', 'in ['), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="PATTERN_MATCH")
