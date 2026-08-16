# 0005. Distinguish meta enforcement tampering

## Status

Accepted.

## Decision and context

`Check.layer` is an `"object" | "meta"` axis defaulting to `"object"`. The decision followed a session pass in which the proposed grouping of `envGatedAudit`, `selfMuteGuard`, `integritySuppressionFlag`, and `selfWiredCheck` was narrowed on re-examination.

`meta` marks a check whose only possible trigger is tampering with Makoto's own audit or enforcement machinery. `object` watches claims and artifacts about the assistant's own work. This is a distinct axis: the assistant lying about its work is different from the assistant disabling the mechanism that would catch the lie.

It is not a blanket tag for checks that mention integrity or audit concepts. `envGatedAudit.py` and `integritySuppressionFlag.py` are general-purpose detectors: they detect any environment-gated audit code or integrity-named suppression flag in a TOML file, regardless of whether Makoto is involved. They deliberately remain `object`. Tagging them `meta` and stripping their `makoto-allow` escape hatch would regress real false-positive tuning documented in each file's “ACKNOWLEDGED FN” sections for cases that are not self-referential.

Only `content.self_mute_guard` and `gate.self_wired` are unambiguously meta because they can fire only on Makoto's own `settings.json` or hook wiring.

`layer="meta"` participates in `makoto.verdict.apply()`'s fold rules. A raw BLOCK from a meta check floors at ASK under LOOSE or SILENT posture instead of softening further. A loose posture setting must not suppress detection of tampering with the mechanism that enforces posture itself. `dispatch._meta_check_ids()` and `dispatch._finding_layer()` thread the layer through `_emit_decision` and `verdict.recheck_certificate`.

`content.self_mute_guard` is Pre-tier with `level="error"`; because Pre-tier is invariantly BLOCK, the floor is live for it today. `gate.self_wired` is Stop-tier ADVISE and never BLOCK, so the floor is present but currently inert. `tests/test_meta_layer.py` asserts that the two known meta ids remain tagged, catching drift if either is untagged or a new Makoto-self-referential check ships untagged.
