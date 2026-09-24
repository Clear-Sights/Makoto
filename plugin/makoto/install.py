"""install/uninstall lifecycle + status reporting.

Hook entries in ~/.claude/settings.json are tagged with _makoto_managed=True
so unwire can find and remove them without touching user-authored entries.

MAKOTO_DISABLE_PATTERNS=id1,id2 makes the dispatcher skip listed patterns; status
reports the current value under "patterns_disabled".

cmd_install handles BOTH state-dir setup and settings.json wiring, for when
/plugin install is unavailable; lazy init in dispatch covers state-dir bootstrap
automatically, so cmd_install is the only makoto command needed otherwise.
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path
from makoto.registry import load_checks, load_precheck_catalog
# Shared with checks/otherPoint.py, which the gate-side layering firewall bars from importing
# this lifecycle module directly.
from makoto.substrate.wiring import (
    MAKOTO_CLAUDE_FLAG as _MAKOTO_CLAUDE_FLAG,
    entry_dispatches_to_makoto as _entry_dispatches_to_makoto,
    entry_owned_by_makoto as _entry_owned_by_makoto,
    event_wired,
    read_plugin_manifest_hooks,
)


# The three settings.json events makoto wires and reports on. ONE tuple so the writer
# (`_wire_claude_hooks`) and the reporter (`_hooks_wired`) can't drift apart on which events count.
_WIRED_EVENTS = ("PreToolUse", "PostToolUse", "Stop")


def _state_dir_path() -> Path:
    """`~/.claude/makoto_state`. Resolved per call, never cached, so the writer and the reporter
    always agree on the path."""
    return Path.home() / ".claude" / "makoto_state"


def _settings_path() -> Path:
    """`~/.claude/settings.json` — the file makoto wires its hook entries into."""
    return Path.home() / ".claude" / "settings.json"


def _claude_md_path() -> Path:
    """`~/.claude/CLAUDE.md` — the file the managed conventions block lives in."""
    return Path.home() / ".claude" / "CLAUDE.md"


def _validate_predicate_modules() -> None:
    """install-time gate: every active pattern's predicate_module imports + has callable + has >=1 keyword.

    Fails loud (exit 1) on import error, missing predicate, or empty keywords. Skips rows with
    empty predicate_module (transitional state). Sources the live catalog via
    load_precheck_catalog(), never an explicit read of data/patterns.toml -- that file is not the
    runtime source of truth, so gating on its presence would make this silently vacuous if removed.
    """
    import importlib
    for p in load_precheck_catalog():
        if not p.predicate_module:
            continue
        try:
            mod = importlib.import_module(p.predicate_module)
        except ImportError as e:
            print(f"makoto install: error — pattern {p.id} predicate_module "
                  f"'{p.predicate_module}' failed to import: {e}", file=sys.stderr)
            sys.exit(1)
        if not callable(getattr(mod, "predicate", None)):
            print(f"makoto install: error — pattern {p.id} predicate_module "
                  f"'{p.predicate_module}' has no callable 'predicate' function.",
                  file=sys.stderr)
            sys.exit(1)
        if not p.keywords:
            print(f"makoto install: error — pattern {p.id} has empty keywords; "
                  f"the prefilter requires >=1 keyword per active pattern.",
                  file=sys.stderr)
            sys.exit(1)


def _install_bash_scripts(state_dir: Path) -> bool:
    """copy _dispatch_shim.sh into <state_dir>/dispatch.sh for settings.json hook wiring.

    Returns whether the shim is on disk afterwards, so a missing source can't silently report
    a successful install whose wired hooks point at a file that doesn't exist."""
    state_dir.mkdir(parents=True, exist_ok=True)
    shim_src = Path(__file__).parent / "_dispatch_shim.sh"
    if not shim_src.exists():
        return False
    shim_dst = state_dir / "dispatch.sh"
    shim_dst.write_text(shim_src.read_text(encoding="utf-8"), encoding="utf-8")
    shim_dst.chmod(0o755)
    return shim_dst.exists()


