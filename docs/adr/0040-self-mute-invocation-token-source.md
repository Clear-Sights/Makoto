# 0040: Self-mute guard's invocation-token source

## Relocated design history

From `selfMuteGuard.py`'s `_MAKOTO_CMD_RX` comment:

```text
Imported from `wiring.MAKOTO_INVOCATION_RX` (aliased `_MAKOTO_CMD_RX`) rather than a local
copy: this guard used to hand-roll its own pattern (`makoto_state|dispatch\.sh`, bare
unanchored substrings), and it drifted from the one `install`/`entry_dispatches_to_makoto`
actually recognize -- missing the plugin-manifest shim form
(`${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh`, so gutting a plugin-packaged install was
invisible to this guard) while ALSO over-matching an unrelated `/usr/local/bin/dispatch.sh`
(false-BLOCKing an edit to a hook makoto does not own -- this check's own module docstring
asserts a zero-FP admissibility bar).
```

## Decision

One invocation-token set, one owner: `substrate.wiring`, the stdlib-only module the
pipeline-order firewall already allows this check to import. The guard never carries its own
copy of the pattern.

## Rationale

A hand-rolled duplicate of the recognition pattern can drift from the canonical one in both
directions at once, and each direction is a distinct failure: an under-match is a missed
self-mute (the guard's whole purpose), an over-match is a false BLOCK on a hook makoto does not
own, against a check that asserts a zero-FP admissibility bar.

## Alternatives considered

Keeping a local pattern in the check (rejected: that is exactly the arrangement that drifted).
