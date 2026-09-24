"""The ConfigChange feature: the pure strip-detection predicate plus the hook adapter that
`.claude/settings.json`'s `ConfigChange` hook entry invokes via
`python3 -m makoto.configchange`.

Two tiers on a firing verdict:
  1. ADVISORY (unconditional): a verdict firing on a path never recorded as wired or
     previously-clean always logs a stderr line and a best-effort audit-row append, and never
     blocks. This is the ambiguous "never wired vs. just stripped" case `configchange_verdict`
     itself cannot resolve.
  2. BLOCKING (FP-safety-scoped): fires only when the strip is a genuine, evidenced transition
     -- either (a) `config_path` is in the installer's own wired-manifest
     (`<state_dir>/configchange_manifest.json`, written by `install.cmd_install`), or (b) a
     prior evaluation of this exact `config_path` observed makoto's hooks present
     (`<state_dir>/configchange_snapshots.json`). A path with neither can never block, no
     matter how many times it evaluates as stripped -- a project that never had makoto's hooks
     must never be blocked from editing its own settings. On block:
     `{"decision": "block", "reason": ...}` on stdout, exit 0 (Claude Code only processes hook
     JSON on exit 0). Never fires for `policy_settings`, which `_APPLICABLE_SOURCES` already
     excludes.
"""
from __future__ import annotations
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable, Optional

from makoto.checks.otherPoint import _missing_makoto_events
from makoto.state.audit import AuditRow, append_row
from makoto.state.store import _state_dir


# The pure predicate
#
# Makoto's Stop-time `gate.self_wired` (`checks/otherPoint.py`) can only ever see a PARTIAL
# strip of its own PreToolUse/PostToolUse/Stop hook entries in `.claude/settings.json` -- a
# single edit that removes all three simultaneously also removes the Stop entry that would have
# reported the loss, so that check has zero coverage against a full-strip attack. Claude Code's
# `ConfigChange` hook event observes the file-level edit itself, independent of Makoto's dispatch
# chain, so a full simultaneous strip is exactly what it fires for.
#
# This module imports `_missing_makoto_events` directly from `selfWiredCheck` rather than
# duplicating that predicate a third time. The gate-module layering firewall
# (`tests/test_import_direction.py`) restricts what a *gate* module may import, not what a
# non-gate module may import from a gate module.

# The two `config_source` values that can carry Makoto's hook wiring at all. `user_settings`
# (global, outside this repo), `policy_settings` (managed/enterprise, not where a repo-local hook
# is installed), and `skills` are structurally incapable of carrying `.claude/settings.json`'s or
# `.claude/settings.local.json`'s `hooks` object, so a change to one of them is never applicable
# regardless of content.
_APPLICABLE_SOURCES = ("project_settings", "local_settings")


@dataclass(frozen=True)
class ConfigChangeVerdict:
    """The result of evaluating one ConfigChange event against Makoto's hook wiring.

    No `fire_level`/advisory-vs-blocking field: `fires` is the one boolean fact this predicate
    asserts, and the adapter below maps it to an enforcement tier.
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
    """Evaluate a `ConfigChange`-shaped `event` (dict-like or attribute-like) against Makoto's
    own hook wiring.

    The settings content comes from either `settings_json` (already parsed) or `fs_read`
    (a `path -> Optional[str]` reader called with `config_path`). If both are omitted, or the
    content can't be read/parsed as a JSON object, the verdict fails open (`evaluated=False`,
    `fires=False`): an indeterminate read is not evidence of a strip.

    Not applicable for any `config_source` other than `project_settings` or `local_settings` --
    the only two sources capable of carrying the `hooks` object.

    Cannot distinguish "never wired" from "just stripped": a settings file that never had
    Makoto's hooks wired produces the identical all-three-missing signal as a full strip would.
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

    # `_missing_makoto_events` normalizes a missing/non-dict "hooks" to {} itself.
    missing = tuple(_missing_makoto_events(data.get("hooks")))
    stripped = bool(missing)
    reason = (f"missing makoto-dispatching entries for: {', '.join(missing)}" if stripped
              else "all of PreToolUse/PostToolUse/Stop retain a makoto-dispatching entry")
    return ConfigChangeVerdict(
        config_source=config_source, config_path=config_path,
        applicable=True, evaluated=True, stripped=stripped, missing_events=missing,
        fires=stripped, reason=reason,
    )


