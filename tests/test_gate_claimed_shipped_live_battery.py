"""Adversarial transcript battery for gate.claimed_shipped through the real Stop dispatcher.

Every case uses events-table row tuples matching `_select_recent`, so this file tests catalog
wiring, pooled cross-agent history, PostToolUse settlement, and the claim/evidence predicates
together rather than replaying only the pure function.
"""
import json
import sqlite3
import subprocess

from makoto.dispatch import run_stop_checks
from makoto.checks.claimedShippedAbsent import _successful_remote_mutation


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd),
                    "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                    *args], check=True, capture_output=True, text=True)


def _pushed_repo(tmp_path):
    """A real work tree whose HEAD was actually pushed to a local `origin` — the ONLY evidence
    the push arm accepts (`pushed_tip_matches_remote` compares `rev-parse HEAD` to
    `ls-remote origin main`; a tmp dir that is not a git repo is NOT_EVALUABLE and returns
    None before any mechanism under test runs)."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)],
                   check=True, capture_output=True, text=True)
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", str(work)],
                   check=True, capture_output=True, text=True)
    (work / "f.txt").write_text("v1\n")
    _git(work, "add", "f.txt")
    _git(work, "commit", "-q", "-m", "c1")
    _git(work, "branch", "-M", "main")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-q", "origin", "main")
    return work

_COMMIT_DDL = (
    "CREATE TABLE commitments (commitment_key TEXT PRIMARY KEY, session_id TEXT, "
    "location TEXT, qty_min REAL, qty_max REAL, status TEXT NOT NULL DEFAULT 'open', "
    "retract_param TEXT, created_event_id INTEGER, ts TEXT)")
_LEDGER_DDL = (
    "CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT NOT NULL, "
    "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)")


def _conn():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute(_COMMIT_DDL)
    conn.execute(_LEDGER_DDL)
    return conn


def _row(idx, cwd, name, tool_input, response, event="PostToolUse", agent_id=None):
    payload = {
        "hook_event_name": event,
        "tool_name": name,
        "tool_input": tool_input,
        "tool_response": response,
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id
    return (idx, f"2026-07-24T00:00:{idx:02d}.000Z", event, cwd, json.dumps(payload))


def _messages(history, cwd, text):
    conn = _conn()
    findings = run_stop_checks(conn, {
        "hook_event_name": "Stop",
        "last_assistant_message": text,
        "session_id": "s",
        "cwd": cwd,
    }, history)
    conn.close()
    return [f.message for f in findings if getattr(f, "pattern_id", "") == "gate.claimed_shipped"]


# RED population: actual completed non-push claims with no successful remote mutation.
def test_red_bare_unbacked_merge_claim_fires(tmp_path):
    msgs = _messages([], str(tmp_path), "I merged the PR.")
    assert msgs, f"gate.claimed_shipped MUST fire on an unbacked merge claim: {msgs}"


def test_not_evaluable_failed_push_transcript_stays_silent_with_cwd(tmp_path):
    """cwd is present but not a git repo: the remote tip is NOT_EVALUABLE and the gate stays
    SILENT by design (pinned by tests/test_delegated_world_evidence.py: with a worktree present,
    an unobservable remote is deliberate fail-open — a failed-push transcript is never
    promoted into a remote verdict either way)."""
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "git push origin main"},
                    {"exitCode": 1, "stderr": "rejected"})]
    msgs = _messages(history, cwd, "I've pushed it to main.")
    assert not msgs, f"NOT_EVALUABLE with a cwd present must stay silent: {msgs}"


def test_red_push_claim_with_no_cwd_falls_back_to_evidence_route_and_fires():
    """With NO cwd at all, nothing world-side is consultable, so the push claim must fall back
    to the recorded-mutation-evidence route and FIRE when the only transcript is a failed push
    — absence is checked there, never read as green with nothing checked at all. Called on the
    gate directly: the live path can never deliver a falsy cwd (context.py substitutes the
    dispatch process's own CWD), so this arm is only reachable as a pure-function contract."""
    from makoto.checks.claimedShippedAbsent import claimed_shipped_gate
    history = [_row(1, "", "Bash", {"command": "git push origin main"},
                    {"exitCode": 1, "stderr": "rejected"})]
    f = claimed_shipped_gate("I've pushed it to main.", history=history, cwd=None)
    assert f is not None and "no recorded mutation evidence" in f.message, \
        f"no-cwd push claim MUST fire via the evidence route: {f}"
    assert "Push claim" not in f.message, "a transcript must never synthesize a remote verdict"


def test_not_evaluable_dry_run_transcript_stays_silent_with_cwd(tmp_path):
    """Same pinned fail-open: cwd present, remote unobservable — silent; the --dry-run
    transcript is not consulted as a remote verdict."""
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "git push origin main --dry-run"},
                    {"exitCode": 0})]
    msgs = _messages(history, cwd, "Pushed it to main.")
    assert not msgs, f"NOT_EVALUABLE with a cwd present must stay silent: {msgs}"


def test_red_failed_github_merge_does_not_back_claim(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "merge_pull_request", {"pullNumber": 42},
                    {"error": "merge conflict"})]
    msgs = _messages(history, cwd, "Merged #42.")
    assert msgs, f"gate.claimed_shipped MUST fire when the merge tool errored: {msgs}"


def test_not_evaluable_pretooluse_push_record_stays_silent_with_cwd(tmp_path):
    """cwd present, remote unobservable: silent by the pinned fail-open. The dangling
    PreToolUse row is additionally not settled evidence — pinned on the no-cwd route below."""
    cwd = str(tmp_path)
    history = [_row(1, cwd, "push_files", {"branch": "main"}, {},
                    event="PreToolUse")]
    msgs = _messages(history, cwd, "I pushed it to main.")
    assert not msgs, f"NOT_EVALUABLE with a cwd present must stay silent: {msgs}"


