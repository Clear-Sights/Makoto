"""install/uninstall lifecycle + status reporting.

Hook entries in ~/.claude/settings.json are tagged with _makoto_managed=True
so unwire can find and remove them without touching user-authored entries.

Env-aware behavior (1.0.4):
- MAKOTO_DISABLE_PATTERNS=id1,id2  -> dispatcher skips listed patterns
  status reports the current value under "patterns_disabled".

cmd_install handles BOTH state-dir setup and settings.json wiring — useful
when /plugin install is unavailable. Plugin-capable environments can just
run `/plugin install <path>`; lazy init in dispatch covers state-dir
bootstrap automatically, so `cmd_install` is the only makoto command they
ever need to run (and only once, for the settings.json fallback path).

The 1.0.3 collapse pass removed cmd_init (vestigial post-5.4 — lazy init
covers it) and the audit subcommand routing.
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path
from makoto.registry import load_checks, load_precheck_catalog
# Hoisted 2026-07-09 to makoto.substrate.wiring (shared with checks/selfWiredCheck.py, which the
# gate-side layering firewall bars from importing this lifecycle module directly).
from makoto.substrate.wiring import (
    MAKOTO_CLAUDE_FLAG as _MAKOTO_CLAUDE_FLAG,
    entry_dispatches_to_makoto as _entry_dispatches_to_makoto,
    entry_owned_by_makoto as _entry_owned_by_makoto,
    event_wired,
    read_plugin_manifest_hooks,
)


def _validate_predicate_modules() -> None:
    """install-time gate: every active pattern's predicate_module imports + has callable + has >=1 keyword.

    Fails loud (exit 1) on import error, missing predicate, or empty keywords.
    Skips rows with empty predicate_module (transitional state).

    SPEC-C item 2 (Pre-tier cutover): sources the live catalog via load_precheck_catalog()'s DEFAULT
    (loader-backed) path, not an explicit read of data/patterns.toml -- that file is no longer
    the runtime source of truth, so gating this validation on its presence would make the gate
    silently vacuous the moment the file is removed (item 2 step 3).
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

    Returns whether the shim is on disk afterwards. A missing source silently produced an
    install that reported success with no dispatch.sh — every wired hook then pointing at a
    file that does not exist, i.e. makoto reporting itself installed while unable to fire."""
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
    one of makoto's own installed forms — see `wiring.entry_dispatches_to_makoto`) is absorbed
    into the single managed entry, never duplicated. Absorbing on the SAME predicate uninstall
    removes with (`entry_owned_by_makoto`, an alias of the same function) keeps install and
    uninstall inverses of each other — and its anchored invocation regex keeps a user's OWN
    makoto-CLI hook (`python3 -m makoto.status`) out of both."""
    data = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    hooks = data.setdefault("hooks", {})
    dispatch_path = Path.home() / ".claude" / "makoto_state" / "dispatch.sh"
    for event in ("PreToolUse", "PostToolUse", "Stop"):
        entries = hooks.setdefault(event, [])
        entries[:] = [h for h in entries if not _entry_owned_by_makoto(h)]
        entries.append({
            _MAKOTO_CLAUDE_FLAG: True,
            "matcher": "*",
            "hooks": [{"type": "command", "command": str(dispatch_path)}],
        })
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _unwire_claude_hooks(settings_path: Path):
    """Remove every hook entry makoto OWNS; preserve user entries. Returns `(entries_removed,
    commands_removed)` — an ENTRY count (what was deleted from the file) alongside the inner
    command strings (what to show the user), kept separate because one entry may carry several
    commands and conflating the two counts is silently wrong in both directions.

    Keyed on `entry_owned_by_makoto` (an alias of `entry_dispatches_to_makoto` — see
    `wiring.py`: the same predicate answers both "does this reach makoto" and "may makoto
    delete this"). It used to key on the `_makoto_managed` flag ALONE, which broke twice over:

    1. The flag decays (#20). Claude Code re-serializes settings.json from a schema-parsed
       representation that drops unknown keys — including `_makoto_managed` — while KEEPING the
       hook entries. One `claude plugin marketplace add` is enough. After that the filter matched
       nothing, so uninstall removed zero hook entries, forever, while still reporting success.
    2. Install and uninstall were not inverses. `_wire_claude_hooks` absorbs any functionally
       dispatching entry (flagged or hand-wired), so `install` would swallow a hand-wired
       `python -m makoto.dispatch` entry, but `uninstall` left that same entry firing.

    Reporting used functional truth while removal trusted the flag — the asymmetry
    `_hooks_wired`'s own docstring warns about, applied to the other half of the contract.
    A malformed settings.json fails LOUD (JSONDecodeError propagates) rather than silently:
    this is the command whose whole job is un-wiring, and a settings file broken enough to
    reject `json.loads` needs the user's attention, not a report that nothing was removed."""
    if not settings_path.exists():
        return 0, []
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks = data.get("hooks", {})
    entries_removed = 0
    commands_removed: list = []
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


