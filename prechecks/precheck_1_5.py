"""pattern 1.5 predicate — DEFERRED checkbox theater on a 'completed' T-item.

Fires when PreToolUse writes docs/pristine-baseline.md with a checked-off
DEFERRED line — '[x] DEFERRED' is checkbox theater: the item isn't actually
done, just deferred. Either complete or leave unchecked.
Scaffold extracted to lib.factories.regex_file_predicate (1.0.3 R1).
Knight-Leveson: stdlib re only.
"""
from __future__ import annotations
import re
from makoto.lib.factories import regex_file_predicate


predicate = regex_file_predicate(
    target_rx=re.compile(r"docs/pristine-baseline\.md$"),
    body_rx=re.compile(r"\[\s*x\s*\]\s+DEFERRED|\[\s*x\s*\]\s+deferred"),
)
