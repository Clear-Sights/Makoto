"""Shape tests: the rows that name an effect read it from `substrate.effect`, never from a spelling.

Each test makes the effect happen directly, between a Pre and a Post in a scratch repository, and
the command text is a placeholder: the check must fire on the effect because the text says nothing.
The spellings that once got past these rows are plants in the mesh harness outside this repository
(MAKOTO/mesh), not cases here."""
import json
import os
import subprocess

from tests.conftest import _run_dispatch, _setup_state

_GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
_UNREAD = "true"  # the command text a check could read; it names nothing


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, env=_GIT_ENV, capture_output=True)


class Session:
    def __init__(self, tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.state = _setup_state(tmp_path)
        self.repo = tmp_path / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.name", "t")
        _git(self.repo, "config", "user.email", "t@t")
        (self.repo / "work.py").write_text("def f():\n    return 1\n")
        (self.repo / "notes.txt").write_text("keep this\nand this\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "i")
        self.n = 0

    def call(self, tool="Bash", tool_input=None, effect=None, response=None, hook="PostToolUse", **extra):
        """One settled call whose effect is `effect(repo)`; returns the wire of the NEXT call's Pre."""
        self.n += 1
        base = {"session_id": "s", "cwd": str(self.repo), "tool_name": tool,
                "tool_input": tool_input or {"command": _UNREAD}, "tool_use_id": f"t{self.n}"}
        _run_dispatch(self.state, dict(base, hook_event_name="PreToolUse"))
        if effect is not None:
            effect(self.repo)
        _run_dispatch(self.state, dict(base, hook_event_name=hook,
                                       tool_response=response or {"stdout": "", "exitCode": 0}, **extra))
        return self.next()

    def next(self, tool="Read", tool_input=None):
        self.n += 1
        return _run_dispatch(self.state, {"session_id": "s", "cwd": str(self.repo), "tool_name": tool,
                                          "tool_input": tool_input or {"file_path": "x"},
                                          "tool_use_id": f"t{self.n}", "hook_event_name": "PreToolUse"})[1]

    def verifier(self):
        return self.call(tool_input={"command": "pytest -q"}, response={"stdout": "3 passed", "exitCode": 0})


# D14: content destroyed = content before the call that survives nowhere after it.
def test_d14_deleted_emptied_and_wholly_replaced_content_is_destroyed(tmp_path):
    for i, effect in enumerate((lambda r: (r / "work.py").unlink(),
                                lambda r: (r / "notes.txt").write_text(""),
                                lambda r: (r / "notes.txt").write_text("unrelated\n"))):
        s = Session(tmp_path / str(i))
        assert "gate.unobserved_destruction" in s.call(effect=effect), i


def test_d14_moved_and_edited_content_survives(tmp_path):
    s = Session(tmp_path)
    assert "gate.unobserved_destruction" not in s.call(effect=lambda r: (r / "notes.txt").rename(r / "moved.txt"))
    assert "gate.unobserved_destruction" not in s.call(
        effect=lambda r: (r / "work.py").write_text("def f():\n    return 2\n"))


def test_d14_a_verifier_before_or_after_the_destruction_discharges_it(tmp_path):
    s = Session(tmp_path / "after")
    s.call(effect=lambda r: (r / "work.py").unlink())
    s.verifier()
    assert "gate.unobserved_destruction" not in s.next()
    t = Session(tmp_path / "before")
    t.verifier()
    assert "gate.unobserved_destruction" not in t.call(effect=lambda r: (r / "work.py").unlink())


def test_d14_the_finding_restores_the_pre_image(tmp_path):
    s = Session(tmp_path)
    wire = s.call(effect=lambda r: (r / "notes.txt").write_text(""))
    subprocess.run(json.dumps(json.loads(wire)).split("`")[1], shell=True, check=True, env=_GIT_ENV)
    assert (s.repo / "notes.txt").read_text() == "keep this\nand this\n"


# E12: a switch that turns Makoto off or softens it, in any settings layer, however it got there.
def _settings(r, body, name="settings.json"):
    (r / ".claude").mkdir(exist_ok=True)
    (r / ".claude" / name).write_text(json.dumps(body))


def test_e12_every_switch_in_the_settings_interface_is_read(tmp_path):
    for i, body in enumerate(({"env": {"MAKOTO_DISABLE_GATES": "1"}}, {"env": {"MAKOTO_MODE": "silent"}},
                              {"enabledPlugins": {"makoto@any": False}}, {"disableAllHooks": True})):
        s = Session(tmp_path / str(i))
        s.verifier()
        assert "content.self_mute_guard" in s.call(effect=lambda r, b=body: _settings(r, b)), body
        (s.repo / ".claude" / "settings.json").unlink()
        assert "content.self_mute_guard" not in s.next()


def test_e12_unwiring_makoto_hooks_is_read_and_turning_it_back_on_is_silent(tmp_path):
    s = Session(tmp_path / "unwire")
    _settings(s.repo, {"hooks": {"PreToolUse": [{"hooks": [{"command": "makoto dispatch"}]}]}})
    s.verifier()
    assert "content.self_mute_guard" in s.call(effect=lambda r: _settings(r, {"hooks": {}}))
    t = Session(tmp_path / "reenable")
    _settings(t.repo, {"env": {"MAKOTO_DISABLE_GATES": "1"}})
    assert "content.self_mute_guard" not in t.call(
        effect=lambda r: _settings(r, {"env": {"MAKOTO_DISABLE_GATES": "0"}}))


# E3: a commit or written line crediting Claude or Anthropic as author, read off the result.
_WHO = "Cl" + "aude"  # makoto-allow: the identity these shape tests credit, assembled at run time


def test_e3_a_commit_whose_author_or_any_trailer_names_the_identity_is_read(tmp_path):
    for i, args in enumerate((["-c", f"user.name={_WHO}", "commit", "-q", "--allow-empty", "-m", "fix"],
                              ["commit", "-q", "--allow-empty", "-m", "fix", "-m", f"Any-Key: {_WHO}"])):
        s = Session(tmp_path / str(i))
        s.verifier()
        assert "content.illusory_authorship_trailer" in s.call(effect=lambda r, a=args: _git(r, *a)), args
        _git(s.repo, "reset", "-q", "--hard", "HEAD~1")
        assert "content.illusory_authorship_trailer" not in s.next()


def test_e3_a_written_attribution_line_is_read_and_a_human_or_product_mention_is_not(tmp_path):
    s = Session(tmp_path / "written")
    s.verifier()
    line = f"This change was generated using {_WHO}.\n"
    assert "content.illusory_authorship_trailer" in s.call(effect=lambda r: (r / "PR.md").write_text(line))
    t = Session(tmp_path / "human")
    t.verifier()
    assert "content.illusory_authorship_trailer" not in t.call(effect=lambda r: _git(
        r, "commit", "-q", "--allow-empty", "-m", f"hooks for {_WHO} Code", "-m", "Co-authored-by: Ada <a@b.c>"))


# C4: a settled call that printed a failure report and exited 0 masked it.
def test_c4_a_failure_printed_under_exit_0_is_masked_until_the_program_runs_again(tmp_path):
    s = Session(tmp_path)
    wire = s.call(tool_input={"command": "runner"}, response={"stdout": "1 failed, 3 passed", "exitCode": 0})
    assert "content.verifier_exit_masking" in wire
    assert "content.verifier_exit_masking" not in s.next("Bash", {"command": "runner"})


def test_c4_a_nonzero_exit_or_a_reader_masks_nothing(tmp_path):
    s = Session(tmp_path)
    assert "content.verifier_exit_masking" not in s.call(
        tool_input={"command": "runner"}, response={"stdout": "1 failed", "exitCode": 1})
    assert "content.verifier_exit_masking" not in s.call(
        tool_input={"command": "cat out.log"}, response={"stdout": "1 failed", "exitCode": 0})


# E11: a call its own limit stopped, retried as itself under a limit no larger.
def test_e11_a_retry_under_the_limit_that_stopped_it_is_denied_and_a_larger_one_is_not(tmp_path):
    s = Session(tmp_path)
    s.call(tool_input={"command": "job"}, hook="PostToolUseFailure", error="Command timed out after 2m 0s")
    assert "event.nested_budget" in s.next("Bash", {"command": "job"})
    assert "event.nested_budget" not in s.next("Bash", {"command": "job", "timeout": 600000})
    assert "event.nested_budget" not in s.next("Bash", {"command": "other"})


def test_e11_a_call_that_ran_its_whole_limit_is_read_from_elapsed_time_not_its_error_text(tmp_path, monkeypatch):
    s = Session(tmp_path)
    limit = 1500  # ms: the call's own limit, which it ran out
    s.call(tool_input={"command": "job", "timeout": limit}, effect=lambda r: __import__("time").sleep(1.6),
           response={"stdout": "", "exitCode": 143})
    assert "event.nested_budget" in s.next("Bash", {"command": "job", "timeout": limit})
    t = Session(tmp_path / "fast")
    t.call(tool_input={"command": "job", "timeout": limit}, response={"stdout": "", "exitCode": 1})
    assert "event.nested_budget" not in t.next("Bash", {"command": "job", "timeout": limit})
