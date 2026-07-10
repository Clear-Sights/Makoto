"""content.deferred_checkbox_theater predicate — DEFERRED checkbox theater on a 'completed' T-item.

Fires when PreToolUse writes docs/pristine-baseline.md with a checked-off
DEFERRED line — '[x] DEFERRED' is checkbox theater: the item isn't actually
done, just deferred. Either complete or leave unchecked.
Scaffold extracted to substrate.factories.regex_file_predicate (1.0.3 R1).
Knight-Leveson: stdlib re only.
"""
# jscpd note (2026-07-09): flagged as a clone against verifierPredicateWeakened.py. Verified: both
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
    target_rx=re.compile(r"docs/pristine-baseline\.md$"),
    body_rx=re.compile(r"\[\s*x\s*\]\s+DEFERRED|\[\s*x\s*\]\s+deferred"),
)


from makoto.substrate._loader import Check as _Check
RETRY_HINT = "Open T-items use '[ ]'; completed use '[x]'. The literal text 'DEFERRED' on a completed checkbox is theater. Either complete the task or leave the box unchecked."
DESCRIPTION = 'DEFERRED checkbox theater on open T-item'

CHECK = _Check(id='content.deferred_checkbox_theater', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('DEFERRED', 'deferred'), retry_hint=RETRY_HINT, description=DESCRIPTION)
