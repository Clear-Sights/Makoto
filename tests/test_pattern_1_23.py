"""pattern 1.23 — makoto self-mute guard.

Fires when the assistant's OWN Write/Edit to ~/.claude/settings.json would
disable or un-wire makoto: introducing a MAKOTO_DISABLE*/MAKOTO_PAUSE env var
set truthy, OR removing a `_makoto_managed` hook entry. The threat model is
unique: makoto inspects the assistant's tool calls, so the assistant editing
the very file that wires/configures makoto is a self-bypass. The legitimate
disable path is OUT-OF-BAND (env var in the operator's shell) or LOUD
(`makoto uninstall`) — never an in-session edit to settings.json.

FP discipline (must stay silent): unrelated settings edits, an unrelated env
var, re-ENABLING makoto (DISABLE set to a falsey value), the same shape in a
NON-settings file (docs/examples), an edit that KEEPS the managed hook.
"""
from makoto.schema import PreCheck
from makoto.prechecks import precheck_1_23


_SETTINGS = "/Users/dev/.claude/settings.json"

_PAT = PreCheck(
    id="1.23",
    fire_level="error",
    description="makoto self-mute — disabling/un-wiring makoto via settings.json",
    retry_hint="Do not disable makoto in-session. If a pause is genuinely needed, set "
               "MAKOTO_DISABLE_GATES/MAKOTO_DISABLE_PATTERNS in your own shell, or run "
               "`makoto uninstall` — both are out-of-band and operator-visible.",
    predicate_module="makoto.prechecks.precheck_1_23",
    keywords=["settings.json", "MAKOTO_DISABLE", "MAKOTO_PAUSE", "_makoto_managed"],
)


