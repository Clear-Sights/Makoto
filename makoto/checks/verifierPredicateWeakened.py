"""content.verifier_predicate_weakened predicate — verifier predicate weakened (loose-comparator shape).

Reads tool_input.content (NOT disk) per the §5.6 semantic-frame correction.
Scaffold extracted to substrate.factories.regex_file_predicate (1.0.3 R1).
Knight-Leveson: stdlib re only.
"""
# jscpd note (2026-07-09): flagged as a clone against deferredCheckboxTheater.py. Verified: both
# modules already reuse the ONE shared factory (substrate.factories.regex_file_predicate) -- the
# matched span is just the minimal `regex_file_predicate(target_rx=re.compile(r"...")` call-site
# syntax common to ANY two callers of that factory, plus the shared doc-convention lines. The two
# target_rx/body_rx regexes differ and ARE each check's real, distinct content; collapsing the call
# sites further would mean merging two unrelated file/body patterns into one, which would be wrong.
# This pair is already at the dedup endpoint substrate.factories.regex_file_predicate exists for.
from __future__ import annotations
import re
from makoto.substrate.factories import regex_file_predicate


predicate = regex_file_predicate(
    target_rx=re.compile(r"constitution/integrity/checks/[^/]+\.py$"),
    body_rx=re.compile(r"\bstartswith\(|\bendswith\(|\bre\.match\b|\bre\.search\b|\bin\s*\["),
)


from makoto.substrate._loader import Check as _Check
RETRY_HINT = "Use '==' for status comparison, not '.startswith()' / '.endswith()' / 're.match'. Loose comparators weaken the verifier per ADR-058 and CLAUDE.md commandment 3."
DESCRIPTION = 'verifier predicate weakened — loose-comparator shape'

CHECK = _Check(id='content.verifier_predicate_weakened', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('startswith(', 'endswith(', 're.match', 're.search', 'in ['), retry_hint=RETRY_HINT, description=DESCRIPTION)
