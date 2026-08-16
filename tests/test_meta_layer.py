"""tests for Check.layer -- catches drift on the two known-meta checks (see _loader.Check's
own docstring for why only these two, not all four originally proposed, are tagged "meta")."""
from makoto.registry import load_checks

_KNOWN_META_IDS = {"content.self_mute_guard", "gate.self_wired"}


def test_known_meta_checks_are_tagged_meta():
    checks = {c.id: c for c in load_checks()}
    for check_id in _KNOWN_META_IDS:
        assert check_id in checks, f"{check_id} not discovered by the loader"
        assert checks[check_id].layer == "meta", f"{check_id} lost its layer='meta' tag"


def test_general_purpose_audit_checks_stay_object_layer():
    # envGatedAudit/integritySuppressionFlag watch ANY audit-suppression pattern, not
    # specifically Makoto's own machinery -- they keep their makoto-allow escape hatch and
    # must NOT be silently upgraded to meta (see _loader.Check's docstring for why that would
    # regress real FP-tuning work on general, non-Makoto-specific audit code).
    checks = {c.id: c for c in load_checks()}
    for check_id in ("content.env_gated_audit", "content.integrity_suppression_flag"):
        assert check_id in checks, f"{check_id} not discovered by the loader"
        assert checks[check_id].layer == "object", (
            f"{check_id} was tagged meta -- this needs a deliberate decision, not a drift")


def test_layer_defaults_to_object_for_every_other_check():
    checks = load_checks()
    non_meta = [c for c in checks if c.id not in _KNOWN_META_IDS]
    assert non_meta, "no non-meta checks discovered -- loader likely broken"
    for c in non_meta:
        assert c.layer == "object", f"{c.id} unexpectedly carries layer={c.layer!r}"
