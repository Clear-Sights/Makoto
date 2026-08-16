"""The ConfigChange feature, whole: the pure strip-detection predicate + the hook ADAPTER — the
real entry point a `.claude/settings.json` `ConfigChange` hook entry invokes via
`python3 -m makoto.configchange`. One feature, one file (Stage 2 seam 6 — merged from
`_dispatch_configchange.py` + `verdict/configchange_verdict.py`, both verbatim).

**WIRED, 2026-07-08 (owner, identifying as Makoto's creator, gave direct, specifically-named
authorization).** `.claude/settings.json` carries a live `ConfigChange` entry pointing at this
module via `dispatch_configchange.sh`. See `docs/self-defense-asymmetry-followup.md`'s
"2026-07-05 followup" sections for the design history; the pure predicate this module's adapter
calls (`configchange_verdict`, below) is unit-tested against constructed payloads.

**TWO TIERS, both owner-authorized (D5, docs/DEFERRED.md):**
  1. **ADVISORY** (unconditional, per DESIGN DECISION 6/9's precedent): the underlying verdict
     firing on a path that has NEVER been recorded as wired or previously-clean always logs a
     stderr line + a best-effort audit-row append. Never blocks. This is the ambiguous
     "never wired vs. just stripped" case `configchange_verdict` itself cannot resolve.
  2. **BLOCKING** (2026-07-08, owner-authorized, FP-safety-scoped): fires ONLY when the strip is
     a genuine, evidenced transition -- either (a) `config_path` is in the installer's own
     manifest of paths it wired (`<state_dir>/configchange_manifest.json`, written by
     `install.cmd_install`), or (b) a PRIOR evaluation of this exact `config_path` observed
     makoto's hooks present (`<state_dir>/configchange_snapshots.json`). A path with neither --
     no manifest entry, no prior "had hooks" observation -- can NEVER block, no matter how many
     times it evaluates as stripped; this is the whole FP-safety property (a project that never
     had makoto's hooks must never be blocked from editing its own settings). On block: the
     documented top-level `{"decision": "block", "reason": ...}` shape on stdout, exit 0 (JSON is
     only processed on exit 0, confirmed against Claude Code's own hooks reference, 2026-07-08).
     Never for `policy_settings` -- already excluded upstream, `configchange_verdict`'s own
     `_APPLICABLE_SOURCES` never includes it, so `verdict.fires` is already False there.

**Verified only against constructed payloads** for the underlying predicate logic (the
predicate section below); a live-fire probe in this session (a scratch, empty
`~/.claude/settings.json` edited mid-session) produced no observed advisory fire -- most likely
because Claude Code snapshots a session's hook set at session start, before this session's own
mid-session wiring landed. Recorded honestly as inconclusive, not claimed as verified-working;
only a hook wired from a session's own start could actually confirm live delivery.
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from dataclasses import dataclass
from typing import Callable

from makoto.checks.selfWiredCheck import _missing_makoto_events
from makoto.state.audit import AuditRow, append_row
from makoto.state.store import _state_dir


# ---- The pure predicate (formerly makoto/verdict/configchange_verdict.py, verbatim) -----------
#
# Background (see `docs/self-defense-asymmetry-followup.md`, "2026-07-05 followup" section):
# Makoto's Stop-time `gate.self_wired` (`checks/selfWiredCheck.py`) can only ever see a PARTIAL
# strip of its own PreToolUse/PostToolUse/Stop hook entries in `.claude/settings.json` — a single
# edit that removes all three simultaneously also removes the Stop entry that would have reported
# the loss, so that check has zero coverage against the canonical full-strip attack. Claude Code's
# `ConfigChange` hook event (fired by the file-watcher when a settings file changes, independent
# of Makoto's dispatch chain) observes the file-level edit itself, so a full simultaneous strip is
# exactly the kind of event it fires for. The adapter section below is what wires this predicate
# to that event.
#
# Detection logic reuse: rather than a third hand-duplicated copy of the "which of PreToolUse/
# PostToolUse/Stop lost its makoto-dispatching entry" predicate, this module imports
# `_missing_makoto_events` directly from `selfWiredCheck`. The gate-module layering firewall
# (`tests/test_import_direction.py`, the pipeline-order firewall) restricts what a *gate* module may import;
# it does not restrict what a non-gate module may import from a gate module.

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
    boolean fact this predicate is willing to assert — the adapter below maps it to whatever
    enforcement tier a human/main authorizes, this predicate does not pick one.
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


# ---- The hook adapter (formerly makoto/_dispatch_configchange.py, verbatim) -------------------

def _make_fs_read(payload: dict):
    """Build a `path -> Optional[str]` reader for `configchange_verdict`'s `fs_read` param.

    Absolute paths are opened directly; relative paths are joined against the payload's `cwd`
    (or `os.getcwd()` if absent) — the same cwd-relative convention `dispatch.py`'s Stop-check
    `fs_read` closures already use. Never raises: any failure (missing file, permissions, a
    directory instead of a file, etc.) is treated as "content unavailable", which
    `configchange_verdict` already fails open on.
    """
    cwd = payload.get("cwd") or os.getcwd()

    def fs_read(path: str) -> Optional[str]:
        try:
            full = path if os.path.isabs(path) else os.path.join(cwd, path)
            if os.path.isfile(full):
                return open(full, encoding="utf-8", errors="replace").read()
        except Exception:
            pass
        return None

    return fs_read


def _record_advisory_fire(payload: dict, verdict) -> None:
    """Loud stderr note (mirrors `dispatch._dispatch_fact`'s style) + a best-effort AuditRow
    append. Wrapped so an observability failure can never break the hook — same fail-open
    philosophy as `dispatch._record_exemption_sink`."""
    print(f"makoto.configchange: ADVISORY {verdict.reason}", file=sys.stderr)
    try:
        state_dir = _state_dir()
        finding = {
            "pattern_id": "gate.configchange_advisory",
            "file": verdict.config_path,
            "line": 0,
            "level": "advisory",
            "message": verdict.reason,
            "retry_hint": "",
            "snippet": "",
            "source_event_id": 0,
        }
        row = AuditRow(
            ts=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            event="live.config_change",
            hook_kind="ConfigChange",
            session_id=payload.get("session_id", ""),
            project_root=payload.get("cwd") or os.getcwd(),
            pattern_fires=["gate.configchange_advisory"],
            exit_code=0,
            retry_hint_emitted=bool(finding["retry_hint"]),
            findings=[finding],
            tool_name="",  # ConfigChange is not tool-scoped
        )
        append_row(state_dir, row)
    except Exception:
        pass  # observability must never break the hook


def _record_block_fire(payload: dict, verdict, reason: str) -> None:
    """Same shape as `_record_advisory_fire`, level="error" -- the blocking tier's own audit
    trail, distinct pattern_id so audit-mining can tell the two tiers apart."""
    try:
        state_dir = _state_dir()
        finding = {
            "pattern_id": "gate.configchange_transition",
            "file": verdict.config_path,
            "line": 0,
            "level": "error",
            "message": reason,
            "retry_hint": "",
            "snippet": "",
            "source_event_id": 0,
        }
        row = AuditRow(
            ts=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            event="live.config_change",
            hook_kind="ConfigChange",
            session_id=payload.get("session_id", ""),
            project_root=payload.get("cwd") or os.getcwd(),
            pattern_fires=["gate.configchange_transition"],
            exit_code=0,
            retry_hint_emitted=False,
            findings=[finding],
            tool_name="",
        )
        append_row(state_dir, row)
    except Exception:
        pass  # observability must never break the hook


# ---- D5 blocking tier (owner-authorized, 2026-07-08): manifest + transition detection ----------

def _manifest_paths() -> set:
    """The set of resolved settings paths `install.cmd_install` has ever wired Makoto hooks
    into. Fail-open: an absent/unreadable/malformed manifest reads as an empty set (no path is
    ever wrongly treated as manifest-wired)."""
    try:
        p = _state_dir() / "configchange_manifest.json"
        if not p.exists():
            return set()
        return set(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _load_snapshot(config_path: str) -> Optional[dict]:
    """The last-recorded observation for `config_path` (`{"had_hooks": bool}`), or None if this
    is the first time this exact path has ever been evaluated. Fail-open: any read/parse fault
    reads as "no prior observation" (never fabricates a had_hooks=True history)."""
    try:
        p = _state_dir() / "configchange_snapshots.json"
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get(config_path)
    except Exception:
        return None


def _save_snapshot(config_path: str, had_hooks: bool) -> None:
    """Record the CURRENT observation for `config_path`, so a FUTURE evaluation of this same
    path can detect a had-hooks-then-lost-them transition. Fail-open: a write fault must never
    break the hook."""
    try:
        state_dir = _state_dir()
        p = state_dir / "configchange_snapshots.json"
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        data[config_path] = {"had_hooks": had_hooks}
        state_dir.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def _should_block(verdict) -> tuple:
    """(should_block, reason) for a FIRING verdict (caller only invokes this when
    `verdict.fires` is already True). Reads the manifest + PRIOR snapshot (before any update),
    so this call's own result never depends on state it is about to write.

    should_block iff EITHER:
      - `verdict.config_path` (resolved) is in the installer's own wired-manifest -- Makoto's
        own install recorded this exact path as genuinely wired, so a stripped evaluation now
        IS a real strip, not an ambiguous never-wired case; OR
      - a PRIOR evaluation of this exact path observed hooks present (`had_hooks=True`) -- a
        real had->lost transition, observed twice, not a guess from a single snapshot.

    A path with NEITHER never blocks, regardless of how many times it evaluates as stripped --
    the whole FP-safety property this tier depends on."""
    try:
        resolved = str(Path(verdict.config_path).resolve()) if verdict.config_path else ""
    except Exception:
        resolved = verdict.config_path or ""
    if resolved and resolved in _manifest_paths():
        return True, (f"{verdict.reason} -- this settings path was recorded by makoto's own "
                      f"installer as genuinely wired, so this is a real strip, not an "
                      f"ambiguous never-wired case")
    prior = _load_snapshot(resolved) if resolved else None
    if prior is not None and prior.get("had_hooks") is True:
        return True, (f"{verdict.reason} -- a prior evaluation of this exact settings path "
                      f"observed makoto's hooks present; this is a genuine had-then-lost "
                      f"transition, not a guess from a single snapshot")
    return False, ""


def main() -> int:
    """Orchestrator, fail-open at every step: a malformed payload, an unreadable settings file,
    or any unexpected fault all resolve to "say nothing, do nothing, exit 0". Two tiers on a
    firing verdict (see module docstring): BLOCK on an evidenced manifest-hit or had->lost
    transition; otherwise ADVISORY (log + audit row, never blocks)."""
    try:
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw)
        except Exception:
            print("makoto.configchange: stdin was not valid JSON; loud-allow",
                  file=sys.stderr)
            return 0
        if not isinstance(payload, dict):
            print(f"makoto.configchange: payload was {type(payload).__name__}, "
                  f"not a JSON object; loud-allow", file=sys.stderr)
            return 0

        fs_read = _make_fs_read(payload)
        verdict = configchange_verdict(payload, fs_read=fs_read)

        try:
            resolved = str(Path(verdict.config_path).resolve()) if verdict.config_path else ""
        except Exception:
            resolved = verdict.config_path or ""

        if verdict.fires:
            block, reason = _should_block(verdict)
            if block:
                print(json.dumps({"decision": "block", "reason": reason}))
                _record_block_fire(payload, verdict, reason)
            else:
                _record_advisory_fire(payload, verdict)

        # Update the snapshot AFTER computing the block decision (never before -- the decision
        # must read the PRIOR state, not the one it is about to write), on every evaluation where
        # the content was actually readable, regardless of whether it fired this time -- this is
        # what lets a FUTURE evaluation detect a transition.
        if verdict.applicable and verdict.evaluated and resolved:
            _save_snapshot(resolved, had_hooks=not verdict.stripped)

        return 0
    except Exception as exc:
        # Never crash the hook to a non-zero exit, and never stay silent about a genuine fault —
        # same never-crash contract every other adapter in this codebase honors.
        print(f"makoto.configchange: unexpected exception, loud-allow: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