def _wire_claude_hooks(settings_path: Path) -> None:
    """add Makoto-managed PreToolUse + Stop hook entries pointing at dispatch.sh; idempotent.

    Idempotency is FUNCTIONAL: any entry already dispatching to makoto (managed, hand-wired, or
    one of makoto's own installed forms) is absorbed into the single managed entry, never
    duplicated. Absorbing on the same predicate uninstall removes with keeps install/uninstall
    inverses of each other, and keeps a user's own makoto-CLI hook out of both."""
    data = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    hooks = data.setdefault("hooks", {})
    dispatch_path = _state_dir_path() / "dispatch.sh"
    # A settings.json hook gets no CLAUDE_PLUGIN_ROOT, and the shim fails open without it.
    root = Path(__file__).resolve().parent.parent.as_posix()
    for event in _WIRED_EVENTS:
        entries = hooks.setdefault(event, [])
        entries[:] = [h for h in entries if not _entry_owned_by_makoto(h)]
        entries.append({
            _MAKOTO_CLAUDE_FLAG: True,
            "matcher": "*",
            "hooks": [{"type": "command", "command": f'CLAUDE_PLUGIN_ROOT="{root}" sh "{dispatch_path.as_posix()}"'}],
        })
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _unwire_claude_hooks(settings_path: Path) -> tuple[int, list[str]]:
    """Remove every hook entry makoto OWNS; preserve user entries. Returns `(entries_removed,
    commands_removed)` — an entry count alongside the inner command strings, kept separate
    because one entry may carry several commands.

    Keyed on `entry_owned_by_makoto` (an alias of `entry_dispatches_to_makoto`), not on the
    `_makoto_managed` flag alone: the flag can decay (Claude Code's settings.json
    re-serialization drops unknown keys while keeping hook entries) while the entry keeps
    firing, and install absorbs any functionally-dispatching entry regardless of the flag, so
    uninstall must key on the same predicate to stay its inverse.

    A malformed settings.json fails LOUD (JSONDecodeError propagates): this command's whole job
    is un-wiring, so a file broken enough to reject `json.loads` needs the user's attention, not
    a report that nothing was removed."""
    if not settings_path.exists():
        return 0, []
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks = data.get("hooks", {})
    entries_removed = 0
    commands_removed: list[str] = []
    for event in list(hooks.keys()):
        kept = []
        for h in hooks[event]:
            if _entry_owned_by_makoto(h):
                entries_removed += 1
                commands_removed.extend(str(i.get("command", "")) for i in (h.get("hooks") or [])
                                        if isinstance(i, dict))
            else:
                kept.append(h)
        hooks[event] = kept
        if not hooks[event]:
            del hooks[event]
    if not hooks and "hooks" in data:
        del data["hooks"]
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return entries_removed, commands_removed


_CONV_START = "<!-- makoto-managed:conventions:start -->"
_CONV_END = "<!-- makoto-managed:conventions:end -->"

# The managed block, start through end marker. Shared by both halves so the writer and the
# remover can't drift apart on what text counts as the block.
_CONV_BLOCK_RX = re.compile(re.escape(_CONV_START) + r".*?" + re.escape(_CONV_END), re.S)


def _strip_conventions_block(text: str) -> str:
    """`text` with any makoto-managed conventions block removed, right-stripped."""
    return _CONV_BLOCK_RX.sub("", text).rstrip()


def _conventions_block_body() -> str:
    """the 3-line law installed into CLAUDE.md: the monotonicity invariant, the makoto-allow
    convention, a pointer to the full conventions. The flagged-shapes catalog is deliberately
    NOT installed here -- each check delivers its own just-in-time when it fires."""
    conv = Path(__file__).resolve().parent / "docs" / "MAKOTO-CONVENTIONS.md"
    return (
        "**Makoto monotonicity invariant — falsifiability-preservation:** a word's meaning may "
        "only be preserved or deepened, never made less checkable; a bypassable test was never a test.\n"
        "**If makoto flags a legitimate instance**, annotate it `makoto-allow: <reason>` on or near "
        "the line (any comment style) — an on-the-record, auditable rationale, never a disguise.\n"
        f"Full conventions (each check also delivers its own just-in-time when it fires): {conv}"
    )


