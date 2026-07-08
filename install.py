"""install/uninstall lifecycle + status reporting.

Hook entries in ~/.claude/settings.json are tagged with _makoto_managed=True
so unwire can find and remove them without touching user-authored entries.

Env-aware behavior (1.0.4):
- MAKOTO_DISABLE_PATTERNS=id1,id2  -> dispatcher skips listed patterns
  status reports the current value under "patterns_disabled".

cmd_install handles BOTH state-dir setup and settings.json wiring — useful
when /plugin install is unavailable. Plugin-capable environments can just
run `/plugin install <path>`; lazy init in _dispatch covers state-dir
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
from makoto.schema import load_prechecks


_MAKOTO_CLAUDE_FLAG = "_makoto_managed"


def _validate_predicate_modules() -> None:
    """install-time gate: every active pattern's predicate_module imports + has callable + has >=1 keyword.

    Fails loud (exit 1) on import error, missing predicate, or empty keywords.
    Skips rows with empty predicate_module (transitional state).

    SPEC-C item 2 (Pre-tier cutover): sources the live catalog via load_prechecks()'s DEFAULT
    (loader-backed) path, not an explicit read of data/patterns.toml -- that file is no longer
    the runtime source of truth, so gating this validation on its presence would make the gate
    silently vacuous the moment the file is removed (item 2 step 3).
    """
    import importlib
    for p in load_prechecks():
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


def _install_bash_scripts(state_dir: Path) -> None:
    """copy _dispatch_shim.sh into <state_dir>/dispatch.sh for settings.json hook wiring."""
    state_dir.mkdir(parents=True, exist_ok=True)
    shim_src = Path(__file__).parent / "_dispatch_shim.sh"
    if shim_src.exists():
        shim_dst = state_dir / "dispatch.sh"
        shim_dst.write_text(shim_src.read_text(encoding="utf-8"), encoding="utf-8")
        shim_dst.chmod(0o755)


def _entry_dispatches_to_makoto(entry) -> bool:
    """the functional wiring truth for ONE hook entry: does it reach makoto's dispatch?

    True for the managed-flag entry cmd_install writes AND for a flag-less hand-wired /
    shim entry (`…/makoto_state/dispatch.sh`, `python -m makoto._dispatch`). Shared by
    wirer and status — keying either on the flag alone lies on a shim-wired device
    (status: hooks_wired=false while firing, fixed v1.2.1; install: a duplicate entry
    double-dispatching every event, the same bug on the write side)."""
    if not isinstance(entry, dict):
        return False
    if entry.get(_MAKOTO_CLAUDE_FLAG):
        return True
    return any(isinstance(inner, dict) and "makoto" in str(inner.get("command", "")).lower()
               for inner in entry.get("hooks", []))


def _wire_claude_hooks(settings_path: Path) -> None:
    """add Makoto-managed PreToolUse + Stop hook entries pointing at dispatch.sh; idempotent.

    Idempotency is FUNCTIONAL: any entry already dispatching to makoto (managed or
    hand-wired) is absorbed into the single managed entry, never duplicated."""
    data = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    hooks = data.setdefault("hooks", {})
    dispatch_path = Path.home() / ".claude" / "makoto_state" / "dispatch.sh"
    for event in ("PreToolUse", "PostToolUse", "Stop"):
        entries = hooks.setdefault(event, [])
        entries[:] = [h for h in entries if not _entry_dispatches_to_makoto(h)]
        entries.append({
            _MAKOTO_CLAUDE_FLAG: True,
            "matcher": "*",
            "hooks": [{"type": "command", "command": str(dispatch_path)}],
        })
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _unwire_claude_hooks(settings_path: Path) -> None:
    """remove all Makoto-managed hook entries; preserve user entries."""
    if not settings_path.exists():
        return
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks = data.get("hooks", {})
    for event in list(hooks.keys()):
        hooks[event] = [h for h in hooks[event] if not h.get(_MAKOTO_CLAUDE_FLAG)]
        if not hooks[event]:
            del hooks[event]
    if not hooks and "hooks" in data:
        del data["hooks"]
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


_CONV_START = "<!-- makoto-managed:conventions:start -->"
_CONV_END = "<!-- makoto-managed:conventions:end -->"


def _conventions_block_body() -> str:
    """the 3-line law installed into CLAUDE.md: the monotonicity invariant, the makoto-allow
    convention, a pointer to the full conventions. The flagged-shapes catalog + examples are
    deliberately NOT installed — each check delivers its convention just-in-time when it fires
    (_dispatch._jit_hint), so guidance lands at the moment it binds and costs zero adherence
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


