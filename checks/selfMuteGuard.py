"""pattern 1.23 predicate — makoto self-mute guard.

Fires when the assistant's OWN Write/Edit to a Claude settings.json would DISABLE
makoto in-session: introducing a MAKOTO_DISABLE*/MAKOTO_PAUSE env var set truthy,
or REMOVING a `_makoto_managed` hook entry (un-wiring). The threat model is unique:
makoto inspects the assistant's tool calls, so the assistant editing the very file
that wires/configures makoto is a one-move self-bypass. The legitimate disable path
is OUT-OF-BAND (MAKOTO_DISABLE_* in the operator's shell) or LOUD (`makoto
uninstall`) — never an in-session edit to settings.json.

    NEVER an in-session edit to settings.json. A `makoto-allow` marker does NOT exempt this
    guard (unlike the content-scan patterns): muting the watcher is not an in-band, self-
    annotated decision — the seal on the mint cannot be signed by the would-be forger.

Custom predicate (not lib.factories.regex_file_predicate): the un-wire case compares the
REMOVED text against the introduced text, which the introduced-text-only scaffold
cannot express. Reads tool_input (NOT disk), per the §5.6 semantic-frame rule, so an
Edit/MultiEdit cannot evade it. Knight-Leveson: stdlib re only.
"""
from __future__ import annotations
import re
from typing import Optional

from makoto.lib.factories import scan_target_content
from makoto.schema import Finding, PreCheck

# The file makoto wires into: ~/.claude/settings.json (or settings.local.json).
_SETTINGS_RX = re.compile(r"\.claude/settings(?:\.local)?\.json$")
# A makoto-disable env var SET to a TRUTHY value — JSON ("KEY": "1") or shell (KEY=1).
# Truthy-only is the FP guard: setting DISABLE to 0/false is RE-ENABLING makoto and
# must never fire.
_DISABLE_ENV_RX = re.compile(
    r"MAKOTO_(?:DISABLE\w*|PAUSE)\b\s*[\"']?\s*[:=]\s*[\"']?(?:1|true|yes|on)\b",
    re.IGNORECASE)
# The marker makoto stamps on its managed hook entries (install._MAKOTO_CLAUDE_FLAG).
_MANAGED_RX = re.compile(r"_makoto_managed")
# A GLOBAL hook kill-switch (Claude Code's `disableAllHooks`, cited code.claude.com/docs/en/hooks)
# — disables EVERY hook, makoto included, via a key the env/un-wire branches never inspect.
# Truthy-only (": true") is the FP guard: setting it false RE-ENABLES hooks and must never fire.
_GLOBAL_DISABLE_RX = re.compile(r'"disableAllHooks"\s*:\s*true\b', re.IGNORECASE)
# makoto's own hook-command invocation token (the dispatch script / state dir it installs,
# install.py:76). If the REMOVED text carried it but the introduced text no longer does, the
# makoto command was gutted to a no-op while the wiring/seal may remain — a self-mute the
# un-wire branch (which keys on `_makoto_managed`) misses because the marker stays in both.
_MAKOTO_CMD_RX = re.compile(r"makoto_state|dispatch\.sh")


def _removed_text(tool_input: dict) -> str:
    """text being REMOVED/REPLACED: Edit.old_string or MultiEdit edits' old_strings."""
    old = tool_input.get("old_string") or ""
    if not old and isinstance(tool_input.get("edits"), list):
        old = "\n".join(e.get("old_string", "") for e in tool_input["edits"]
                        if isinstance(e, dict) and e.get("old_string"))
    return old


def predicate(*, current_event: dict, history: list, pattern: PreCheck,
              conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    ti = current_event.get("tool_input", {}) or {}
    fp = ti.get("file_path", "") or ""
    if not _SETTINGS_RX.search(fp):
        return None                                   # not a Claude settings file -> inert
    new_content = scan_target_content(ti)             # the INTRODUCED text (never old_string)

    removed = _removed_text(ti)                       # text being REMOVED/REPLACED (Edit/MultiEdit)
    reason = None
    snippet = ""
    m = _DISABLE_ENV_RX.search(new_content)
    gm = _GLOBAL_DISABLE_RX.search(new_content)
    if m:
        reason = f"introduces makoto-disabling env var ({m.group(0).strip()!r})"
        snippet = new_content[max(0, m.start() - 40): m.end() + 40]
    elif gm:
        # NEW-1: a global hook kill-switch silences EVERY hook (makoto included) in one move.
        reason = "introduces a global hook kill-switch (`disableAllHooks: true`)"
        snippet = new_content[max(0, gm.start() - 40): gm.end() + 40]
    elif _MANAGED_RX.search(removed) and not _MANAGED_RX.search(new_content):
        # un-wiring: a `_makoto_managed` hook in the REMOVED text, gone from the new text.
        reason = "removes makoto's `_makoto_managed` hook entry (un-wires the guard)"
        snippet = removed[:120]
    elif _MAKOTO_CMD_RX.search(removed) and not _MAKOTO_CMD_RX.search(new_content):
        # NEW-2: command-gut — the seal/marker may survive, but the dispatch invocation that
        # actually RUNS makoto is removed/replaced, leaving the watcher unreachable.
        reason = "guts makoto's hook command (the dispatch invocation is removed/replaced)"
        snippet = removed[:120]
    if reason is None:
        return None

    return Finding(
        pattern_id=pattern.id,
        file=fp,
        line=0,
        level=pattern.fire_level,
        message=(f"row {pattern.id} ({pattern.description}): {reason}. makoto watches "
                 f"your tool calls — disabling it in-session is a self-bypass; disable "
                 f"out-of-band (your shell) or run `makoto uninstall`."),
        retry_hint=pattern.retry_hint,
        snippet=snippet,
    )


from makoto.checks._loader import Check as _Check
RETRY_HINT = 'Do not disable makoto in-session. If a pause is genuinely needed, set MAKOTO_DISABLE_GATES / MAKOTO_DISABLE_PATTERNS in your OWN shell, or run `makoto uninstall` — both are out-of-band and operator-visible. Editing ~/.claude/settings.json to mute the hook that watches you is a self-bypass.'
DESCRIPTION = 'makoto self-mute — disabling/un-wiring makoto via settings.json'

CHECK = _Check(id='content.self_mute_guard', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('settings.json', 'MAKOTO_DISABLE', 'MAKOTO_PAUSE', '_makoto_managed', 'disableAllHooks', 'makoto_state'), retry_hint=RETRY_HINT, description=DESCRIPTION)
