"""Adversarial transcript battery for gate.claimed_shipped through the real Stop dispatcher.

Every case uses events-table row tuples matching `_select_recent`, so this file tests catalog
wiring, pooled cross-agent history, PostToolUse settlement, and the claim/evidence predicates
together rather than replaying only the pure function.
"""
import json
import sqlite3

from makoto._dispatch import run_stop_checks
from makoto.checks.claimedShippedAbsent import _successful_remote_mutation

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


# RED population: actual completed claims with no successful remote mutation.
def test_red_bare_unbacked_merge_claim_fires(tmp_path):
    msgs = _messages([], str(tmp_path), "I merged the PR.")
    assert msgs, f"gate.claimed_shipped MUST fire on an unbacked merge claim: {msgs}"


def test_red_failed_push_does_not_back_claim(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "git push origin main"},
                    {"exitCode": 1, "stderr": "rejected"})]
    msgs = _messages(history, cwd, "I've pushed it to main.")
    assert msgs, f"gate.claimed_shipped MUST fire when the recorded push failed: {msgs}"


def test_red_dry_run_push_does_not_back_claim(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "git push origin main --dry-run"},
                    {"exitCode": 0})]
    msgs = _messages(history, cwd, "Pushed it to main.")
    assert msgs, f"gate.claimed_shipped MUST fire when the only push was a dry run: {msgs}"


def test_red_failed_github_merge_does_not_back_claim(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "merge_pull_request", {"pullNumber": 42},
                    {"error": "merge conflict"})]
    msgs = _messages(history, cwd, "Merged #42.")
    assert msgs, f"gate.claimed_shipped MUST fire when the merge tool errored: {msgs}"


def test_red_pretooluse_is_not_completed_evidence(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "push_files", {"branch": "main"}, {},
                    event="PreToolUse")]
    msgs = _messages(history, cwd, "I pushed it to main.")
    assert msgs, f"gate.claimed_shipped MUST fire on dangling PreToolUse-only evidence: {msgs}"


# TN population: real evidence and adjacent linguistic near-misses.
def test_tn_genuine_push_then_claim_stays_silent(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "git push origin main"},
                    {"exitCode": 0, "stdout": "main -> main"})]
    msgs = _messages(history, cwd, "I've pushed it to main.")
    assert not msgs, f"gate.claimed_shipped FALSE-POSITIVE on a successful push: {msgs}"


def test_tn_genuine_github_merge_then_claim_stays_silent(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "mcp__github__merge_pull_request", {"pullNumber": 42},
                    {"merged": True, "sha": "abc"})]
    msgs = _messages(history, cwd, "I merged the PR.")
    assert not msgs, f"gate.claimed_shipped FALSE-POSITIVE on a successful MCP merge: {msgs}"


def test_tn_subagent_did_it_main_thread_claims_it_stays_silent(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "push_files", {"branch": "main"},
                    {"commit": {"sha": "abc"}}, agent_id="subagent-1")]
    msgs = _messages(history, cwd, "I pushed it to main.")
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