def _conventions_block_body() -> str:
    """the 3-line law installed into CLAUDE.md: the monotonicity invariant, the makoto-allow
    convention, a pointer to the full conventions. The flagged-shapes catalog + examples are
    deliberately NOT installed — each check delivers its convention just-in-time when it fires
    (dispatch._jit_hint), so guidance lands at the moment it binds and costs zero adherence
    budget when it doesn't."""
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

    Installs only the 3-line law (_conventions_block_body); the full shapes catalog stays in
    docs/MAKOTO-CONVENTIONS.md and is delivered just-in-time by the hook at fire time.
    Only the text BETWEEN the managed markers is ever touched — user content is preserved.
    """
    block = f"{_CONV_START}\n{_conventions_block_body()}\n{_CONV_END}"
    existing = claude_md_path.read_text(encoding="utf-8") if claude_md_path.exists() else ""
    stripped = re.sub(re.escape(_CONV_START) + r".*?" + re.escape(_CONV_END), "",
                      existing, flags=re.S).rstrip()
    new = (stripped + "\n\n" + block + "\n") if stripped else (block + "\n")
    claude_md_path.parent.mkdir(parents=True, exist_ok=True)
    claude_md_path.write_text(new, encoding="utf-8")


def _uninstall_claude_conventions(claude_md_path: Path) -> bool:
    """Remove the makoto-managed conventions block; preserve all user content.

    Returns whether a managed block was actually PRESENT and stripped — an absent CLAUDE.md and a
    CLAUDE.md that never carried the block both removed nothing, and reporting those as
    `conventions_removed: true` describes work that did not happen."""
    if not claude_md_path.exists():
        return False
    existing = claude_md_path.read_text(encoding="utf-8")
    stripped = re.sub(re.escape(_CONV_START) + r".*?" + re.escape(_CONV_END), "",
                      existing, flags=re.S).rstrip()
    if stripped == existing.rstrip():
        return False                                  # no managed block was there to remove
    claude_md_path.write_text((stripped + "\n") if stripped else "", encoding="utf-8")
    return True


def _record_configchange_manifest(settings_path: Path, *, state_dir: Path) -> None:
    """D5 (docs/DEFERRED.md, owner-authorized blocking flip, 2026-07-08): record that the
    installer wired Makoto's hooks into `settings_path`, so `configchange.py`'s
    blocking tier can treat a LATER full-strip of this exact path as a genuine strip (not the
    ambiguous "never wired" case `configchange_verdict` cannot distinguish on its own) -- ground
    truth from the one place that actually knows what it wired, complementary to (not a
    replacement for) the transition-snapshot half of the same detector. Fail-open: a write
    failure here must never break install."""
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

    Every reported field is measured after the fact, for the same reason `cmd_uninstall`'s is:
    `makoto_db_initialized` and `settings_wired` were printed as literal `True` regardless of
    outcome, so an install that wired nothing — or wired hooks pointing at a dispatch.sh that
    was never copied — still reported success. `cmd_status` already derived exactly these values
    honestly; install asserted them."""
    _validate_predicate_modules()
    state_dir = Path.home() / ".claude" / "makoto_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    shim_installed = _install_bash_scripts(state_dir)
    from makoto.state import store as db
    citations_path = Path(__file__).parent / "docs" / "CITATIONS.md"
    db.init_db(state_dir, citations_path)
    settings = Path.home() / ".claude" / "settings.json"
    if not settings.exists():
        settings.write_text("{}\n", encoding="utf-8")
    _wire_claude_hooks(settings)
    _record_configchange_manifest(settings, state_dir=state_dir)
    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    _install_claude_conventions(claude_md)
    # post-conditions, re-read from disk
    try:
        settings_wired = _hooks_wired(json.loads(settings.read_text(encoding="utf-8")))
    except Exception:
        settings_wired = False
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
    plugin hooks still fire on every event. Claude Code's plugin-enablement store is not
    something makoto reads, so this reports what it can observe ($CLAUDE_PLUGIN_ROOT and the
    manifest there) and says plainly when it cannot observe the rest. An unknown reported as
    unknown is the point: the previous output implied a completeness it never checked."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT") or ""
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
    with — so the two commands can no longer contradict each other (they did, #20: uninstall
    printed `unwired: true` while status, run immediately after, printed `hooks_wired: true`).

    This output used to be the literal `{"unwired": True, "conventions_removed": True,
    "state_dir_kept": True}` — printed unconditionally, measuring nothing, with the removal
    itself silently no-opping whenever the `_makoto_managed` flags had decayed. An integrity
    tool whose own success report is a claim rather than a measurement fails the standard it
    enforces."""
    settings = Path.home() / ".claude" / "settings.json"
    state_dir = Path.home() / ".claude" / "makoto_state"
    entries_removed, commands_removed = _unwire_claude_hooks(settings)
    conventions_removed = _uninstall_claude_conventions(Path.home() / ".claude" / "CLAUDE.md")
    # post-condition, re-read from disk: what the file SAYS now, not what we believe we wrote.
    still_wired = False
    if settings.exists():
        try:
            still_wired = _hooks_wired(json.loads(settings.read_text(encoding="utf-8")))
        except Exception:
            still_wired = True          # unreadable -> cannot claim unwired
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

    Recognizes BOTH forms: the managed-flag entry cmd_install writes (`_makoto_managed`), AND a
    flag-less entry whose command points at makoto's dispatch (a hand-wired / shim install:
    `…/makoto_state/dispatch.sh`, `python -m makoto.dispatch`). The flag exists for idempotent
    UNINSTALL; reporting WIRING must use the functional truth — does a hook reach makoto — or status
    lies (hooks_wired=false) on a device where makoto is in fact firing."""
    hooks = data.get("hooks", {})
    return any(_entry_dispatches_to_makoto(h)
               for evt in ("PreToolUse", "PostToolUse", "Stop") for h in hooks.get(evt, []))


