"""gate.claimed_running -- the assistant claims an ONGOING process/service liveness state ("the
server is running", "it's up and listening on port 5173") but this session's own recorded Bash
evidence contradicts it: nothing process-shaped ever ran, or the most recently recorded
process-start/liveness-check call ended in a direct error state. FP-safe by design: the claim only
fires when a first-person process-start verb ("I started/launched/ran ...") co-occurs anywhere in
the same message -- generic explanatory prose about a tool's default behavior essentially never
also narrates the assistant itself starting something -- plus the usual quoted/negated/
forward-framed clause guards (mirroring substrate.claims.whole_suite_pass_claim's shape). Agnostic
in the gate.canon sense: the failure verdict reads only protocol terminals (`interrupted`, a
non-zero `exitCode`, or PostToolUseFailure's top-level `error`), never a test-runner regex or a
language/framework token."""
from makoto.checks.claimedRunningAbsent import (
    _latest_process_call_failed,
    _running_claim,
    claimed_running_gate,
)


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
    assert _running_claim("I just launched it. It's up and running.") is not None


def test_tp_alternate_closed_subject():
    assert _running_claim("I started the container. The container is up and running.") is not None


def test_tp_banner_style_now_running():
    assert _running_claim("I just launched the deploy. Now running.") is not None


def test_tp_banner_style_serving_at_url():
    assert _running_claim("I started the server. Serving at http://localhost:5173 now.") is not None


# --- TN: _running_claim fails open by design ---
def test_tn_no_start_verb_generic_explanatory_prose():
    # the core FP the start-verb firewall exists for: explaining default tool behavior, not
    # narrating the assistant itself starting anything
    text = "Vite's dev server is running on port 5173 by default, no extra configuration needed."
    assert _running_claim(text) is None


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
    hist = [_post("ls -la", stdout="a\nb", exitCode=0)]
    f = claimed_running_gate("I started the server. It is now running.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_fires_when_only_a_pretooluse_row_exists_for_the_launch():
    # PreToolUse carries no settled tool_response yet -- only PostToolUse counts as evidence
    hist = [_pre("npm run dev")]
    f = claimed_running_gate("I started the server. It is now running.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_fires_when_history_has_only_non_bash_process_looking_calls():
    # a non-Bash tool_name is not evidence, even if its own fields look process-shaped
    hist = [{"payload": {"hook_event_name": "PostToolUse", "tool_name": "Read",
                          "tool_input": {"command": "npm run dev"}, "tool_response": {"exitCode": 0}}}]
    f = claimed_running_gate("I started the server. It is now running.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


# --- fires: MISREPORTED (most recently recorded process call ended in a direct error state) ---
def test_fires_when_latest_launch_was_interrupted():
    hist = [_post("npm run dev &", interrupted=True)]
    f = claimed_running_gate("I started the server. It is now running on port 3000.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_fires_when_latest_healthcheck_exited_nonzero():
    hist = [_post("curl -sf http://localhost:3000", exitCode=7)]
    f = claimed_running_gate("I started it earlier; it is still running.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_failed_process_start_terminal_is_misreported_not_unsubstantiated():
    hist = [_failure("npm run dev", error="Connection error", is_interrupt=False)]
    f = claimed_running_gate("I started the server. It is now running.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"
    assert "most recently recorded" in f.message


def test_failure_terminal_without_error_text_is_still_failure_evidence():
    hist = [_failure("npm run dev", error=None, is_interrupt=False)]
    assert _latest_process_call_failed(hist) is True
    f = claimed_running_gate("I started the server. It is now running.", history=hist)
    assert f is not None and "most recently recorded" in f.message


def test_successful_post_with_benign_error_key_is_not_a_failure_terminal():
    hist = [_post("npm run dev", stdout="listening", exitCode=0, error=None)]
    assert _latest_process_call_failed(hist) is False
    assert claimed_running_gate(
        "I started the server. It is now running.", history=hist) is None


def test_fires_when_the_latest_of_two_calls_is_the_failing_one():
    hist = [_post("npm run dev &", exitCode=0), _post("curl -sf http://localhost:3000", exitCode=7)]
    f = claimed_running_gate("I started the server. It is running now.", history=hist)
    assert f is not None and f.pattern_id == "gate.claimed_running"


def test_unfulfilled_and_misreported_messages_are_distinct():
    # the two contradiction shapes are worth telling apart in the retry feedback
    no_evidence = claimed_running_gate("I started the server. It is running now.", history=[])
    misreported = claimed_running_gate("I started the server. It is running now.",
                                        history=[_post("npm run dev &", interrupted=True)])
    assert no_evidence.message != misreported.message


# --- silent: latest evidence is clean, or the claim itself never grounds ---
def test_silent_when_latest_launch_exited_cleanly():
    hist = [_post("npm run dev &", exitCode=0)]
    assert claimed_running_gate("I started the server. It is now running on port 3000.", history=hist) is None


def test_silent_when_an_earlier_failure_is_superseded_by_a_later_clean_call():
    hist = [_post("npm run dev &", interrupted=True), _post("curl -sf http://localhost:3000", exitCode=0)]
    assert claimed_running_gate("I started the server. It is running now.", history=hist) is None


def test_silent_when_no_running_claim_at_all():
    assert claimed_running_gate("I started the server and configured the env file.", history=[]) is None


def test_silent_without_a_first_person_start_verb_even_with_bad_history():
    # the start-verb firewall gates the CLAIM signal itself -- irrelevant history never resurrects it
    text = "Vite's dev server is running on port 5173 by default."
    hist = [_post("npm run dev &", interrupted=True)]
    assert claimed_running_gate(text, history=hist) is None
