"""Pure claim/evidence tests for gate.claimed_shipped."""
import json

from makoto.checks.claimedShippedAbsent import (
    PushTipStatus, _shipped_claim, _successful_remote_mutation, claimed_shipped_gate,
    pushed_tip_matches_remote,
)


def _event(name, tool_input=None, response=None, event="PostToolUse"):
    return {"payload": {
        "hook_event_name": event,
        "tool_name": name,
        "tool_input": tool_input or {},
        "tool_response": response if response is not None else {},
    }}


def _bash(command, **response):
    return _event("Bash", {"command": command}, response)


# Claim lexicon: positive completed-action and state families.
def test_claim_first_person_completed_actions():
    for text in (
        "I merged the PR.",
        "I've pushed it to main.",
        "I published the package.",
        "I deployed to production.",
        "I shipped the release.",
        "I released version 2.0.",
    ):
        assert _shipped_claim(text) is not None, text


def test_claim_subjectless_status_report_actions():
    for text in ("Pushed it to main.", "Merged #42.", "- Published the package."):
        assert _shipped_claim(text) is not None, text


def test_claim_present_result_states():
    for text in ("It's live now.", "The PR is now merged.", "The package is already published."):
        assert _shipped_claim(text) is not None, text


# Precision firewall: future, negated, passive, quoted, and explanatory prose.
def test_no_claim_for_forward_or_future_frames():
    for text in (
        "I'll merge this once CI passes.",
        "I will push it tomorrow.",
        "Once CI passes, the PR is now merged.",
    ):
        assert _shipped_claim(text) is None, text


def test_no_claim_for_negated_frames():
    for text in (
        "I haven't merged it yet.",
        "I did not push the branch.",
        "The package is not published yet.",
    ):
        assert _shipped_claim(text) is None, text


def test_no_claim_for_passive_or_third_party_frames():
    for text in (
        "It was merged by someone else.",
        "The PR got merged.",
        "Alice pushed it to main.",
        "The package was published yesterday.",
    ):
        assert _shipped_claim(text) is None, text


def test_no_claim_for_explanatory_or_unrelated_ship_words():
    for text in (
        "This deploys to a CDN when the workflow runs.",
        "The merge algorithm combines two sorted lists.",
        "We should push back on scope creep.",
        "The store ships orders on Mondays.",
        "The live variable analysis is complete.",
    ):
        assert _shipped_claim(text) is None, text


def test_no_claim_inside_code_span():
    assert _shipped_claim("The expected status is `It's live now.` but I did not verify it.") is None


# Evidence: successful Bash push and closed GitHub mutation set.
def test_successful_non_dry_run_git_push_is_evidence():
    assert _successful_remote_mutation([_bash("git push origin main", exitCode=0)]) is True


def test_git_push_with_global_options_is_evidence():
    assert _successful_remote_mutation([_bash("git -C /repo push origin main", exitCode=0)]) is True


def test_dry_run_push_is_not_evidence_regardless_of_flag_position():
    """SUPERSEDES the pre-2026-09-03 form of this test, which asserted
    `_successful_remote_mutation(...) is False` for a dry-run push.

    WHAT IT ASSERTED AND WHY THAT WAS THE DEFECT: `False` is this helper's FIRING value — a
    grounded claim that nothing shipped. A dry-run push is not a recognized push, so it fell
    through the closed vocabulary exactly as `gh pr merge`, `npm publish`, and `./deploy.sh`
    do. Pinning `False` there pinned "a vocabulary miss is a positive assertion of absence" as
    a requirement — the same shape repaired in gate.claimed_running (`_latest_process_call_failed`).

    WHAT IS ASSERTED NOW: a dry-run push is still NOT evidence — it must never return True.
    It is NOT-EVALUABLE (None) instead of firing. The property under test is unchanged
    ("a dry run does not discharge a shipping claim"); only the disposition of the miss moved
    from BLOCK to silence.
    """
    for command in (
        "git push --dry-run origin main",
        "git push origin main --dry-run",
        "git push -n origin main",
        "git push origin main -n",
    ):
        assert _successful_remote_mutation([_bash(command, exitCode=0)]) is not True, command
        assert _successful_remote_mutation([_bash(command, exitCode=0)]) is None, command


def test_failed_interrupted_or_unsettled_push_is_not_evidence():
    histories = (
        [_bash("git push origin main", exitCode=1, stderr="rejected")],
        [_bash("git push origin main", exitCode=0, interrupted=True)],
        [_bash("git push origin main")],
        [_event("Bash", {"command": "git push origin main"}, {"exitCode": 0}, event="PreToolUse")],
    )
    for history in histories:
        assert _successful_remote_mutation(history) is False


def test_successful_merge_pull_request_is_evidence():
    ev = _event("merge_pull_request", {"owner": "o", "repo": "r", "pullNumber": 42},
                {"merged": True, "sha": "abc"})
    assert _successful_remote_mutation([ev]) is True


def test_successful_fully_qualified_github_merge_is_evidence():
    ev = _event("mcp__github__merge_pull_request", {}, {"merged": True})
    assert _successful_remote_mutation([ev]) is True