# The hook adapter

def _make_fs_read(payload: dict):
    """Build a `path -> Optional[str]` reader for `configchange_verdict`'s `fs_read` param.

    Absolute paths are opened directly; relative paths are joined against the payload's `cwd`
    (or `os.getcwd()` if absent). Never raises: any failure is treated as "content unavailable",
    which `configchange_verdict` already fails open on.
    """
    cwd = payload.get("cwd") or os.getcwd()

    def fs_read(path: str) -> Optional[str]:
        try:
            full = path if os.path.isabs(path) else os.path.join(cwd, path)
            if os.path.isfile(full):
                with open(full, encoding="utf-8", errors="replace") as fh:
                    return fh.read()
        except Exception:
            pass
        return None

    return fs_read


def _record_fire(payload: dict, verdict, *, pattern_id: str, level: str, message: str) -> None:
    """Shared AuditRow-construction shape for both the advisory and blocking tiers.
    `exit_code` is derived here from `level` (error -> exit 2) rather than passed in by each
    caller, so the two tiers can't independently drift out of sync."""
    try:
        state_dir = _state_dir()
        finding = {
            "pattern_id": pattern_id,
            "file": verdict.config_path,
            "line": 0,
            "level": level,
            "message": message,
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
            pattern_fires=[pattern_id],
            exit_code=2 if finding["level"] == "error" else 0,
            retry_hint_emitted=bool(finding["retry_hint"]),
            findings=[finding],
            tool_name="",  # ConfigChange is not tool-scoped
        )
        append_row(state_dir, row)
    except Exception:
        pass  # observability must never break the hook


def _record_advisory_fire(payload: dict, verdict) -> None:
    """Stderr note plus a best-effort AuditRow append. An observability failure must never
    break the hook."""
    print(f"makoto.configchange: ADVISORY {verdict.reason}", file=sys.stderr)
    _record_fire(payload, verdict, pattern_id="gate.configchange_advisory",
                 level="advisory", message=verdict.reason)


def _record_block_fire(payload: dict, verdict, reason: str) -> None:
    """Same shape as `_record_advisory_fire`, level="error", with a distinct pattern_id so
    audit-mining can tell the two tiers apart."""
    _record_fire(payload, verdict, pattern_id="gate.configchange_transition",
                 level="error", message=reason)


# Blocking tier: manifest + transition detection

def _resolved_config_path(config_path: str) -> str:
    """Resolved, absolute, symlink-free form of `config_path`, so the manifest (written in this
    same form by `install._record_configchange_manifest`) and the snapshot store agree on one
    key per file. Fail-soft: any resolution fault falls back to the path verbatim."""
    try:
        return str(Path(config_path).resolve()) if config_path else ""
    except Exception:
        return config_path or ""


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
    """(should_block, reason) for a firing verdict. Reads the manifest and the prior snapshot
    (before any update), so the result never depends on state it is about to write.

    should_block iff either the resolved `config_path` is in the installer's wired-manifest
    (a real strip, not an ambiguous never-wired case), or a prior evaluation of this exact path
    observed hooks present (a real had->lost transition, not a guess from one snapshot).

    A path with neither never blocks, regardless of how many times it evaluates as stripped."""
    resolved = _resolved_config_path(verdict.config_path)
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

        if verdict.fires:
            block, reason = _should_block(verdict)
            if block:
                print(json.dumps({"decision": "block", "reason": reason}))
                _record_block_fire(payload, verdict, reason)
            else:
                _record_advisory_fire(payload, verdict)

        # Update the snapshot after computing the block decision, not before -- the decision
        # must read the prior state, not the one it is about to write.
        if verdict.applicable and verdict.evaluated:
            resolved = _resolved_config_path(verdict.config_path)
            if resolved:
                _save_snapshot(resolved, had_hooks=not verdict.stripped)

        return 0
    except Exception as exc:
        # Never crash the hook to a non-zero exit, and never stay silent about a genuine fault.
        print(f"makoto.configchange: unexpected exception, loud-allow: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
