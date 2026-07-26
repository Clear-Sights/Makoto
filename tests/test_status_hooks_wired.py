"""`makoto status` must report hooks_wired by the FUNCTIONAL truth (a hook dispatches to makoto), not
only by the `_makoto_managed` marker the uninstaller keys on. A hand-wired / shim install
(command -> makoto_state/dispatch.sh, no flag) is still wired and must read as such."""
from makoto import install
def test_flagged_managed_entry_is_wired():
    data = {"hooks": {"Stop": [{"_makoto_managed": True,
                                "hooks": [{"type": "command", "command": "anything"}]}]}}
    assert install._hooks_wired(data)


def test_flagless_dispatch_shim_entry_is_wired():
    # the exact shape on this device: command points at makoto_state/dispatch.sh, no managed flag
    data = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": "/Users/x/.claude/makoto_state/dispatch.sh"}]}]}}
    assert install._hooks_wired(data)


def test_module_dispatch_command_is_wired():
    data = {"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": "python -m makoto._dispatch"}]}]}}
    assert install._hooks_wired(data)


def test_unrelated_hook_is_not_wired():
    data = {"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": "python -m something_else"}]}]}}
    assert not install._hooks_wired(data)


def test_empty_settings_is_not_wired():
    assert not install._hooks_wired({})
