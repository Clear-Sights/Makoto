"""pattern 1.4 predicate — INTEGRITY-suppression flag WITHOUT an ADR backlink.

Fires when a PreToolUse Write/Edit on a `.toml` config file introduces a
suppression flag whose key NAMES an integrity / verification / audit concept
(`audit|verif|integrit|attest|checksum|signatur|tamper|provenance`) carrying a
`_(skip|bypass|inapplicable)` suffix set `= true`, AS A STANDALONE ASSIGNMENT
LINE — UNLESS an `ADR-NNN` backlink (e.g. a `*_rationale = "ADR-042"` line) or a
`makoto-allow:` marker is present.

SCOPE (2026-06-02, warning-tier-elimination cert — graduated to BLOCKING):
  * target is `.toml` ONLY (real machine-read config). `.md` was DROPPED: markdown
    is prose/docs, where these flags appear as inline-code / table / fenced
    EXAMPLES, never as live config — every corpus FP was a `.md` doc quoting an
    example. A documented future extension may add `.yaml`/`.ini` if those config
    surfaces appear in-ecosystem (none do today; YAGNI).
  * the key must NAME an integrity concept. A bare perf toggle (`cache_skip`,
    `retry_skip`) is NOT an integrity check, so makoto firing on it would be an
    ILLUSORY word (not material). Narrowing to integrity-named keys is what makes
    1.4's fire MATERIAL — a real suppressed integrity check.
  * full-LINE anchor (`^...= true`, MULTILINE): the flag must be a standalone
    assignment line, so an inline/table mention in prose cannot match.

ACKNOWLEDGED FN (cert §1.4): a DELIBERATELY-misnamed integrity suppression (e.g.
`cache_skip = true` where "cache" is really the audit cache) evades. The threat
model is honest-but-sloppy, not adversarial-deceptive-naming — and the original
pattern was equally evadable (rename off `_skip`). Narrowing trades that
unchanged adversarial FN for elimination of the honest-config FP class.

Built from the regex_file_predicate factory; the ADR-backlink carve-out is the
factory's optional `exempt_rx`. Knight-Leveson: stdlib re only.
"""
from __future__ import annotations
import re
from makoto.lib.factories import regex_file_predicate
from makoto.lexicons import _INTEG_VOCAB as _INTEG   # shared L0 integrity vocab (single source)

_TARGET_RX = re.compile(r"\.toml$")

# `_INTEG` is the shared L0 integrity vocabulary (imported above from lexicons; the narrowing
# rationale is homed there). `p14._INTEG` stays a module attribute; pattern_1_2 (env-gated audit)
# consumes the same source.

# a STANDALONE assignment line whose key names an integrity concept and carries a
# suppression suffix set true: `^ <integ>..._skip = true`. MULTILINE so `^`/`$`
# bind to each physical line; quotes optional for TOML quoted keys.
_FLAG_RX = re.compile(
    r"(?im)^[ \t]*[\"']?\w*(?:" + _INTEG + r")\w*_(?:skip|bypass|inapplicable)[\"']?"
    r"[ \t]*=[ \t]*true\b"
)

# an ADR backlink anywhere in the same content documents the suppression -> exempt.
_ADR_BACKLINK_RX = re.compile(r"\bADR-\d+\b")

predicate = regex_file_predicate(
    target_rx=_TARGET_RX, body_rx=_FLAG_RX,
    exempt_rx=_ADR_BACKLINK_RX, exempt_label="ADR backlink",
)
