"""makoto.core.hostdialect -- the host-dialect boundary: one hop from a host's spelling to the protocol.

One domain: a hook envelope arrives from some host, and every reader downstream of
`dispatch.main()` -- routing, gates, history, audit -- must see the same protocol regardless of
which host sent it. Consumed by `dispatch.main()` alone, at the top, before anything routes on
the payload. Stdlib-only, no makoto-internal imports: safe for anything to depend on.

WHY THIS MODULE EXISTS
`dispatch.main()` routes on an exact-match `HANDLERS` lookup keyed on Claude Code's PascalCase
event names. Cursor delivers the same events in camelCase (`preToolUse`, not `PreToolUse`).
Without translation, a `postToolUse` event runs the wrong handler, Pre-tier predicates keyed on
`hook_event_name == "PreToolUse"` silently no-op, and the persisted events-table row carries the
host's own spelling, blinding every history decoder that keys on the protocol names for the rest
of the session. A check that reads nothing reports no finding, and nothing reports that it read
nothing.

WHAT IS DELIBERATELY NOT RELAXED
Genuinely unevaluable envelopes -- non-JSON stdin, non-object payload -- keep failing exactly as
before (loud-allow / fail-closed; see `dispatch.main()`'s hybrid contract). A genuinely unknown
event name is left untouched: `canonical_event` can only return a name the caller already
declared, so this module cannot invent an event, only recognize one installed under a different
capitalization.

WHY DERIVED, NOT A HAND-WRITTEN ALIAS MAP
The alias index is built from the caller's own set of known event names. A hand-maintained alias
table is a second list of the events, and the failure mode of a second list is that someone adds
a `HANDLERS` row and forgets the alias. Deriving means a new event is aliased the moment it is
routable, with nothing to remember. Folding applies only where unambiguous: if two known names
collide case-insensitively the fold is refused for that name and exact-match still decides, so
the index can never make routing more ambiguous than the caller's own table.

PAYLOAD-FIELD PARITY
Aliasing the event restores routing, but several checks then silently no-op on a foreign host
because the payload fields differ too. `normalize_payload` fills the protocol field from the
host's spelling only when the protocol field is absent, so a host that already speaks the
protocol passes through untouched.

Deliberately not filled: `last_assistant_message`. Cursor's documented stop schema has no
equivalent, and the Stop gates that read it degrade to empty (fail-open) without it. Fabricating
a value would manufacture the very evidence those gates exist to check. An absent field is an
honest gap; a synthesized one is a lie the gate cannot see through.

WHAT GETS PERSISTED
`dispatch` ingests the normalized payload into the events table whenever normalization changed
anything. That table is what every history decoder reads, keyed on `hook_event_name` and
`tool_name` -- so persisting the host's spelling instead would blind every history-derived gate
for the rest of the session. The dialect itself is not lost: it is recorded once per session as a
dispatch fact naming the host spellings translated.
"""
from __future__ import annotations

import json

# Host tool spelling -> (protocol tool, input key proving the alias applies).
_TOOL_ALIASES = {
    "Shell": ("Bash", "command"),
}

# Host field spellings -> the protocol field, filled ONLY when the protocol field is absent.
_FIELD_ALIASES = {
    "session_id": ("conversation_id",),   # Cursor documents session_id on sessionStart only
    "tool_response": ("tool_output",),    # Cursor sends a JSON *string*, not an object
}


def _present(value) -> bool:
    """Does the payload actually carry this value? The empty string counts as ABSENT.

    One rule, one place: a host that sends `"conversation_id": ""` has told us nothing, and
    treating that as a filled protocol field would let an empty spelling shadow a real one."""
    return value not in (None, "")


def alias_index(known) -> dict:
    """Map every unambiguous case-folded spelling of `known` to its canonical member.

    Derived from the caller's own event set (see the module docstring): a name is folded only if
    its lowercase form belongs to exactly one known name, so a caller whose table already
    distinguishes two names by case keeps deciding those by exact match alone."""
    folded: dict = {}
    for name in known:
        if isinstance(name, str):
            low = name.lower()
            folded[low] = None if low in folded else name   # a second spelling refuses the fold
    return {low: name for low, name in folded.items() if name is not None}


def canonical_event(event, known):
    """The member of `known` that `event` names in ANY host's capitalization, else None.

    Exact match wins outright, so a host already speaking the protocol is never reinterpreted.
    None means genuinely unknown -- the caller keeps treating it exactly as before."""
    if not isinstance(event, str):
        return None
    if event in known:
        return event
    return alias_index(known).get(event.lower())


def _as_response_dict(value):
    """A host's tool result as the dict every downstream reader expects.

    Cursor sends `tool_output` as a JSON *string*. A string that decodes to an object is that
    object; anything else is wrapped under `output` rather than dropped -- the readers all use
    `.get`, so a wrapped scalar is inert to them, while discarding it would silently destroy the
    only record that the call produced a result at all."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except Exception:
            decoded = None
        if isinstance(decoded, dict):
            return decoded
    return {"output": value}


def normalize_payload(payload: dict, known_events) -> tuple:
    """Return `(normalized_payload, notes)` -- the payload as the protocol, plus what was renamed.

    `notes` is a dict of the host spellings actually encountered, empty when the payload already
    spoke the protocol: it makes a dialect translation an auditable event rather than an
    invisible one.

    Never mutates the caller's dict. The copy is deep on `tool_input`/`tool_response`
    specifically -- `dict(payload)` alone is shallow, and the caller persists the normalized
    dict as the events-table row, so an in-place edit of a nested field would otherwise rewrite
    the persisted record through the alias."""
    if not isinstance(payload, dict):
        return payload, {}
    out = dict(payload)
    for nested in ("tool_input", "tool_response"):
        if isinstance(out.get(nested), dict):
            out[nested] = dict(out[nested])
    notes: dict = {}

    raw_event = out.get("hook_event_name")
    canon = canonical_event(raw_event, known_events)
    if canon is not None and canon != raw_event:
        notes["hook_event_name"] = raw_event
        out["hook_event_name"] = canon

    for field, sources in _FIELD_ALIASES.items():
        if _present(out.get(field)):
            continue                                  # host already speaks the protocol
        for src in sources:
            if not _present(out.get(src)):
                continue
            value = out[src]
            out[field] = _as_response_dict(value) if field == "tool_response" else value
            notes[field] = src
            break

    tool = out.get("tool_name")
    alias = _TOOL_ALIASES.get(tool) if isinstance(tool, str) else None
    if alias is not None:
        target, evidence = alias
        ti = out.get("tool_input")
        if isinstance(ti, dict) and (evidence is None or _present(ti.get(evidence))):
            notes["tool_name"] = tool
            out["tool_name"] = target

    return out, notes
