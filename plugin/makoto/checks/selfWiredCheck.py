from __future__ import annotations
import json
import os
from typing import Optional
from makoto.vocab import Finding
from makoto.kit import live_query_finding
# The wiring predicate lives in makoto.substrate.wiring (an L0 primitive module, firewall-
# allowed by tests/test_import_direction.py's pipeline-order firewall), shared with install.py
# rather than mirrored here. See docs/adr/0041-wiring-predicate-hoist.md for the decision
# history.
from makoto.substrate.wiring import (
    PLUGIN_MANIFEST_RELPATH as _PLUGIN_MANIFEST_RELPATH,
    entry_dispatches_to_makoto as _entry_dispatches_to_makoto,
    event_wired as _event_wired,
    read_plugin_manifest_hooks as _read_plugin_manifest_hooks,
)

_MAKOTO_EVENTS = ("PreToolUse", "PostToolUse", "Stop")
# The FULL event set the plugin-packaged manifest wires (plugin/hooks/hooks.json): the three
# settings.json events above PLUS the plugin-only edges. Stop-edge checks genuinely run through
# SubagentStop (tests/test_dispatch.py pins gates firing through it), so a plugin manifest
# stripped of SubagentStop/SessionStart/PostToolUseFailure is a real partial strip, not noise.
# Demanded ONLY from the TRUSTED env-resolved manifest of a live plugin-packaged install; the
# settings.json sources keep the 3-event scope, which matches install._WIRED_EVENTS exactly.
_PLUGIN_MANIFEST_EVENTS = _MAKOTO_EVENTS + ("SubagentStop", "SessionStart", "PostToolUseFailure")


def _default_plugin_fs_read(path):
    try:
        if not os.path.isfile(path):
            # A FIFO or device node planted at the path would block open().read() forever,
            # wedging the Stop hook (no JSON on stdout, never exits 0) -- same isfile guard
            # the injected reader in context.py carries.
            return None
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


# The plugin root THIS running makoto lives under: .../<root>/makoto/checks/selfWiredCheck.py
# -> <root>. The dispatch shim cd's into $CLAUDE_PLUGIN_ROOT and execs `python3 -m
# makoto.dispatch` from there, so for a genuine plugin-packaged install the running package's
# grandparent directory IS the live plugin root. A static property of this file, safe to bind
# at import; consumed by the `_trusted_env_root` identity assertion nested in
# `_missing_makoto_events` and `self_wired_gate` (nested, not top-level -- the flat def count
# is part of this package's pinned shape), which keeps a decoy/forged $CLAUDE_PLUGIN_ROOT from
# ever CONFIRMING wiring: without it, a decoy root carrying a copied manifest silently
# suppresses a real full strip (absence reading green). A foreign or unverifiable root degrades
# to None -- "confirms nothing" -- the same fail-closed direction read_plugin_manifest_hooks
# documents; this is the concrete meaning of the docstring's "never a guessed/cached path".
_OWN_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _missing_makoto_events(hooks, *, plugin_root=None, plugin_fs_read=None,
                           home_hooks=None, events=_MAKOTO_EVENTS) -> list:
    """[event, ...] for each event in `events` confirmed by NONE of: settings.json's own "hooks"
    key, the home `~/.claude/settings.json` hooks passed as `home_hooks` (the file
    `makoto install` actually writes), or the plugin manifest (2026-07-22 two-source fix: a
    plugin-packaged install legitimately wires makoto via hooks/hooks.json alone, and
    settings.json is never expected to duplicate it — this predicate checks every source before
    calling an event missing). Empty list means fully wired. `plugin_root` defaults to the live
    $CLAUDE_PLUGIN_ROOT — identity-checked against the running package's own plugin root, so a
    decoy root can never confirm wiring — and `plugin_fs_read` to an isfile-guarded real file
    read when not supplied, so this stays pure/injectable for tests exactly like the
    settings.json side already is — see tests/test_self_wired_check.py.

    `hooks` NORMALIZATION IS PART OF THIS CONTRACT, not an incidental guard: a missing/None/
    non-dict `hooks` is read as {} (i.e. "wires nothing", so all three events report missing),
    so no caller needs its own isinstance pre-guard. Load-bearing for
    `test_hooks_key_not_a_dict_fails_open_to_missing_all`; do not drop it."""
    settings_hooks = hooks if isinstance(hooks, dict) else {}
    home = home_hooks if isinstance(home_hooks, dict) else {}
    still_missing = [event for event in events
                     if not _event_wired(settings_hooks, event)
                     and not _event_wired(home, event)]
    if not still_missing:
        return []
    root = plugin_root
    if root is None:
        # Env-derived root: identity-checked against _OWN_PLUGIN_ROOT (see its comment) so a
        # decoy $CLAUDE_PLUGIN_ROOT can never CONFIRM wiring; mirrored in self_wired_gate.
        root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if root:
            try:
                if os.path.realpath(root) != os.path.realpath(_OWN_PLUGIN_ROOT):
                    root = None
            except OSError:
                root = None
    reader = plugin_fs_read if plugin_fs_read is not None else _default_plugin_fs_read
    plugin_hooks = _read_plugin_manifest_hooks(root, reader)
    return [event for event in still_missing if not _event_wired(plugin_hooks, event)]


