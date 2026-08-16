# 0008. Retire legacy pattern-id aliases

## Status

Accepted.

## Decision and context

The 2026-07-10 epoch reset made canonical `family.name` forms the only pattern ids. The legacy-id alias closure was retired with the alias table itself. Operator state and configurations predating the reset were archived or wiped, so nothing remaining needs to resolve through old ids.