def test_red_no_cwd_dangling_pretooluse_is_not_settled_evidence():
    """On the no-cwd fallback route (pure-function, see above), a dangling PreToolUse push
    record must NOT discharge the claim: only a settled successful mutation is evidence."""
    from makoto.checks.claimedShippedAbsent import claimed_shipped_gate
    history = [_row(1, "", "push_files", {"branch": "main"}, {},
                    event="PreToolUse")]
    f = claimed_shipped_gate("I pushed it to main.", history=history, cwd=None)
    assert f is not None and "no recorded mutation evidence" in f.message, \
        f"a dangling PreToolUse row must not read as settled evidence: {f}"


# TN population: real evidence and adjacent linguistic near-misses.
def test_tn_genuine_push_then_claim_stays_silent(tmp_path):
    """A push claim whose local HEAD really IS origin/main's tip must be silent via the
    remote-tip MATCH arm — evaluated against a real repo, not skipped as NOT_EVALUABLE
    (a bare tmp cwd never reaches the mechanism this test names)."""
    work = _pushed_repo(tmp_path)
    msgs = _messages([], str(work), "I've pushed it to main.")
    assert not msgs, f"gate.claimed_shipped FALSE-POSITIVE on a genuinely pushed tip: {msgs}"


def test_red_push_claim_with_mismatched_remote_tip_fires(tmp_path):
    """The push arm's MISMATCH Finding must actually fire: local HEAD advanced past the pushed
    origin tip while the claim says 'pushed'. Without this RED, a mutant that silences the
    entire push branch (unconditional None) passes every case in this battery."""
    work = _pushed_repo(tmp_path)
    (work / "f.txt").write_text("v2\n")
    _git(work, "add", "f.txt")
    _git(work, "commit", "-q", "-m", "c2 (not pushed)")
    msgs = _messages([], str(work), "I've pushed it to main.")
    assert msgs and "Push claim" in msgs[0] and "is false" in msgs[0], \
        f"gate.claimed_shipped MUST fire the MISMATCH push finding -- battery VOID: {msgs}"


def test_tn_genuine_github_merge_then_claim_stays_silent(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "mcp__github__merge_pull_request", {"pullNumber": 42},
                    {"merged": True, "sha": "abc"})]
    msgs = _messages(history, cwd, "I merged the PR.")
    assert not msgs, f"gate.claimed_shipped FALSE-POSITIVE on a successful MCP merge: {msgs}"


def test_tn_subagent_did_it_main_thread_claims_it_stays_silent(tmp_path):
    """Pooled cross-agent evidence must discharge the main thread's claim through
    `_successful_remote_mutation`. The claim is a NON-push shipping claim on purpose: a push
    claim routes to the remote-tip arm and (in a non-repo tmp cwd) returns NOT_EVALUABLE
    before the pooling mechanism this test names is ever consulted."""
    cwd = str(tmp_path)
    history = [_row(1, cwd, "push_files", {"branch": "main"},
                    {"commit": {"sha": "abc"}}, agent_id="subagent-1")]
    msgs = _messages(history, cwd, "I shipped the change.")
    assert not msgs, f"gate.claimed_shipped FALSE-POSITIVE: subagent evidence must be pooled: {msgs}"


def test_tn_forward_promise_stays_silent_here(tmp_path):
    text = "I'll merge this once CI passes."
    msgs = _messages([], str(tmp_path), text)
    assert not msgs, f"gate.claimed_shipped FALSE-POSITIVE on a future promise: {msgs}"


def test_tn_passive_third_party_phrase_stays_silent(tmp_path):
    text = "It was merged by someone else."
    msgs = _messages([], str(tmp_path), text)
    assert not msgs, f"gate.claimed_shipped FALSE-POSITIVE on passive third-party prose: {msgs}"


def test_tn_negated_phrase_stays_silent(tmp_path):
    text = "I haven't merged it yet."
    msgs = _messages([], str(tmp_path), text)
    assert not msgs, f"gate.claimed_shipped FALSE-POSITIVE on a negated claim: {msgs}"


def test_tn_unrelated_ship_shaped_words_stay_silent(tmp_path):
    text = "This deploys to a CDN, and the store ships orders on Mondays."
    msgs = _messages([], str(tmp_path), text)
    assert not msgs, f"gate.claimed_shipped FALSE-POSITIVE on explanatory prose: {msgs}"


def test_tn_local_file_production_claim_remains_completion_scope(tmp_path):
    text = "I created src/widget.py."
    msgs = _messages([], str(tmp_path), text)
    assert not msgs, f"gate.claimed_shipped must not duplicate gate.completion: {msgs}"


# Law 1: transcript evidence fixtures genuinely carry opposite predicate values.
def test_law1_remote_mutation_precondition_separates_red_and_clean(tmp_path):
    cwd = str(tmp_path)
    red = [
        [],
        [_row(1, cwd, "Bash", {"command": "git push --dry-run origin main"}, {"exitCode": 0})],
        [_row(1, cwd, "Bash", {"command": "git push origin main"}, {"exitCode": 1})],
        [_row(1, cwd, "merge_pull_request", {}, {"error": "conflict"})],
    ]
    clean = [
        [_row(1, cwd, "Bash", {"command": "git push origin main"}, {"exitCode": 0})],
        [_row(1, cwd, "merge_pull_request", {}, {"merged": True})],
        [_row(1, cwd, "push_files", {}, {"commit": {"sha": "abc"}}, agent_id="subagent-1")],
    ]
    for history in red:
        assert _successful_remote_mutation(history) is False
    for history in clean:
        assert _successful_remote_mutation(history) is True
