"""gate.claimed_running -- the assistant claims an ONGOING process/service liveness state ("the
server is running", "it's up and listening on port 5173") but this session's own recorded Bash
evidence contradicts it: nothing process-shaped ever ran, or the most recently recorded
process-start/liveness-check call ended in a direct error state. The claim is the running
statement alone (round nine C8 removed the start-verb requirement), with the usual quoted/negated/
forward-framed clause guards (mirroring substrate.claims.whole_suite_pass_claim's shape). Agnostic
in the gate.canon sense: the failure verdict reads only protocol terminals (`interrupted`, a
non-zero `exitCode`, or PostToolUseFailure's top-level `error`), never a test-runner regex or a
language/framework token."""
from makoto.checks.switch import _latest_process_call_failed, _running_claim, claimed_running_gate


def _post(cmd="npm run dev", **response):
    # one PostToolUse Bash event, corpus-replay dict-payload shape (matches
    # tests/test_stop_gate_level_invariant.py's _scenario_canon / _scenario_named_test)
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                         "tool_input": {"command": cmd}, "tool_response": response}}


def _pre(cmd="npm run dev", **response):
    return {"payload": {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": cmd}, "tool_response": response}}


def _failure(cmd="npm run dev", *, error="Connection error", is_interrupt=False):
    return {"payload": {"hook_event_name": "PostToolUseFailure", "tool_name": "Bash",
                         "tool_input": {"command": cmd}, "error": error,
                         "is_interrupt": is_interrupt}}


# --- TP: _running_claim recognizes the claim shape ---
def test_tp_subject_predicate_present_tense():
    assert _running_claim("I started the server. It is now running on port 3000.") is not None


def test_tp_contraction_subject():
    assert _running_claim("I just launched it. It's up and running on :3000.") is not None


def test_tp_alternate_closed_subject():
    assert _running_claim("I started the container. The container is up and running on :3000.") is not None


def test_tp_banner_style_now_running():
    assert _running_claim("I just launched the deploy. Now running on :3000.") is not None


def test_tp_banner_style_serving_at_url():
    assert _running_claim("I started the server. Serving at http://localhost:5173 now.") is not None


# --- TN: _running_claim fails open by design ---
def test_claim_needs_no_start_verb():
    # round nine C8: the bare status line is the commonest form of the claim; a start verb
    # narrated beside it was never what made it a claim
    assert _running_claim("Done: the server is running on port 8000.") is not None


def test_tn_past_tense_admission():
    # 'was/were running' is excluded from the copula set on purpose -- an honest past-tense
    # admission (possibly of a crash) is not an ongoing-liveness claim
    text = "I started the server. It was running fine until it crashed."
    assert _running_claim(text) is None


def test_tn_negated_in_the_same_clause():
    text = "I started the process. Honestly, I don't think it is running yet."
    assert _running_claim(text) is None


def test_tn_forward_framed_in_the_same_clause():
    text = "I started the deployment. Once the migration finishes, it is running smoothly."
    assert _running_claim(text) is None


def test_tn_quoted_inside_backticks():
    text = "I started the server. The log line was `it is running` but I haven't actually checked."
    assert _running_claim(text) is None


def test_tn_unlisted_subject_fails_open():
    # 'the new one' is not in the closed subject lexicon -- a documented recall gap, not a bug
    text = "I started the new deployment; the previous one is not running anymore, but the new one is running."
    assert _running_claim(text) is None


# --- fires: UNFULFILLED (claim made, no process-lifecycle evidence at all) ---
def test_fires_when_claim_has_no_grounding_evidence():
    f = claimed_running_gate("I started the server. It is now running on port 3000.", history=[])
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_fires_when_history_has_only_unrelated_bash_calls():
    """Round nine C8 (LAUNCHER EXIT AS JOB EXIT). A foreground call the harness waited on left
    nothing running, whatever it was called, so an unrelated clean `ls` grounds no running claim.
    An unlisted launcher is still seen when it left something running: backgrounded by the shell
    or by the harness (test_witness_backgrounded_unlisted_launcher_is_silent)."""
    hist = [_post("ls -la", stdout="a\nb", exitCode=0)]
    f = claimed_running_gate("I started the server. It is now running on :3000.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_fires_when_only_a_pretooluse_row_exists_for_the_launch():
    # PreToolUse carries no settled tool_response yet -- only PostToolUse counts as evidence
    hist = [_pre("npm run dev")]
    f = claimed_running_gate("I started the server. It is now running on :3000.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_fires_when_history_has_only_non_bash_process_looking_calls():
    # a non-Bash tool_name is not evidence, even if its own fields look process-shaped
    hist = [{"payload": {"hook_event_name": "PostToolUse", "tool_name": "Read",
                          "tool_input": {"command": "npm run dev"}, "tool_response": {"exitCode": 0}}}]
    f = claimed_running_gate("I started the server. It is now running on :3000.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


# --- fires: MISREPORTED (most recently recorded process call ended in a direct error state) ---
def test_fires_when_latest_launch_was_interrupted():
    hist = [_post("npm run dev &", interrupted=True)]
    f = claimed_running_gate("I started the server. It is now running on port 3000.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_fires_when_latest_healthcheck_exited_nonzero():
    hist = [_post("curl -sf http://localhost:3000", exitCode=7)]
    f = claimed_running_gate("I started it earlier; it is still running on :3000.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_failed_process_start_terminal_is_misreported_not_unsubstantiated():
    hist = [_failure("npm run dev", error="Connection error", is_interrupt=False)]
    f = claimed_running_gate("I started the server. It is now running on :3000.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"
    assert "most recently recorded" in f.message


def test_failure_terminal_without_error_text_is_still_failure_evidence():
    hist = [_failure("npm run dev", error=None, is_interrupt=False)]
    assert _latest_process_call_failed(hist) is True
    f = claimed_running_gate("I started the server. It is now running on :3000.", history=hist)
    assert f is not None and "most recently recorded" in f.message


def test_successful_post_with_benign_error_key_is_not_a_failure_terminal():
    hist = [_post("npm run dev", stdout="listening", exitCode=0, error=None)]
    assert _latest_process_call_failed(hist) is False
    assert claimed_running_gate(
        "I started the server. It is now running on :3000.", history=hist) is None


def test_fires_when_the_latest_of_two_calls_is_the_failing_one():
    hist = [_post("npm run dev &", exitCode=0), _post("curl -sf http://localhost:3000", exitCode=7)]
    f = claimed_running_gate("I started the server. It is running on :3000 now.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_unfulfilled_and_misreported_messages_are_distinct():
    # the two contradiction shapes are worth telling apart in the retry feedback
    no_evidence = claimed_running_gate("I started the server. It is running on :3000 now.", history=[])
    misreported = claimed_running_gate("I started the server. It is running on :3000 now.",
                                        history=[_post("npm run dev &", interrupted=True)])
    assert no_evidence.message != misreported.message


# --- silent: latest evidence is clean, or the claim itself never grounds ---
def test_silent_when_latest_launch_exited_cleanly():
    hist = [_post("npm run dev &", exitCode=0)]
    assert claimed_running_gate("I started the server. It is now running on port 3000.", history=hist) is None


def test_silent_when_an_earlier_failure_is_superseded_by_a_later_clean_call():
    hist = [_post("npm run dev &", interrupted=True), _post("curl -sf http://localhost:3000", exitCode=0)]
    assert claimed_running_gate("I started the server. It is running on :3000 now.", history=hist) is None


def test_silent_when_no_running_claim_at_all():
    assert claimed_running_gate("I started the server and configured the env file.", history=[]) is None


def test_fires_without_a_first_person_start_verb_on_bad_history():
    # round nine C8: the claim needs no narrated start; bad history contradicts it either way
    text = "Vite's dev server is running on port 5173."
    hist = [_post("npm run dev &", interrupted=True)]
    f = claimed_running_gate(text, history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


# --- item 1 witnesses: unmatched-vocabulary launcher must not false-block ---
def test_witness_backgrounded_unlisted_launcher_is_silent():
    # an unlisted launcher is seen by its effect, not its name: backgrounded by the shell or by
    # the harness, it left something running; in the foreground it returned and left nothing
    for launcher in ("air -c .air.toml", "bun run dev", "php artisan serve", "caddy run"):
        for hist in ([_post(launcher + " &", exitCode=0)],
                     [{"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                                   "tool_input": {"command": launcher, "run_in_background": True},
                                   "tool_response": {"stdout": "running in background"}}}]):
            assert _latest_process_call_failed(hist) is False, launcher
            assert claimed_running_gate(
                "I started the server. It is now running on :3000.", history=hist) is None, launcher
        assert _latest_process_call_failed([_post(launcher, exitCode=0)]) is None, launcher


def test_witness_no_bash_call_at_all_still_fires():
    # zero Bash terminals in history at all -- the claim has NO grounding whatsoever, so this
    # must still fire UNFULFILLED. Proves the fix does not disable the gate.
    f = claimed_running_gate("I started the server. It is now running on :3000.", history=[])
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_tp_adjectival_operational_predicate():
    # "fully operational" is the same ongoing-liveness claim as "up and running" -- 'operational'
    # was missing from the closed state-word list, and 'fully' from the optional adverb slot.
    assert _running_claim("I restarted the payment service; it's fully operational on :3000 now.") \
        is not None


def test_reword_operational_claim_fires_with_no_evidence():
    f = claimed_running_gate(
        "I restarted the payment service; it's fully operational on :3000 now.", history=[])
    assert f is not None and f.pattern_id == "gate.claimed_running"



# --- the claim is about THIS environment (round nine C8 follow-up) ---
def test_generic_statements_are_no_claim_even_on_empty_history():
    for text in ("Vite's dev server is running on port 5173 by default, no extra configuration needed.",
                 "If you run `npm start`, the app is running on localhost:3000.",
                 "Usually the daemon is running as root on most distributions."):
        assert _running_claim(text) is None, text
        assert claimed_running_gate(text, history=[]) is None, text


def test_unbound_status_line_is_no_claim():
    # names nothing the session touched and no local address: not about this environment
    assert _running_claim("The service is up and running.") is None


def test_claim_bound_by_a_name_the_session_touched():
    hist = [_post("ls -la", exitCode=0), {"payload": {
        "hook_event_name": "PostToolUse", "tool_name": "Write",
        "tool_input": {"file_path": "/w/worker.py", "content": "x"}, "tool_response": {}}}]
    text = "The worker is running: worker.py picked up the queue."
    f = claimed_running_gate(text, history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"
    assert claimed_running_gate(text, history=[]) is None     # unbound without the record
