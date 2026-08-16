# 0004: Check layer field and meta-layer immunity

Date: 2026-08-16

## Relocated design history

From `Check` in `makoto/registry.py`:

```text
`layer` ("object" | "meta", default "object" -- DESIGN DECISION, session pass after the
envGatedAudit/selfMuteGuard/integritySuppressionFlag/selfWiredCheck grouping was proposed and
then narrowed on re-examination): "meta" marks a check whose ONLY possible trigger is
tampering with Makoto's own audit/enforcement machinery -- as opposed to "object", which
watches claims/artifacts about the assistant's OWN WORK. This is a real, distinct axis (is
the assistant lying about its work vs. is the assistant disabling the thing that would catch
the lie), but it is NOT a blanket tag for "checks that mention integrity/audit concepts" --
envGatedAudit.py and integritySuppressionFlag.py are GENERAL-PURPOSE detectors (any env-gated
audit code, any integrity-named suppression flag in a .toml, regardless of whether it has
anything to do with Makoto itself) and were deliberately left "object" rather than "meta":
tagging them meta and stripping their `makoto-allow` escape hatch would regress real FP-
tuning work (see each file's own "ACKNOWLEDGED FN" sections) for a case that isn't actually
self-referential. Only `content.self_mute_guard` and `gate.self_wired` are unambiguously
meta -- both can ONLY ever fire on Makoto's own settings.json/hook-wiring, nothing else.
`layer="meta"` has TWO consumers: `tests/test_meta_layer.py` asserts the two known-meta
check ids are tagged, catching drift if either is ever un-tagged or a new
Makoto-self-referential check ships untagged; and (wired 2026-08-16, the follow-up this
paragraph used to defer) `makoto.verdict.apply()`'s fold now takes a `layer` argument -- a
meta BLOCK never softens below ASK under LOOSE/SILENT, since a permissive posture must not
be able to suppress detection of tampering with the machinery that enforces posture.
`dispatch._finding_layer` maps the worst finding's pattern_id to its check's layer via the
derived `_meta_check_ids()` set. In practice today only `content.self_mute_guard` (Pre-tier,
BLOCK-capable) exercises the floor; `gate.self_wired` is Stop-tier ADVISE (never BLOCK) so
the floor is structurally present but inert for it. selfMuteGuard's makoto-allow immunity
remains separately hardcoded in its own predicate (never calls the shared `makoto_allowed`
path).
```