def _pre(file_path, *, content=None, new_string=None, old_string=None, edits=None,
         tool_name="Write"):
    ti = {"file_path": file_path}
    if content is not None:
        ti["content"] = content
    if new_string is not None:
        ti["new_string"] = new_string
    if old_string is not None:
        ti["old_string"] = old_string
    if edits is not None:
        ti["edits"] = edits
    return {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": ti}


def _run(payload):
    return precheck_1_23.predicate(current_event=payload, history=[], pattern=_PAT, conn=None)


# ---- FIRE: introducing a makoto-disable env var into settings.json --------------

def test_fire_write_disable_gates_truthy():
    p = _pre(_SETTINGS, content='{"env": {"MAKOTO_DISABLE_GATES": "1"}}')
    f = _run(p)
    assert f is not None and f.pattern_id == "1.23" and f.level == "error"


def test_fire_edit_disable_patterns_new_string():
    p = _pre(_SETTINGS, new_string='"MAKOTO_DISABLE_PATTERNS": "1.1,1.23"', tool_name="Edit")
    assert _run(p) is not None


def test_fire_pause_var():
    p = _pre(_SETTINGS, content='{"env": {"MAKOTO_PAUSE": "true"}}')
    assert _run(p) is not None


def test_fire_multiedit_disable_among_edits():
    edits = [
        {"old_string": '"theme": "dark"', "new_string": '"theme": "light"'},
        {"old_string": '"env": {}', "new_string": '"env": {"MAKOTO_DISABLE_GATES": "yes"}'},
    ]
    p = _pre(_SETTINGS, edits=edits, tool_name="MultiEdit")
    assert _run(p) is not None


def test_fire_settings_local_json():
    """settings.local.json is also a Claude settings file makoto can be wired in."""
    p = _pre("/Users/dev/.claude/settings.local.json", content='{"env":{"MAKOTO_DISABLE_GATES":"on"}}')
    assert _run(p) is not None


# ---- FIRE: un-wiring (removing the _makoto_managed hook entry) -------------------

def test_fire_edit_removes_managed_hook():
    old = '{"_makoto_managed": true, "hooks": [{"type":"command","command":"~/.claude/makoto_state/dispatch.sh"}]}'
    new = '{}'
    p = _pre(_SETTINGS, old_string=old, new_string=new, tool_name="Edit")
    assert _run(p) is not None


# ---- FIRE (NEW-1, §completeness survey): a GLOBAL hook kill-switch silences every hook ----

def test_fire_global_disable_all_hooks_truthy():
    """`"disableAllHooks": true` turns off the whole hook layer (makoto included) via a key
    1.23's env/un-wire branches never inspect — a one-move total self-mute."""
    p = _pre(_SETTINGS, content='{"disableAllHooks": true}')
    f = _run(p)
    assert f is not None and f.pattern_id == "1.23" and f.level == "error"

def test_fire_global_disable_all_hooks_edit():
    p = _pre(_SETTINGS, new_string='"disableAllHooks": true', tool_name="Edit")
    assert _run(p) is not None

def test_inert_global_disable_all_hooks_false():
    """setting disableAllHooks to false is RE-ENABLING hooks — never fire (truthy-only guard)."""
    p = _pre(_SETTINGS, content='{"disableAllHooks": false}')
    assert _run(p) is None

def test_inert_disable_all_hooks_in_non_settings_file():
    p = _pre("/Users/dev/project/README.md", content='Set `"disableAllHooks": true` to turn off hooks.')
    assert _run(p) is None


# ---- FIRE (NEW-2): keep the wiring but GUT makoto's hook command to a no-op ----

def test_fire_guts_makoto_command_to_noop():
    """The _makoto_managed seal stays, but the dispatch invocation is replaced by a no-op —
    the un-wire branch sees the marker in both old and new (silent), yet makoto is unreachable."""
    old = '{"type":"command","command":"/Users/dev/.claude/makoto_state/dispatch.sh","_makoto_managed":true}'
    new = '{"type":"command","command":"true","_makoto_managed":true}'
    p = _pre(_SETTINGS, old_string=old, new_string=new, tool_name="Edit")
    f = _run(p)
    assert f is not None and f.pattern_id == "1.23"

def test_fire_guts_makoto_command_to_bogus_path():
    old = '{"command":"~/.claude/makoto_state/dispatch.sh"}'
    new = '{"command":"/bin/true"}'
    p = _pre(_SETTINGS, old_string=old, new_string=new, tool_name="Edit")
    assert _run(p) is not None

def test_inert_command_edit_keeps_makoto_invocation():
    """changing an unrelated field while keeping the makoto command must not fire."""
    old = '{"command":"~/.claude/makoto_state/dispatch.sh","timeout":5}'
    new = '{"command":"~/.claude/makoto_state/dispatch.sh","timeout":10}'
    p = _pre(_SETTINGS, old_string=old, new_string=new, tool_name="Edit")
    assert _run(p) is None


# ---- INERT: must stay silent ----------------------------------------------------

def test_inert_unrelated_env_var():
    p = _pre(_SETTINGS, content='{"env": {"FOO_BAR": "1", "EDITOR": "vim"}}')
    assert _run(p) is None


def test_inert_reenabling_disable_set_falsey():
    """setting DISABLE to a falsey value is RE-ENABLING makoto — never fire."""
    p = _pre(_SETTINGS, content='{"env": {"MAKOTO_DISABLE_GATES": "0"}}')
    assert _run(p) is None


def test_inert_disable_mentioned_in_non_settings_file():
    """documenting MAKOTO_DISABLE_GATES in a README is not a self-mute."""
    p = _pre("/Users/dev/project/README.md", content='Set `MAKOTO_DISABLE_GATES=1` to pause gates.')
    assert _run(p) is None


def test_inert_edit_keeps_managed_hook():
    """adding an unrelated hook while keeping the makoto entry must not look like un-wiring."""
    old = '{"_makoto_managed": true, "command": "dispatch.sh"}'
    new = '{"_makoto_managed": true, "command": "dispatch.sh"}, {"command": "other.sh"}'
    p = _pre(_SETTINGS, old_string=old, new_string=new, tool_name="Edit")
    assert _run(p) is None


# ---- FIRE: a makoto-allow marker must NOT exempt a self-mute (the seal is un-forgeable) ----

def test_fire_makoto_allow_does_not_exempt_self_mute():
    """§7.5a: muting makoto is never in-band allow-listable. A settings.json edit that
    disables makoto fires even when annotated with makoto-allow — the legitimate disable
    path is out-of-band (operator shell) or `makoto uninstall`, never an in-session marker."""
    p = _pre(_SETTINGS, content='{"env": {"MAKOTO_DISABLE_GATES": "1"}}  // makoto-allow: operator asked me to pause for this debug session')
    f = _run(p)
    assert f is not None and f.pattern_id == "1.23" and f.level == "error"


def test_inert_non_pretooluse_event():
    p = dict(_pre(_SETTINGS, content='{"env":{"MAKOTO_DISABLE_GATES":"1"}}'))
    p["hook_event_name"] = "Stop"
    assert _run(p) is None


def test_multiedit_with_non_dict_entry():
    """_removed_text must guard non-dict entries in the edits list. The
    `isinstance(e, dict) and e.get('old_string')` filter short-circuits on a
    non-dict (str) entry so it's skipped silently; flipping AND->OR forces
    `e.get('old_string')` on the str and raises AttributeError. A MultiEdit
    carrying a valid dict entry plus a stray non-dict entry (unrelated content)
    must stay inert — never crash."""
    p = _pre(_SETTINGS,
             edits=[{"old_string": "x", "new_string": "y"}, "not_a_dict"],
             tool_name="MultiEdit")
    assert _run(p) is None


# ---- ANTI-GOODHART CANARY: a known-fire + known-inert must both classify right ---

def test_anti_goodhart_canary_fire_and_inert():
    fire = _pre(_SETTINGS, content='{"env": {"MAKOTO_DISABLE_GATES": "1"}}')
    inert = _pre(_SETTINGS, content='{"env": {"UNRELATED": "1"}}')
    fired = _run(fire) is not None
    silent = _run(inert) is None
    # If EITHER is misclassified, the detector is biased (fire-on-all or fire-on-none) — VOID.
    assert fired and silent, "canary breached: detector is not discriminating"


def test_catalog_row_exists_and_matches():
    """the live catalog must declare 1.23 with the predicate wired (no test/catalog drift)."""
    from pathlib import Path
    from makoto.schema import load_prechecks
    cat = {p.id: p for p in load_prechecks(Path(__file__).parent.parent / "data" / "patterns.toml")}
    assert "1.23" in cat, "patterns.toml missing row 1.23"
    row = cat["1.23"]
    assert row.predicate_module == "makoto.prechecks.precheck_1_23"
    assert row.fire_level == "error"
    assert "settings.json" in row.keywords