def _install_claude_conventions(claude_md_path: Path) -> None:
    """write/refresh the makoto-managed conventions block in CLAUDE.md, idempotently.

    Only the text BETWEEN the managed markers is ever touched — user content is preserved.
    """
    block = f"{_CONV_START}\n{_conventions_block_body()}\n{_CONV_END}"
    existing = claude_md_path.read_text(encoding="utf-8") if claude_md_path.exists() else ""
    stripped = _strip_conventions_block(existing)
    new = (stripped + "\n\n" + block + "\n") if stripped else (block + "\n")
    claude_md_path.parent.mkdir(parents=True, exist_ok=True)
    claude_md_path.write_text(new, encoding="utf-8")


def _uninstall_claude_conventions(claude_md_path: Path) -> bool:
    """Remove the makoto-managed conventions block; preserve all user content.

    Returns whether a managed block was actually PRESENT and stripped, so an absent CLAUDE.md
    or one that never carried the block is never reported as `conventions_removed: true`."""
    if not claude_md_path.exists():
        return False
    existing = claude_md_path.read_text(encoding="utf-8")
    stripped = _strip_conventions_block(existing)
    if stripped == existing.rstrip():
        return False                                  # no managed block was there to remove
    claude_md_path.write_text((stripped + "\n") if stripped else "", encoding="utf-8")
    return True


