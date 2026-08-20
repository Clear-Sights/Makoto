"""content.integrity_suppression_flag predicate — INTEGRITY-suppression flag WITHOUT an ADR backlink.

Fires when a PreToolUse Write/Edit on a `.toml` config file introduces a
suppression flag whose key NAMES an integrity / verification / audit concept
(`audit|verif|integrit|attest|checksum|signatur|tamper|provenance`) carrying a
`_(skip|bypass|inapplicable)` suffix — or the prefix form `skip_<integ>` /
`bypass_<integ>` — set `= true`, AS A STANDALONE ASSIGNMENT LINE — UNLESS an
`ADR-NNN` backlink ON OR ADJACENT TO the flag line (e.g. a `*_rationale =
"ADR-042"` line) or a `makoto-allow:` marker is present. BOTH carve-outs are
recorded through the exemption sink: an exemption that leaves no audit row is a
laundering token, not a carve-out.

SCOPE (2026-06-02, warning-tier-elimination cert — graduated to BLOCKING):
  * target is `.toml` ONLY (real machine-read config). `.md` was DROPPED: markdown
    is prose/docs, where these flags appear as inline-code / table / fenced
    EXAMPLES, never as live config — every corpus FP was a `.md` doc quoting an
    example. A documented future extension may add `.yaml`/`.ini` if those config
    surfaces appear in-ecosystem (none do today; YAGNI).
  * the key must NAME an integrity concept. A bare perf toggle (`cache_skip`,
    `retry_skip`) is NOT an integrity check, so makoto firing on it would be an
    ILLUSORY word (not material). Narrowing to integrity-named keys is what makes
    content.integrity_suppression_flag's fire MATERIAL — a real suppressed integrity check.
  * full-LINE anchor (`^...= true`, MULTILINE): the flag must be a standalone
    assignment line, so an inline/table mention in prose cannot match.

ACKNOWLEDGED FN (cert §1.4): a DELIBERATELY-misnamed integrity suppression (e.g.
`cache_skip = true` where "cache" is really the audit cache) evades. The threat
model is honest-but-sloppy, not adversarial-deceptive-naming — and the original
pattern was equally evadable (rename off `_skip`). Narrowing trades that
unchanged adversarial FN for elimination of the honest-config FP class.

Built from the regex_file_predicate factory; the ADR-backlink carve-out is a
line-scoped, audited wrapper around it (the factory's whole-content `exempt_rx`
is deliberately NOT used -- it exempts before the recorder runs).
Knight-Leveson: stdlib re only.
"""
from __future__ import annotations
import re
from typing import Optional
from makoto.kit import _record_exemption, regex_file_predicate, scan_target_content
from makoto.vocab import Finding
from makoto.vocab import _INTEG_VOCAB as _INTEG   # shared L0 integrity vocab (single source)

_TARGET_RX = re.compile(r"\.toml$")

# `_INTEG` stays a module attribute under exactly that name: tests/test_lexicons.py pins
# `integritySuppressionFlag._INTEG is vocab._INTEG_VOCAB`. The narrowing rationale is homed with
# the vocabulary in `makoto.vocab`; content.env_gated_audit consumes the same object, no second copy.

# a STANDALONE assignment line whose key names an integrity concept and carries a
# suppression affix set true: suffix form (`audit_skip = true`) or the equally natural
# prefix form (`skip_audit = true`, `bypass_verification = true`). MULTILINE so `^` binds
# to each physical line; quotes optional for TOML quoted keys.
_FLAG_RX = re.compile(
    r"(?im)^[ \t]*[\"']?(?:"
    r"\w*(?:" + _INTEG + r")\w*_(?:skip|bypass|inapplicable)"
    r"|(?:skip|bypass)_\w*(?:" + _INTEG + r")\w*"
    r")[\"']?[ \t]*=[ \t]*true\b"
)

# an ADR backlink documents the suppression -> exempt, but ONLY when it sits on the flag's
# own line or within _ADR_WINDOW adjacent lines (the documented `*_rationale = "ADR-NNN"`
# shape). Whole-content scope was a laundering token: one unrelated `ADR-0` string anywhere
# in the payload disarmed the check silently -- the same measured defeat Ward's
# `_allow_lines` went line-scoped to close.
_ADR_BACKLINK_RX = re.compile(r"\bADR-\d+\b")
_ADR_WINDOW = 2

_flag_predicate = regex_file_predicate(
    target_rx=_TARGET_RX, body_rx=_FLAG_RX, exempt_label="ADR backlink",
)


def predicate(*, current_event: dict, history: list, pattern,
              conn=None) -> Optional[Finding]:
    """The factory predicate plus the LINE-SCOPED, AUDITED ADR carve-out.

    Unlike the factory's whole-content `exempt_rx` (which returns before the exemption
    recorder ever runs), an ADR exemption here is recorded exactly as a `makoto-allow:`
    marker is -- the module docstring presents the two carve-outs as equivalent, so one must
    not vanish where the other leaves an audit row."""
    # `history=()` literal, NOT the incoming parameter: the factory predicate never reads it,
    # and this check's declared eats (current_event/pattern/conn) must stay exact
    # (tests/test_check_law_eats.py rejects an undeclared read).
    finding = _flag_predicate(current_event=current_event, history=(),
                              pattern=pattern, conn=conn)
    if finding is None:
        return None
    content = scan_target_content(current_event.get("tool_input", {}) or {})
    lines = content.splitlines()
    lo = max(0, finding.line - 1 - _ADR_WINDOW)
    hi = finding.line + _ADR_WINDOW
    backlink = _ADR_BACKLINK_RX.search("\n".join(lines[lo:hi]))
    if backlink:
        _record_exemption(current_event, conn, pattern_id=pattern.id, file=finding.file,
                          line=finding.line,
                          reason=f"ADR backlink {backlink.group(0)} adjacent to the flag",
                          snippet=finding.snippet)
        return None
    return finding


from makoto.registry import Check as _Check
RETRY_HINT = 'Suppression flags on an integrity/verification/audit-named key require an ADR backlink (*_rationale = "ADR-NNN") or a `makoto-allow: <reason>` marker. Add the rationale or remove the flag.'
DESCRIPTION = 'integrity-named suppression flag (_skip/_bypass/_inapplicable=true) in a .toml without ADR backlink'

CHECK = _Check(id='content.integrity_suppression_flag', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('_skip', '_bypass', '_inapplicable', 'skip_', 'bypass_'), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="PATTERN_MATCH")
