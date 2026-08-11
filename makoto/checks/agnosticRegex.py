"""Three exact PreToolUse regex checks, registered from one data table.

These checks have the same observable algorithm: on PreToolUse, match a target path,
optionally exempt a whole payload, regex-search the introduced text, then emit the standard
Finding.  Their only distinctions are table data.  ``predicate`` dispatches by ``pattern.id``;
the loader sees the first check as ``CHECK`` and the remaining two as ``EXTRA_CHECKS``.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

from makoto.core.lexicons import _INTEG_VOCAB as _INTEG
from makoto.core.schema import Finding, PreCheck
from makoto.substrate._loader import Check
from makoto.substrate.factories import regex_file_predicate


@dataclass(frozen=True)
class RegexCheckSpec:
    """All behavior that may differ between otherwise-identical regex checks."""
    id: str
    target_pattern: str
    body_pattern: str
    keywords: tuple[str, ...]
    retry_hint: str
    description: str
    corpus_stem: str
    legacy_id: str
    exempt_pattern: str = ""
    exempt_label: str = ""


SPECS = (
    RegexCheckSpec(
        id="content.verifier_predicate_weakened",
        target_pattern=r"constitution/integrity/checks/[^/]+\.py$",
        body_pattern=r"\bstartswith\(|\bendswith\(|\bre\.match\b|\bre\.search\b|\bin\s*\[",
        keywords=("startswith(", "endswith(", "re.match", "re.search", "in ["),
        retry_hint="Use '==' for status comparison, not '.startswith()' / '.endswith()' / 're.match'. Loose comparators weaken the verifier per ADR-058 and CLAUDE.md commandment 3.",
        description="verifier predicate weakened — loose-comparator shape",
        corpus_stem="verifierPredicateWeakened",
        legacy_id="1.1",
    ),
    RegexCheckSpec(
        id="content.integrity_suppression_flag",
        target_pattern=r"\.toml$",
        body_pattern=(
            r"(?im)^[ \t]*[\"']?\w*(?:" + _INTEG + r")\w*_(?:skip|bypass|inapplicable)[\"']?"
            r"[ \t]*=[ \t]*true\b"
        ),
        keywords=("_skip", "_bypass", "_inapplicable"),
        retry_hint='Suppression flags on an integrity/verification/audit-named key require an ADR backlink (*_rationale = "ADR-NNN") or a `makoto-allow: <reason>` marker. Add the rationale or remove the flag.',
        description="integrity-named suppression flag (_skip/_bypass/_inapplicable=true) in a .toml without ADR backlink",
        corpus_stem="integritySuppressionFlag",
        legacy_id="1.4",
        exempt_pattern=r"\bADR-\d+\b",
        exempt_label="ADR backlink",
    ),
    RegexCheckSpec(
        id="content.deferred_checkbox_theater",
        target_pattern=r"docs/pristine-baseline\.md$",
        body_pattern=r"\[\s*x\s*\]\s+DEFERRED|\[\s*x\s*\]\s+deferred",
        keywords=("DEFERRED", "deferred"),
        retry_hint="Open T-items use '[ ]'; completed use '[x]'. The literal text 'DEFERRED' on a completed checkbox is theater. Either complete the task or leave the box unchecked.",
        description="DEFERRED checkbox theater on open T-item",
        corpus_stem="deferredCheckboxTheater",
        legacy_id="1.5",
    ),
)


def _predicate_for(spec: RegexCheckSpec):
    exempt_rx = re.compile(spec.exempt_pattern) if spec.exempt_pattern else None
    return regex_file_predicate(
        target_rx=re.compile(spec.target_pattern),
        body_rx=re.compile(spec.body_pattern),
        exempt_rx=exempt_rx,
        exempt_label=spec.exempt_label,
    )


def _build_predicates() -> dict[str, object]:
    predicates = {}
    for spec in SPECS:
        built = _predicate_for(spec)
        predicates[spec.id] = built
        predicates[spec.legacy_id] = built
    return predicates


PREDICATES = _build_predicates()


def predicate(*, current_event: dict, history: list, pattern: PreCheck,
              conn=None) -> Optional[Finding]:
    """Run the table-selected regex predicate; foreign IDs are intentionally inert."""
    selected = PREDICATES.get(pattern.id)
    if selected is None:
        return None
    return selected(current_event=current_event, history=history, pattern=pattern, conn=conn)


def _check_for(spec: RegexCheckSpec) -> Check:
    return Check(
        id=spec.id,
        applies_at="Pre",
        posture="BLOCK",
        predicate_module=__name__,
        keywords=spec.keywords,
        retry_hint=spec.retry_hint,
        description=spec.description,
    )


# Kept as named constants because the catalog's voice audit requires the CHECK export to use them.
RETRY_HINT = SPECS[0].retry_hint
DESCRIPTION = SPECS[0].description
CHECK = Check(id=SPECS[0].id, applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=SPECS[0].keywords, retry_hint=RETRY_HINT, description=DESCRIPTION)
EXTRA_CHECKS = [_check_for(spec) for spec in SPECS[1:]]