def _record_configchange_manifest(settings_path: Path, *, state_dir: Path) -> None:
    """Record that the installer wired Makoto's hooks into `settings_path`, so
    `configchange.py`'s blocking tier can treat a LATER full-strip of this exact path as a
    genuine strip rather than the ambiguous "never wired" case. Fail-open: a write failure here
    must never break install."""
    manifest_path = state_dir / "configchange_manifest.json"
    try:
        paths = set(json.loads(manifest_path.read_text(encoding="utf-8"))) if manifest_path.exists() else set()
    except Exception:
        paths = set()
    paths.add(str(settings_path.resolve()))
    try:
        manifest_path.write_text(json.dumps(sorted(paths), indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass  # observability must never break install


def cmd_install() -> int:
    """state-dir setup + ~/.claude/settings.json hook wiring. Idempotent.

    Every reported field is measured after the fact rather than asserted, so an install that
    wired nothing -- or wired hooks pointing at a dispatch.sh never copied -- can't still report
    success."""
    _validate_predicate_modules()
    state_dir = _state_dir_path()
    state_dir.mkdir(parents=True, exist_ok=True)
    shim_installed = _install_bash_scripts(state_dir)
    from makoto.state import store as db
    citations_path = Path(__file__).parent / "docs" / "CITATIONS.md"
    db.init_db(state_dir, citations_path)
    settings = _settings_path()
    if not settings.exists():
        settings.write_text("{}\n", encoding="utf-8")
    _wire_claude_hooks(settings)
    _record_configchange_manifest(settings, state_dir=state_dir)
    claude_md = _claude_md_path()
    _install_claude_conventions(claude_md)
    settings_wired = _hooks_wired_on_disk(settings, on_unreadable=False)
    try:
        conventions_written = _CONV_START in claude_md.read_text(encoding="utf-8")
    except Exception:
        conventions_written = False
    print(json.dumps({
        "state_dir": str(state_dir),
        "state_dir_present": state_dir.is_dir(),
        "dispatch_shim_installed": shim_installed,
        "makoto_db_initialized": (state_dir / "makoto.record.db").exists(),
        "settings_wired": settings_wired,
        "settings_path": str(settings),
        "conventions_written": conventions_written,
        "conventions_path": str(claude_md),
    }, indent=2))
    return 0


def _plugin_wiring_report() -> dict:
    """What can be MEASURED about the OTHER wiring source: the marketplace plugin's hooks.json.

    Unwiring settings.json does not disable an enabled `makoto@makoto` plugin — its manifest
    wires the same dispatch independently, so an uninstall can look clean in settings.json while
    plugin hooks still fire. Claude Code's plugin-enablement store is not something makoto reads,
    so this reports only what it can observe ($CLAUDE_PLUGIN_ROOT and the manifest there) and
    says plainly when it cannot observe the rest."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return {"plugin_hooks_declared": None,
                "note": "CLAUDE_PLUGIN_ROOT is unset here, so the marketplace plugin's wiring "
                        "could not be inspected. If `makoto@makoto` is installed as a plugin, "
                        "its hooks still fire regardless of this settings.json unwire — disable "
                        "it with Claude Code's plugin CLI."}
    def _read(path):
        try:
            return Path(path).read_text(encoding="utf-8")
        except Exception:
            return ""
    hooks = read_plugin_manifest_hooks(root, _read)
    declared = sorted(evt for evt in ("PreToolUse", "PostToolUse", "Stop", "SubagentStop",
                                      "SessionStart") if event_wired(hooks, evt))
    return {"plugin_hooks_declared": declared,
            "note": ("A plugin manifest at CLAUDE_PLUGIN_ROOT still declares these events; "
                     "unwiring settings.json does NOT disable them.") if declared else
                    "No makoto hooks declared by the plugin manifest at CLAUDE_PLUGIN_ROOT."}


def cmd_uninstall() -> int:
    """Remove every Claude Code hook entry that makoto owns; state dir kept.

    Every field printed is MEASURED. `unwired` is a post-condition: settings.json is RE-READ from
    disk after the write and put through `_hooks_wired`, the same predicate `cmd_status` reports
    with, so the two commands can never contradict each other."""
    settings = _settings_path()
    state_dir = _state_dir_path()
    entries_removed, commands_removed = _unwire_claude_hooks(settings)
    conventions_removed = _uninstall_claude_conventions(_claude_md_path())
    # Re-read from disk: no file -> nothing left to fire; unreadable -> can't claim unwired.
    still_wired = settings.exists() and _hooks_wired_on_disk(settings, on_unreadable=True)
    print(json.dumps({
        "hook_entries_removed": entries_removed,
        "hook_commands_removed": commands_removed,
        "unwired": not still_wired,
        "conventions_removed": conventions_removed,
        "state_dir_kept": state_dir.is_dir(),
        "settings_path": str(settings),
        **_plugin_wiring_report(),
    }, indent=2))
    return 0


def _hooks_wired(data: dict) -> bool:
    """True iff settings.json carries at least one hook entry that DISPATCHES to makoto.

    Recognizes both the managed-flag entry cmd_install writes and a flag-less hand-wired/shim
    entry whose command points at makoto's dispatch. Reporting WIRING must use functional truth
    — does a hook reach makoto — or status lies on a device where makoto is in fact firing."""
    hooks = data.get("hooks", {})
    return any(_entry_dispatches_to_makoto(h)
               for evt in _WIRED_EVENTS for h in hooks.get(evt, []))


def _hooks_wired_on_disk(settings_path: Path, *, on_unreadable: bool) -> bool:
    """`_hooks_wired` against what `settings_path` SAYS right now, re-read from disk rather than
    assumed from the write. `on_unreadable` is the answer when the file can't be read or parsed;
    install and uninstall deliberately differ (False vs True) since each must fail toward its
    own honest claim."""
    try:
        return _hooks_wired(json.loads(settings_path.read_text(encoding="utf-8")))
    except Exception:
        return on_unreadable


def cmd_status() -> int:
    """report patterns_count, hooks_wired, state_dir."""
    state_dir = _state_dir_path()
    # Loaded ONCE and reused for the mute-eligibility set below -- a second load would only
    # re-glob checks/ and re-import every candidate module to agree with the first.
    catalog = load_precheck_catalog()
    patterns_count = len(catalog)
    settings = _settings_path()
    hooks_wired = False
    if settings.exists():
        data = json.loads(settings.read_text(encoding="utf-8"))
        hooks_wired = _hooks_wired(data)
    # MAKOTO_DISABLE_PATTERNS is honored by the Pre-tier predicate loop ONLY; Stop gates are
    # governed by their own `_gates_enabled()` switch and never consult this list. So requested
    # vs. effective are reported as separate fields, rather than telling a user who muted a
    # noisy gate that it was disabled while it kept firing.
    requested = [p.strip() for p in os.environ.get("MAKOTO_DISABLE_PATTERNS", "").split(",") if p.strip()]
    stop_ids = {c.id for c in load_checks(edge="Stop")}
    muteable = {p.id for p in catalog} - stop_ids
    print(json.dumps({
        "patterns_count": patterns_count,
        "patterns_disabled": [p for p in requested if p in muteable],
        "patterns_disable_requested": requested,
        "patterns_disable_ineffective": [p for p in requested if p not in muteable],
        "hooks_wired": hooks_wired,
        "state_dir": str(state_dir),
        "state_dir_present": state_dir.is_dir(),
    }, indent=2))
    return 0