def test_successful_push_files_is_evidence():
    ev = _event("push_files", {"branch": "main"}, {"commit": {"sha": "abc"}})
    assert _successful_remote_mutation([ev]) is True


def test_failed_or_ambiguous_remote_tool_response_is_not_evidence():
    histories = (
        [_event("merge_pull_request", {}, {"error": "conflict"})],
        [_event("merge_pull_request", {}, {"merged": False})],
        [_event("push_files", {}, {"is_error": True})],
        [_event("push_files", {}, {})],
    )
    for history in histories:
        assert _successful_remote_mutation(history) is False


def test_create_pull_request_is_intentionally_not_shipping_evidence():
    ev = _event("create_pull_request", {}, {"number": 42, "url": "https://example/pr/42"})
    assert _successful_remote_mutation([ev]) is False


def test_read_only_or_similarly_named_tool_is_not_evidence():
    for name in ("get_pull_request", "merge_pull_request_status", "Read"):
        assert _successful_remote_mutation([_event(name, {}, {"ok": True})]) is False


def test_malformed_history_rows_fail_open_as_evidence():
    """SUPERSEDES the pre-2026-09-03 form, which asserted `is False` for an all-undecodable
    window while its own name promised "fail open".

    WHAT IT ASSERTED AND WHY THAT WAS THE DEFECT: `False` is the FIRING value. The test's name
    and its assertion disagreed — a window of rows nobody could decode produced a BLOCK stating
    that no mutation evidence exists, when the dropped row could have been the very push the
    claim cites. Absence of parseable evidence is not evidence of absence.

    WHAT IS ASSERTED NOW: the name's actual promise. An undecodable window is NOT-EVALUABLE
    (None) and therefore silent.
    """
    assert _successful_remote_mutation([{"payload": "{"}, ("short",), None]) is None


# End-to-end pure gate verdict.
def test_gate_fires_on_bare_unbacked_claim():
    finding = claimed_shipped_gate("I merged the PR.", history=[])
    assert finding is not None
    assert finding.pattern_id == "gate.claimed_shipped"
    assert finding.level == "error"


def test_gate_silent_when_claim_has_successful_bash_evidence():
    history = [_bash("git push origin main", exitCode=0)]
    assert claimed_shipped_gate("I've pushed it to main.", history=history) is None


def test_gate_silent_when_claim_has_successful_non_bash_evidence():
    history = [_event("merge_pull_request", {}, {"merged": True})]
    assert claimed_shipped_gate("I merged the PR.", history=history) is None


def test_gate_fires_when_only_failed_mutation_exists():
    history = [_event("merge_pull_request", {}, {"error": "conflict"})]
    assert claimed_shipped_gate("I merged the PR.", history=history) is not None


def test_gate_silent_without_a_shipping_claim_even_with_bad_history():
    history = [_bash("git push --dry-run origin main", exitCode=0)]
    assert claimed_shipped_gate("This deploys to a CDN.", history=history) is None


def test_tuple_history_shape_is_supported():
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main"},
        "tool_response": {"exitCode": 0},
    })
    row = (1, "t", "PostToolUse", "/repo", payload)
    assert claimed_shipped_gate("Pushed it to main.", history=[row]) is None


def test_push_tip_match_upholds_claim(monkeypatch, tmp_path):
    def run(argv, **_kwargs):
        if "ls-remote" in argv:
            return type("R", (), {"returncode": 0, "stdout": "abc123\trefs/heads/main\n", "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": "abc123\n", "stderr": ""})()
    monkeypatch.setattr("makoto.checks.claimedShippedAbsent.subprocess.run", run)
    result = pushed_tip_matches_remote("I've pushed it to main.", tmp_path)
    assert result.status is PushTipStatus.MATCH


def test_push_tip_mismatch_refutes_claim_with_both_shas(monkeypatch, tmp_path):
    def run(argv, **_kwargs):
        if "ls-remote" in argv:
            return type("R", (), {"returncode": 0, "stdout": "remote456\trefs/heads/main\n", "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": "local123\n", "stderr": ""})()
    monkeypatch.setattr("makoto.checks.claimedShippedAbsent.subprocess.run", run)
    result = pushed_tip_matches_remote("I've pushed it to main.", tmp_path)
    assert result.status is PushTipStatus.MISMATCH
    assert (result.local_sha, result.remote_sha) == ("local123", "remote456")


def test_push_tip_without_remote_is_not_evaluable(monkeypatch, tmp_path):
    def run(argv, **_kwargs):
        if "ls-remote" in argv:
            return type("R", (), {"returncode": 128, "stdout": "", "stderr": "no remote"})()
        return type("R", (), {"returncode": 0, "stdout": "local123\n", "stderr": ""})()
    monkeypatch.setattr("makoto.checks.claimedShippedAbsent.subprocess.run", run)
    result = pushed_tip_matches_remote("I've pushed it to main.", tmp_path)
    assert result.status is PushTipStatus.NOT_EVALUABLE
