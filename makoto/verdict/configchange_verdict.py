"""Pure detection logic for a hypothetical `ConfigChange` hook adapter — NOT a live hook.

Background (see `docs/self-defense-asymmetry-followup.md`, "2026-07-05 followup" section): Makoto's
Stop-time `gate.self_wired` (`checks/selfWiredCheck.py`, migrated from `stopchecks/stopcheck_self_wired.py`
in SPEC-5 Task 4) can only ever see a PARTIAL strip
of its own PreToolUse/PostToolUse/Stop hook entries in `.claude/settings.json` — a single edit that
removes all three simultaneously also removes the Stop entry that would have reported the loss, so
the check has zero coverage against the canonical full-strip attack. Claude Code's own `ConfigChange`
hook event (fired by Claude Code's file-watcher when a settings file changes, independent of Makoto's
PreToolUse/PostToolUse/Stop dispatch chain) is architecturally different: it observes the file-level
edit itself, so a full simultaneous strip is exactly the kind of event it fires for.

**This module does NOT close that gap.** It contains only the pure predicate a future `ConfigChange`
hook adapter could call — no hook registration, no `.claude/settings.json` wiring, nothing that runs
in a live session. Wiring a new hook entry, and deciding whether it should be advisory or blocking,
is oversight-config territory (`CLAUDE.md` rule 4: hook wiring, enforcement tiers/defaults) requiring
direct human/main authorization, not a dispatcher/worker-level build. See the followup doc's "Candidate
for a future FABLE decision" section for what that would still take.

**Verified only against constructed payloads.** No real `ConfigChange` event has ever reached this
code — it has not been wired into any hook, so there is no live event stream to test against. The
function below is tested with hand-built payload shapes that match the event's documented schema
(`config_source`, `config_path`); whether Claude Code's real payload matches that schema exactly, with
no additional wrapping, is unverified beyond the documentation research already recorded in the
followup doc.

Detection logic reuse: rather than a third hand-duplicated copy of the "which of PreToolUse/
PostToolUse/Stop lost its makoto-dispatching entry" predicate (`selfWiredCheck.py` already
duplicates it from `install.py` by hand, forced by the `checks` package's own gate-module layering
firewall — see that module's top comment), this module imports `_missing_makoto_events` directly from
`selfWiredCheck`. That firewall (`tests/test_gate_shape.py`, `ALLOWED_IMPORT_ROOTS`) restricts
what a *gate* module may import; it does not restrict what a non-gate module may import from a gate
module (`tests/test_stopcheck_self_wired.py` already imports the same private helpers), so a byte-for-
byte-identical import is possible here instead of a second duplicate.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Callable, Optional

from makoto.checks.selfWiredCheck import _missing_makoto_events

# The two `config_source` values (per Claude Code's documented ConfigChange schema — see the
# followup doc's citations) that can carry Makoto's hook wiring at all. `user_settings` (global,
# outside this repo), `policy_settings` (managed/enterprise, cannot be blocked per the docs and is
# not where a repo-local hook is installed), and `skills` are structurally incapable of carrying
# `.claude/settings.json`'s or `.claude/settings.local.json`'s `hooks` object, so a change to one of
# them is never applicable to this predicate regardless of content.
_APPLICABLE_SOURCES = ("project_settings", "local_settings")


@dataclass(frozen=True)
class ConfigChangeVerdict:
    """The result of evaluating one ConfigChange event against Makoto's hook wiring.

    No `fire_level`/advisory-vs-blocking field on purpose (see module docstring): `fires` is the one
    boolean fact this predicate is willing to assert — a future hook adapter maps it to whatever
    enforcement tier a human/main authorizes, this module does not pick one.
    """
    config_source: str                # verbatim from the event, or None if absent
    config_path: str                  # verbatim from the event, or "" if absent
    applicable: bool                  # False iff config_source can't carry makoto's hook wiring at all
    evaluated: bool                   # False iff applicable but the settings content could not be
                                       # obtained/parsed as a JSON object (fail-open, mirrors gate.self_wired)
    stripped: bool                    # True iff >=1 of PreToolUse/PostToolUse/Stop lost its
                                       # makoto-dispatching entry (only meaningful when evaluated)
    missing_events: tuple             # which event(s) are missing; () if none, not applicable, or not evaluated
    fires: bool                       # applicable AND evaluated AND stripped — the single actionable bit
    reason: str                       # human-readable explanation, for logging/audit


def _get(event, key):
    if isinstance(event, dict):
        return event.get(key)
    return getattr(event, key, None)


def configchange_verdict(event, *, settings_json: Optional[dict] = None,
                          fs_read: Optional[Callable[[str], Optional[str]]] = None) -> ConfigChangeVerdict:
    """Evaluate a `ConfigChange`-shaped `event` against Makoto's own hook wiring.

    `event` carries the two documented ConfigChange fields, `config_source` and `config_path`
    (dict-like or attribute-like; either works via `_get`). The settings file's own content is
    supplied by the caller in one of two ways (caller's choice, not fixed by this function):
      - `settings_json`: the already-parsed JSON object (preferred when the caller already has it,
        e.g. a test, or a future adapter that reads the file itself before calling this function), or
      - `fs_read`: a `path -> Optional[str]` reader called with `event`'s `config_path`, mirroring the
        `fs_read` convention `gate.self_wired` already uses for its own settings.json read.
    If both are omitted, or the content can't be read/parsed as a JSON object, the verdict fails open
    (`evaluated=False`, `fires=False`) — same fail-open philosophy as every other gate in this repo:
    an indeterminate read is not treated as evidence of a strip.

    Not applicable (`applicable=False`) for any `config_source` other than `project_settings` or
    `local_settings`, regardless of content — those are the only two sources capable of carrying
    `.claude/settings.json` / `.claude/settings.local.json`'s `hooks` object.

    Cannot distinguish "never wired" from "just stripped" (same caveat as `gate.self_wired`'s own
    docstring): a settings file that simply never had Makoto's hooks wired produces the identical
    all-three-missing signal as a full strip would.
    """
    config_source = _get(event, "config_source")
    config_path = _get(event, "config_path") or ""

    if config_source not in _APPLICABLE_SOURCES:
        return ConfigChangeVerdict(
            config_source=config_source, config_path=config_path,
            applicable=False, evaluated=False, stripped=False, missing_events=(), fires=False,
            reason=(f"config_source={config_source!r} cannot carry makoto's hook wiring "
                    f"(only {_APPLICABLE_SOURCES!r} can); not evaluated"),
        )

    data = settings_json
    if data is None and fs_read is not None:
        try:
            raw = fs_read(config_path)
        except Exception:
            raw = None
        if raw:
            try:
                data = json.loads(raw)
            except Exception:
                data = None

    if not isinstance(data, dict):
        return ConfigChangeVerdict(
            config_source=config_source, config_path=config_path,
            applicable=True, evaluated=False, stripped=False, missing_events=(), fires=False,
            reason="settings content unavailable or not a JSON object; fail-open, cannot evaluate",
        )

    hooks = data.get("hooks")
    missing = tuple(_missing_makoto_events(hooks if isinstance(hooks, dict) else {}))
    stripped = bool(missing)
    reason = (f"missing makoto-dispatching entries for: {', '.join(missing)}" if stripped
              else "all of PreToolUse/PostToolUse/Stop retain a makoto-dispatching entry")
    return ConfigChangeVerdict(
        config_source=config_source, config_path=config_path,
        applicable=True, evaluated=True, stripped=stripped, missing_events=missing,
        fires=stripped, reason=reason,
    )
