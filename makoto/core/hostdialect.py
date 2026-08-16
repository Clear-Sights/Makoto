"""makoto.core.hostdialect -- the host-dialect boundary: one hop from a host's spelling to the protocol.

ONE domain: a hook envelope arrives from SOME host, and every reader downstream of
`dispatch.main()` -- routing, gates, history, audit -- must see the SAME protocol regardless of
which host sent it. Consumed by `dispatch.main()` alone, at the top, immediately after the
payload parses and before anything routes on it. Stdlib-only, no makoto-internal imports: safe
for anything to depend on.

WHY THIS MODULE EXISTS (#19)
`dispatch.main()` routes on an exact-match `HANDLERS` lookup keyed on Claude Code's PascalCase
event names. Cursor loads Claude-Code-compatible hook wiring (including a third-party plugin's
`hooks/hooks.json`) but delivers the event name in camelCase: `preToolUse`, not `PreToolUse`.
Under the wildcard-law routing a `postToolUse` therefore ran the WRONG handler
(`_evaluate_and_gate` instead of `_accumulate`: no ledger row, no plan advance), the Pre-tier
predicates that key on `hook_event_name == "PreToolUse"` silently no-opped, and the persisted
events-table row carried the host's own spelling -- leaving every history decoder that keys on
the protocol names (`canon.timeout`/`canon.recur`, `gate.identical_retry`, the claim-graph Bash
evidence path) blind for the rest of the session. A check that reads nothing reports no finding,
and nothing reports that it read nothing.

WHAT IS DELIBERATELY *NOT* RELAXED
The genuinely unevaluable envelopes -- non-JSON stdin, non-object payload -- keep failing exactly
as before (loud-allow / fail-closed respectively; see `dispatch.main()`'s HYBRID contract). A
genuinely unknown event name (Cursor's native-only `beforeShellExecution`, `sessionEnd`, or
garbage) is left untouched: `canonical_event` can only ever return a name the caller already
declared, so this module cannot invent an event, only recognize one that was already installed
under a different capitalization.

WHY DERIVED, NOT A HAND-WRITTEN ALIAS MAP
The alias index is built FROM the caller's own set of known event names. A hand-maintained
`{"preToolUse": "PreToolUse", ...}` table is a second list of the events, and the failure mode of
a second list is that someone adds a `HANDLERS` row and forgets the alias -- reintroducing exactly
this outage for the new event only, on one host, silently. Deriving means a new event is aliased
the moment it is routable, by construction, with nothing to remember. Folding is applied only
where it is unambiguous: if two known names collide case-insensitively the fold is refused for
that name and exact-match still decides, so the index can never make routing MORE ambiguous than
the caller's own table.

PAYLOAD-FIELD PARITY
Aliasing the event restores routing, but several checks then silently no-op on a foreign host
because the payload FIELDS differ too. `normalize_payload` fills the protocol field from the
host's spelling ONLY when the protocol field is absent, so a host that already speaks the
protocol is passed through untouched.

Deliberately NOT filled: `last_assistant_message`. Cursor's documented stop schema has no
equivalent, and the Stop gates that read it degrade to empty (fail-open) without it. Fabricating
a value -- from a transcript, or from anything else -- would manufacture the very evidence those
gates exist to check. An absent field is an honest gap; a synthesized one is a lie the gate
cannot see through. Closing it needs a real transcript adapter, not a rename.

WHAT GETS PERSISTED
`dispatch` ingests the NORMALIZED payload into the events table whenever normalization changed
anything (a protocol-speaking host still ingests its own bytes, byte-identical). That table is
the rolling substrate every history decoder reads, and those decoders key on the payload's own
`hook_event_name` and `tool_name` -- so persisting the host's spelling instead would admit a
dialect envelope live and then leave it invisible to every history-derived gate for the rest of
the session: host compatibility bought by silently blinding the Stop tier. The dialect itself is
not lost -- it is recorded once per session as a dispatch fact naming the host spellings that
were translated.
"""
from __future__ import annotations

import json

# Host tool-name spellings -> the protocol tool name makoto's atoms key on, each admitted ONLY on
# positive evidence that it is the same tool (see `_TOOL_EVIDENCE`), never on the name alone. A
# rename on faith would route an unrelated tool into the command-reading atoms.
_TOOL_ALIASES = {
    "Shell": "Bash",          # Cursor's shell tool; carries tool_input.command like Bash
}
# The input key whose presence proves the aliased tool really is the protocol tool. `Shell` only
# becomes `Bash` if it actually carries a command to read -- otherwise the atoms would key on a
# tool whose shape they cannot parse, and read nothing while reporting they ran.
_TOOL_EVIDENCE = {
    "Shell": "command",
}

# Host field spellings -> the protocol field, filled ONLY when the protocol field is absent.
_FIELD_ALIASES = {
    "session_id": ("conversation_id",),   # Cursor documents session_id on sessionStart only
    "tool_response": ("tool_output",),    # Cursor sends a JSON *string*, not an object
}


def alias_index(known) -> dict:
    """Map every unambiguous case-folded spelling of `known` to its canonical member.

    Derived from the caller's own event set (see the module docstring): a name is folded only if
    its lowercase form belongs to exactly one known name, so a caller whose table already
    distinguishes two names by case keeps deciding those by exact match alone."""
    counts: dict = {}
    for name in known:
        if isinstance(name, str):
            counts[name.lower()] = counts.get(name.lower(), 0) + 1
    return {name.lower(): name for name in known
            if isinstance(name, str) and counts.get(name.lower()) == 1}


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
            return {"output": value}
        return decoded if isinstance(decoded, dict) else {"output": value}
    return {"output": value}


def normalize_payload(payload: dict, known_events) -> tuple:
    """Return `(normalized_payload, notes)` -- the payload as the protocol, plus what was renamed.

    `notes` is a dict of the host spellings actually encountered, empty when the payload already
    spoke the protocol. It exists so a dialect translation is an auditable event and not an
    invisible one: a silent rename is indistinguishable from a bug the next time a field goes
    missing. The caller owns what to do with a still-unrecognized event -- this function changes
    nothing else about that decision.

    Never mutates the caller's dict; a host already speaking the protocol gets an equal copy.
    The copy is deep on `tool_input`/`tool_response` specifically -- `dict(payload)` alone is
    shallow, and now that the caller persists the normalized dict as the events-table row (see
    the module docstring's WHAT GETS PERSISTED), any future in-place edit of a nested field by a
    handler would silently rewrite the persisted record through the alias. Nothing today mutates
    these in place, but the guarantee should not depend on that staying true."""
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
        if out.get(field) not in (None, ""):
            continue                                  # host already speaks the protocol
        for src in sources:
            if out.get(src) in (None, ""):
                continue
            value = out[src]
            out[field] = _as_response_dict(value) if field == "tool_response" else value
            notes[field] = src
            break

    tool = out.get("tool_name")
    target = _TOOL_ALIASES.get(tool) if isinstance(tool, str) else None
    if target is not None:
        ti = out.get("tool_input")
        evidence = _TOOL_EVIDENCE.get(tool)
        if isinstance(ti, dict) and (evidence is None or ti.get(evidence) not in (None, "")):
            notes["tool_name"] = tool
            out["tool_name"] = target

    return out, notes
