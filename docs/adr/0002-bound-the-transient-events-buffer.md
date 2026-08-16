# 0002. Bound the transient events buffer

## Status

Accepted.

## Decision and context

The `events` table is a transient evidence buffer, not a durable log. Its only production reader is `_select_recent`, which never looks back past a one-hour same-session window. Anything older is dead weight.

Makoto keeps a small multiple of that window and prunes the rest on every ingest. This hard-bounds the table to approximately one working window's worth of rows regardless of how many sessions accumulate, so the database cannot grow without limit.

Durable cross-session state lives in the ledger and commitments; the fire (blocking-event) log lives in `audit.jsonl`. Neither is touched by this pruning.
