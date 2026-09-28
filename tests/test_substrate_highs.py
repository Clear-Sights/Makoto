"""Shape tests for two substrate faults the attacker found in every row at once.

A touched file under a directory with a capital letter was never read by the file-reading Stop
rows, because ledger keys are case-folded; and one decision showed only the worst finding, so a
second fault surfaced only after the first was fixed."""
from tests.conftest import _run_dispatch, _setup_state


def _event(repo, n, hook, **kw):
    return dict({"session_id": "s", "cwd": str(repo), "tool_use_id": f"t{n}", "hook_event_name": hook}, **kw)


def test_a_file_under_a_capitalised_directory_is_read_by_the_stop_rows(tmp_path):
    for d in ("lower", "Upper"):
        (tmp_path / d).mkdir()
        state = _setup_state(tmp_path / d)
        repo = tmp_path / d / "repo"
        f = repo / d / "test_a.py"
        f.parent.mkdir(parents=True)
        body = "def test_a():\n    assert True\n"
        call = {"tool_name": "Write", "tool_input": {"file_path": str(f), "content": body}}
        _run_dispatch(state, _event(repo, 1, "PreToolUse", **call))
        f.write_text(body)
        _run_dispatch(state, _event(repo, 1, "PostToolUse", tool_response={"success": True}, **call))
        wire = _run_dispatch(state, _event(repo, 2, "Stop", stop_hook_active=False))[1]
        assert "gate.hollow_test" in wire, d


_WHO = "Cl" + "aude"  # makoto-allow: the identity this shape test credits, assembled at run time


def test_every_finding_rides_the_decision_not_only_the_worst(tmp_path):
    state = _setup_state(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    body = ('{"env": {"MAKOTO_DISABLE_GATES": "1"}, '
            f'"note": "Co-Authored-By: {_WHO} <noreply@anthrop' + 'ic.com>"}')
    wire = _run_dispatch(state, _event(repo, 1, "PreToolUse", tool_name="Write", tool_input={
        "file_path": str(repo / ".claude" / "settings.json"), "content": body}))[1]
    assert "content.self_mute_guard" in wire and "content.illusory_authorship_trailer" in wire