def self_wired_gate(fs_read, *, plugin_root=None, plugin_fs_read=None,
                    home_fs_read=None) -> Optional[Finding]:
    """Partial-strip detection only: catches an edit that leaves at least one of makoto's
    PreToolUse/PostToolUse/Stop entries wired (in ANY consultable source) while removing
    another; an edit that strips wiring from ALL sources for ALL events simultaneously disables
    this check itself in the same instant (Claude Code reloads hooks.json live, not cached once
    at session start — verified against code.claude.com/docs/en/settings.md, "When edits take
    effect"), so it still provides ZERO coverage against that canonical full-strip attack. See
    docs/self-defense-asymmetry-followup.md for the fuller writeup; this check is recorded
    there as mitigation, not closure.

    THREE wiring sources, checked with IDENTICAL rigor: the project `.claude/settings.json`'s
    own "hooks" key (repo-root-relative, read via `fs_read`), the HOME `~/.claude/settings.json`
    — the file `makoto install` actually writes (install._settings_path), read via
    `home_fs_read` (defaults to an isfile-guarded real read; consultable only when it carries a
    real hooks dict) — and the makoto plugin's own hooks/hooks.json manifest, resolved via
    `plugin_root` (defaults to the live $CLAUDE_PLUGIN_ROOT, identity-checked against the
    plugin root the RUNNING package lives under so a decoy/forged root can never confirm wiring
    — the concrete meaning of "never a guessed/cached path") and read via `plugin_fs_read`
    (defaults to the same isfile-guarded read). Fires iff an event is confirmed by NO source; an
    absent/empty project settings.json no longer short-circuits the other sources (it used to
    return None before the manifest was ever consulted, leaving the whole check inert in any
    repo without a project settings file — including a plugin-packaged install, the main way
    makoto ships). When NO source is even consultable (no project settings, no home hooks
    table, no trusted plugin root), there is no fact to assert either way, so the gate stays
    silent. The message names exactly which event(s) lost their entry and which sources were
    consulted; the Finding's `file` points at a source that was actually consulted, never
    unconditionally at a project settings file that may not exist.

    For a TRUSTED env-resolved plugin manifest the demanded event set widens from the three
    settings.json events to every event the packaged manifest declares
    (`_PLUGIN_MANIFEST_EVENTS`): SubagentStop/SessionStart/PostToolUseFailure enforcement is
    real (Stop gates fire through SubagentStop — tests/test_dispatch.py), so stripping those
    keys from a plugin-packaged hooks/hooks.json must not read clean.

    ADVISORY tier only (`level="advisory"`, never `"error"`): per this repo's "advisory over
    blocking" standing policy and the explicit condition this check shipped under, it must never
    block a turn — `_emit_decision` in dispatch.py maps level=="advisory" to posture.ADVISE, and
    wire.py's Stop/SubagentStop table has no ADVISE entry (only BLOCK renders there), so an
    advisory finding is recorded to the audit log (a forensic trail) and never surfaces as a
    block. Fail-open on a MALFORMED project settings.json (unparseable JSON or a non-dict
    payload returns None silently, matching every other gate's fail-open philosophy); the
    plugin-manifest side fails CLOSED instead (any read/resolution failure there degrades to
    "confirms nothing", never to silent-wired — an unresolvable/forged plugin_root must never
    suppress a real finding). This still cannot distinguish a genuine simultaneous full strip
    of every source (the documented blind spot above) — it reads disk state at check time, not
    the harness's own live-loaded hook table."""
    if fs_read is None:
        return None
    try:
        raw = fs_read(".claude/settings.json")
    except Exception:
        return None
    project_hooks = None
    project_consulted = False
    if raw:
        try:
            data = json.loads(raw)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        project_consulted = True
        # No isinstance pre-guard here: normalizing a missing/non-dict "hooks" to {} is part of
        # `_missing_makoto_events`'s own documented contract (see its docstring).
        project_hooks = data.get("hooks")
    # The HOME `~/.claude/settings.json` -- the file `makoto install` actually writes
    # (install._settings_path). Consultable ONLY when it carries a real non-empty hooks dict:
    # a hooks-less home settings can neither confirm nor indict, so it never triggers a
    # finding on its own and never silences one.
    home_hooks = None
    home_path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    try:
        raw_home = (home_fs_read if home_fs_read is not None
                    else _default_plugin_fs_read)(home_path)
    except Exception:
        raw_home = None
    if raw_home:
        try:
            home_data = json.loads(raw_home)
        except Exception:
            home_data = None
        if isinstance(home_data, dict):
            candidate = home_data.get("hooks")
            if isinstance(candidate, dict) and candidate:
                home_hooks = candidate
    env_root = None
    if plugin_root is None:
        # Env-derived root: identity-checked against _OWN_PLUGIN_ROOT (see its comment) so a
        # decoy $CLAUDE_PLUGIN_ROOT can never CONFIRM wiring; mirrored in
        # _missing_makoto_events's own default path for its direct callers (configchange.py).
        env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if env_root:
            try:
                if os.path.realpath(env_root) != os.path.realpath(_OWN_PLUGIN_ROOT):
                    env_root = None
            except OSError:
                env_root = None
    root = plugin_root if plugin_root is not None else env_root
    if not (project_consulted or home_hooks is not None or root):
        # No source is even consultable: project settings absent/empty, home settings carries
        # no hooks table, no trusted plugin root. There is no wiring fact to assert either
        # way -- fail-open on total absence, never a Finding resting on an unconsulted oracle.
        return None
    events = _PLUGIN_MANIFEST_EVENTS if env_root else _MAKOTO_EVENTS
    missing = _missing_makoto_events(project_hooks, plugin_root=root,
                                     plugin_fs_read=plugin_fs_read,
                                     home_hooks=home_hooks, events=events)
    if not missing:
        return None
    named = ", ".join(missing)
    manifest_path = os.path.join(root, _PLUGIN_MANIFEST_RELPATH) if root else None
    consulted = []
    if project_consulted:
        consulted.append(".claude/settings.json")
    if home_hooks is not None:
        consulted.append("~/.claude/settings.json")
    if manifest_path:
        consulted.append(manifest_path)
    if project_consulted:
        finding_file = ".claude/settings.json"
    elif manifest_path:
        finding_file = manifest_path
    else:
        finding_file = os.path.join("~", ".claude", "settings.json")
    return Finding(
        pattern_id="gate.self_wired",
        file=finding_file,
        line=0,
        level="advisory",
        message=(f"makoto's hook wiring is missing an entry for: {named} in every consultable "
                 f"wiring source ({'; '.join(consulted)}). "
                 "This is a PARTIAL-STRIP signal only — it cannot see a simultaneous strip of "
                 "all events from every source at once (see this check's own docstring / "
                 "docs/self-defense-asymmetry-followup.md)."),
        retry_hint=("Advisory only, never blocking: confirm this was an intentional change, or "
                    "restore the missing hook entry — `makoto install` re-wires "
                    "~/.claude/settings.json; a plugin-packaged install needs its "
                    "hooks/hooks.json manifest restored (re-enable/reinstall the plugin)."),
    )


# NOTE (owner-revised deviation, logged): this CHECK's posture is "ADVISE", not "BLOCK" like every
# sibling Stop gate. gate.self_wired's own Finding.level is documented and behaviorally pinned
# (tests/test_stop_gate_level_invariant.py) as ALWAYS "advisory", never "error" (the one
# DESIGN-DECISION-cited advisory exception among the Stop gates, FD6 2026-07-05) -- declaring it
# CHECK.posture="BLOCK" here would misrepresent that in the flat checks/ catalog's own metadata.
# `may_block=True` here is NOT a contradiction: it only says "structurally eligible IF posture
# were ever BLOCK" (it isn't, and is pinned as such by the test above) -- the actual never-blocks
# guarantee still rests on posture=="ADVISE", same as always.
from makoto.registry import Check as _Check
run = live_query_finding(
    query=lambda fs_read: self_wired_gate(fs_read), posture_label="gate.self_wired"
)
CHECK = _Check(id="gate.self_wired", applies_at="Stop", posture="ADVISE", may_block=True,
               eats=frozenset({"fs_read"}),
               run=run, layer="meta", tests="LIVE_QUERY")
