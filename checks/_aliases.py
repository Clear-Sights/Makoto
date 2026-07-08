"""checks/_aliases.py -- SPEC-C item 3 (one namespace): a permanent, append-only, bidirectional
resolution table between a check's CURRENT canonical id and any LEGACY id it used to carry.

A rename is otherwise a silent breaking change to a real, operator-facing config surface
(`MAKOTO_DISABLE_PATTERNS`) and to audit-row `pattern_id` history already written to disk for
real sessions -- this table is what keeps a legacy id resolvable FOREVER, so a rename is pure
ADDITION, never subtraction, from an existing operator's point of view.

Only ADD entries here -- a rename never removes an old mapping, even if the check is renamed
again later (a->b->c keeps BOTH a->c and b->c, so every id a check has EVER carried keeps
resolving to whatever it is called today).
"""
from __future__ import annotations

# legacy id -> current canonical id. Permanent, append-only.
LEGACY_TO_CANONICAL: dict[str, str] = {
    "makoto.contract_order": "gate.contract_order",
    "makoto.stale_establisher": "gate.stale_establisher",
    "write.thrash_revert": "event.thrash_revert",
    "makoto.forbidden_location": "event.forbidden_location",
    "makoto.identical_retry": "event.identical_retry",
    "1.1": "content.verifier_predicate_weakened",
    "1.2": "content.env_gated_audit",
    "1.4": "content.integrity_suppression_flag",
    "1.5": "content.deferred_checkbox_theater",
    "1.6": "content.phantom_citation",
    "1.9": "content.unsourced_webfetch",
    "1.21": "content.verifier_exit_masking",
    "1.22": "content.fabricated_commit_sha",
    "1.23": "content.self_mute_guard",
    "1.26": "content.cert_verify_disabled",
    "1.27": "content.verifier_body_hollowed",
    "1.28": "content.jwt_signature_disabled",
    "1.29": "content.cert_none_mode",
    "1.30": "content.timing_unsafe_compare",
    "1.31": "content.jwt_none_alg",
    "1.32": "content.paramiko_host_key_weakened",
    "1.33": "content.cert_reqs_none",
    "1.34": "content.illusory_authorship_trailer",
}


def canonical(id_: str) -> str:
    """The current canonical id for `id_` -- itself, unless `id_` is a known legacy alias."""
    return LEGACY_TO_CANONICAL.get(id_, id_)


def is_legacy(id_: str) -> bool:
    return id_ in LEGACY_TO_CANONICAL
