"""ConfigChange hook adapter.

It accepts only a complete, readable ConfigChange envelope. A detected strip is advisory unless
the installer manifest or a prior snapshot proves that Makoto had wired that exact path; those
evidenced transitions block. The pure verdict lives in
``makoto.verdict.configchange_verdict`` and the end-to-end contract is tested in
``tests/test_dispatch_configchange.py`` and ``tests/test_dispatch_configchange_blocking.py``.
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from makoto.record.audit import AuditRow, append_row
from makoto.verdict.configchange_verdict import configchange_verdict
from makoto.record.state import _state_dir


def _make_fs_read(payload: dict):
    """Build a `path -> Optional[str]` reader for `configchange_verdict`'s `fs_read` param.

    Absolute paths are opened directly; relative paths are joined against the payload's `cwd`
    (or `os.getcwd()` if absent) — the same cwd-relative convention `_dispatch.py`'s Stop-check
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
    """Loud stderr note (mirrors `_dispatch._dispatch_fact`'s style) + a best-effort AuditRow
    append. Wrapped so an observability failure can never break the hook — same fail-open
    philosophy as `_dispatch._record_exemption_sink`."""
    print(f"makoto._dispatch_configchange: ADVISORY {verdict.reason}", file=sys.stderr)
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
    """Orchestrate a complete ConfigChange envelope. Input that cannot be evaluated fails closed
    with exit 2; a readable, complete envelope still has the two verdict tiers below. Two tiers on a
    firing verdict (see module docstring): BLOCK on an evidenced manifest-hit or had->lost
    transition; otherwise ADVISORY (log + audit row, never blocks)."""
    try:
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw)
        except Exception:
            reason = "stdin was empty" if not raw.strip() else "stdin was not valid JSON"
            print(f"makoto._dispatch_configchange: {reason}; NOT_EVALUABLE",
                  file=sys.stderr)
            return 2
        if not isinstance(payload, dict):
            print(f"makoto._dispatch_configchange: payload was {type(payload).__name__}, "
                  f"not a JSON object; NOT_EVALUABLE", file=sys.stderr)
            return 2
        if not payload:
            print("makoto._dispatch_configchange: payload was an empty JSON object; NOT_EVALUABLE",
                  file=sys.stderr)
            return 2
        if payload.get("hook_event_name") != "ConfigChange":
            print("makoto._dispatch_configchange: hook_event_name must be 'ConfigChange'; "
                  "NOT_EVALUABLE", file=sys.stderr)
            return 2
        config_path = payload.get("config_path", payload.get("file_path"))
        source = payload.get("config_source", payload.get("source"))
        if not isinstance(config_path, str) or not config_path.strip():
            print("makoto._dispatch_configchange: config_path/file_path is required; "
                  "NOT_EVALUABLE", file=sys.stderr)
            return 2
        if not isinstance(source, str) or not source.strip():
            print("makoto._dispatch_configchange: config_source/source is required; "
                  "NOT_EVALUABLE", file=sys.stderr)
            return 2

        fs_read = _make_fs_read(payload)
        config_text = fs_read(config_path)
        if config_text is None:
            print("makoto._dispatch_configchange: configuration content is unavailable; "
                  "NOT_EVALUABLE", file=sys.stderr)
            return 2
        try:
            if not isinstance(json.loads(config_text), dict):
                raise ValueError("configuration JSON was not an object")
        except Exception:
            print("makoto._dispatch_configchange: configuration content is not a JSON object; "
                  "NOT_EVALUABLE", file=sys.stderr)
            return 2
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
        print(f"makoto._dispatch_configchange: unexpected exception, loud-allow: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