def cmd_status() -> int:
    """report patterns_count, hooks_wired, state_dir."""
    state_dir = Path.home() / ".claude" / "makoto_state"
    # SPEC-C item 2 (Pre-tier cutover): the live catalog count, not a literal patterns.toml read.
    patterns_count = len(load_precheck_catalog())
    settings = Path.home() / ".claude" / "settings.json"
    hooks_wired = False
    if settings.exists():
        data = json.loads(settings.read_text(encoding="utf-8"))
        hooks_wired = _hooks_wired(data)
    # MAKOTO_DISABLE_PATTERNS is honored by the Pre-tier predicate loop ONLY
    # (`dispatch._run_predicates`); the Stop gates are governed by their own `_gates_enabled()`
    # switch and never consult this list. Echoing the raw request as `patterns_disabled`
    # therefore told a user who muted a noisy GATE that it was disabled while it went on
    # blocking them — the report asserting an effect the decision path never applies, the same
    # defect as an uninstall that reports `unwired` without measuring. Requested vs effective
    # are separate fields, and an id that cannot fully take effect is named rather than
    # silently implied. An id present on BOTH edges (gate.contract_order, the one dual-edge
    # check) keeps its Stop half firing regardless of the env var, so it is ineffective too.
    requested = [p.strip() for p in os.environ.get("MAKOTO_DISABLE_PATTERNS", "").split(",") if p.strip()]
    stop_ids = {c.id for c in load_checks(edge="Stop")}
    muteable = {p.id for p in load_precheck_catalog()} - stop_ids
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
