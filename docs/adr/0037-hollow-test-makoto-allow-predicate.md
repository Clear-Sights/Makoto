# 0037: hollowTest's `makoto-allow` exemption uses the one canonical marker predicate

## Relocated design history

From `makoto/checks/hollowTest.py`'s `_allowed()`:

```text
This was a bare `"makoto-allow" in line` substring test, which exempted a reasonless
`# makoto-allow` — while `makoto_allowed`/`_MAKOTO_ALLOW_RX` (§7.5b, the predicate every
factory-built content check uses) requires a colon and a non-empty reason, and while this
module's OWN finding text tells the author to write `# makoto-allow: <reason>`. The escape
hatch was strictly laxer than the rule makoto installs into the user's CLAUDE.md
("an on-the-record, auditable rationale, never a disguise"), so an exemption marker
asserting an audit trail was accepted without one — the flag-decay bug in miniature, on
the security-relevant path.
```