def _uninstall_claude_conventions(claude_md_path: Path) -> None:
    """remove the makoto-managed conventions block; preserve all user content."""
    if not claude_md_path.exists():
        return
    existing = claude_md_path.read_text(encoding="utf-8")
    stripped = re.sub(re.escape(_CONV_START) + r".*?" + re.escape(_CONV_END), "",
                      existing, flags=re.S).rstrip()
    claude_md_path.write_text((stripped + "\n") if stripped else "", encoding="utf-8")


def _record_configchange_manifest(settings_path: Path, *, state_dir: Path) -> None:
    """D5 (docs/DEFERRED.md, owner-authorized blocking flip, 2026-07-08): record that the
    installer wired Makoto's hooks into `settings_path`, so `_dispatch_configchange.py`'s
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
    """state-dir setup + ~/.claude/settings.json hook wiring. Idempotent."""
    _validate_predicate_modules()
    state_dir = Path.home() / ".claude" / "makoto_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    _install_bash_scripts(state_dir)
    from makoto import db
    citations_path = Path(__file__).parent / "docs" / "CITATIONS.md"
    db.init_db(state_dir, citations_path)
    settings = Path.home() / ".claude" / "settings.json"
    if not settings.exists():
        settings.write_text("{}\n", encoding="utf-8")
    _wire_claude_hooks(settings)
    _record_configchange_manifest(settings, state_dir=state_dir)
    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    _install_claude_conventions(claude_md)
    print(json.dumps({
        "state_dir": str(state_dir),
        "makoto_db_initialized": True,
        "settings_wired": True,
        "settings_path": str(settings),
        "conventions_written": str(claude_md),
    }, indent=2))
    return 0


def cmd_uninstall() -> int:
    """remove all Makoto-managed Claude Code hook entries; state dir kept."""
    settings = Path.home() / ".claude" / "settings.json"
    _unwire_claude_hooks(settings)
    _uninstall_claude_conventions(Path.home() / ".claude" / "CLAUDE.md")
    print(json.dumps({"unwired": True, "conventions_removed": True, "state_dir_kept": True}, indent=2))
    return 0


def _hooks_wired(data: dict) -> bool:
    """True iff settings.json carries at least one hook entry that DISPATCHES to makoto.

    Recognizes BOTH forms: the managed-flag entry cmd_install writes (`_makoto_managed`), AND a
    flag-less entry whose command points at makoto's dispatch (a hand-wired / shim install:
    `…/makoto_state/dispatch.sh`, `python -m makoto._dispatch`). The flag exists for idempotent
    UNINSTALL; reporting WIRING must use the functional truth — does a hook reach makoto — or status
    lies (hooks_wired=false) on a device where makoto is in fact firing."""
    hooks = data.get("hooks", {})
    return any(_entry_dispatches_to_makoto(h)
               for evt in ("PreToolUse", "PostToolUse", "Stop") for h in hooks.get(evt, []))


def cmd_status() -> int:
    """report patterns_count, hooks_wired, state_dir."""
    state_dir = Path.home() / ".claude" / "makoto_state"
    # SPEC-C item 2 (Pre-tier cutover): the live catalog count, not a literal patterns.toml read.
    patterns_count = len(load_prechecks())
    settings = Path.home() / ".claude" / "settings.json"
    hooks_wired = False
    if settings.exists():
        data = json.loads(settings.read_text(encoding="utf-8"))
        hooks_wired = _hooks_wired(data)
    disabled = [p.strip() for p in os.environ.get("MAKOTO_DISABLE_PATTERNS", "").split(",") if p.strip()]
    print(json.dumps({
        "patterns_count": patterns_count,
        "patterns_disabled": disabled,
        "hooks_wired": hooks_wired,
        "state_dir": str(state_dir),
        "state_dir_present": state_dir.is_dir(),
    }, indent=2))
    return 0
