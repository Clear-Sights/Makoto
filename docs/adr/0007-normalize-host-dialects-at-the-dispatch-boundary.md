# 0007. Normalize host dialects at the dispatch boundary

## Status

Accepted.

## Decision and context

The `makoto.core.hostdialect` boundary converts whatever spelling the host sent into the protocol every downstream reader assumes. It is applied after the envelope has proven evaluable — parseable and an object — and before anything routes on or persists it. Routing, gates, history, commitments, and audit therefore see one canonical payload instead of each learning a second dialect.

Cursor loads Claude-Code-compatible hook wiring but delivers camelCase names such as `preToolUse`. Under wildcard-law routing, that spelling ran the wrong handler and persisted a row every history decoder was blind to, tracked as issue #19.

The unevaluable-envelope refusals remain unchanged. Normalization only adjusts known events' capitalization, and `canonical_event` can return only a name already in `HANDLERS`; a genuinely unknown event still follows the same wildcard path as before.

Makoto persists what it evaluated, not the host's original spelling. The events table is the rolling substrate every history decoder reads, and those decoders key on the payload's `hook_event_name` and `tool_name`. Ingesting a raw dialect envelope would leave `event.identical_retry`, `canon.recur`, `canon.timeout`, and the claim-graph Bash evidence path reading zero matching rows for a Cursor session: admitted live, then invisible to every history-derived gate.

The serialized payload is rewritten only when normalization changed something, so a host already speaking the protocol still ingests its own bytes byte-identically. Serialization uses `ensure_ascii=False`: the default would escape non-ASCII as `\uXXXX`, but `_keyword_hit` prefilters the Pre catalog with a raw substring scan. An escaped row could match a non-ASCII keyword on a protocol host and silently miss it on a dialect host, reproducing the exact “check that reads nothing” failure this boundary prevents.
