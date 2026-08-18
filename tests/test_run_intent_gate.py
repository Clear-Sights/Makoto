"""gate.run_promised -- the forward-looking sibling of gate.claimed_running: the immediately
PRIOR turn's own message promised a first-person run-intent action ("I'll run the tests", "I'm
going to restart the server", "let me deploy this") but no Bash call appears anywhere in this
session's recorded history since -- the word must match the world, checked one turn later.
Stateless (no new persistence): the one-turn grace period falls out of `history` structurally
never containing the row for the Stop currently being evaluated, so a promise made THIS turn can
only ever be checked starting at the NEXT one. FP-safe by design: closed first-person-auxiliary +
closed process-lifecycle-verb lexicon (mirroring gate.claimed_running's own verb set), plus the
usual quoted/negated/question/idiom clause guards."""
import json

from makoto.checks.runIntentUnfulfilled import (
    run_promised_gate, _run_intent_claim, _last_stop_index, _bash_call_after,
)


def _stop(text, session_id="s1"):
    # one Stop-event row, corpus-replay dict-payload shape (matches
    # tests/test_stop_gate_level_invariant.py's _scenario_run_promised)
    return {"payload": {"hook_event_name": "Stop", "session_id": session_id,
                         "last_assistant_message": text}}


def _substop(text, session_id="s1"):
    return {"payload": {"hook_event_name": "SubagentStop", "session_id": session_id,
                         "last_assistant_message": text}}


def _post(cmd="pytest -q", tool_name="Bash", **response):
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": tool_name,
                         "tool_input": {"command": cmd}, "tool_response": response}}


def _pre(cmd="pytest -q"):
    return {"payload": {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": cmd}, "tool_response": {}}}


def _failure(cmd="pytest -q", *, error="Connection error", is_interrupt=False):
    return {"payload": {"hook_event_name": "PostToolUseFailure", "tool_name": "Bash",
                         "tool_input": {"command": cmd}, "error": error,
                         "is_interrupt": is_interrupt}}


def _wrapper_typed(event_type, **payload):
    """A production events-table row whose event type lives only on the wrapper column."""
    return (1, "ts", event_type, "/repo", json.dumps(payload))


# --- TP: _run_intent_claim recognizes the claim shape (every aux x every verb family) ---
def test_tp_going_to_run():
    assert _run_intent_claim("I'm going to run the tests now.") is not None


def test_tp_ill_run():
    assert _run_intent_claim("I'll run npm test.") is not None


def test_tp_let_me_run():
    assert _run_intent_claim("Let me run the build script.") is not None


def test_tp_i_will_run():
    assert _run_intent_claim("I will run this migration.") is not None


def test_tp_plan_to():
    assert _run_intent_claim("I plan to restart the server.") is not None


def test_tp_about_to():
    assert _run_intent_claim("I'm about to deploy the service.") is not None


def test_tp_launch():
    assert _run_intent_claim("I'll launch the container.") is not None


def test_tp_spin_up():
    assert _run_intent_claim("I'm going to spin up the daemon.") is not None


def test_tp_bring_up():
    assert _run_intent_claim("I'll bring up the api.") is not None


def test_tp_kick_off():
    assert _run_intent_claim("I'm going to kick off the job.") is not None


def test_tp_fire_up():
    assert _run_intent_claim("I'll fire up the worker.") is not None


def test_tp_stand_up():
    assert _run_intent_claim("I'm going to stand up the backend.") is not None


def test_tp_start_with_closed_object():
    assert _run_intent_claim("I'm going to start the server.") is not None


def test_tp_start_up_with_closed_object():
    assert _run_intent_claim("Let me start up the dev server.") is not None


def test_tp_filler_adverb_between_aux_and_verb():
    assert _run_intent_claim("I'll quickly restart the process.") is not None


def test_tp_returns_the_match_text():
    m = _run_intent_claim("I'll run the tests now.")
    assert m is not None and m.group(0) == "I'll run"


# --- TN: _run_intent_claim fails open by design ---
def test_tn_wrong_subject_and_verb_it_going_to_rain():
    # the canonical false-trigger this gate must never fire on: wrong subject (not first-person),
    # and 'rain' is nowhere in the closed verb set
    assert _run_intent_claim("it's going to rain today") is None


def test_tn_bare_start_without_a_closed_object():
    # 'start' alone is too overloaded for "begin any activity" -- only qualifies paired with a
    # closed process-object noun
    assert _run_intent_claim("I'm going to start writing the tests now") is None


def test_tn_run_by_you_idiom():
    assert _run_intent_claim("I'll run this by you first") is None


def test_tn_run_through_idiom():
    assert _run_intent_claim("Let me run through the test cases") is None


def test_tn_run_the_numbers_idiom():
    assert _run_intent_claim("I'm going to run the numbers real quick") is None


def test_tn_negated_never():
    assert _run_intent_claim("I'll never run that migration") is None


def test_tn_negated_not_going_to():
    assert _run_intent_claim("I'm not going to run the tests") is None


def test_tn_wont_is_not_will():
    assert _run_intent_claim("I won't run this") is None


def test_tn_hedge_probably_breaks_the_gap():
    # a hedge word in the aux-to-verb slot must break the match outright, not be swallowed as
    # filler -- a hedged statement is not a firm commitment
    assert _run_intent_claim("I'll probably run the tests") is None


def test_tn_be_running_is_not_the_infinitive():
    # 'I'll be running late' -- a common idiom unrelated to process execution; the gerund after
    # 'be' does not match the required bare-infinitive verb form
    assert _run_intent_claim("I'll be running late") is None


def test_tn_present_tense_state_claim_not_a_promise():
    assert _run_intent_claim("The tests are running now") is None


def test_tn_past_tense_not_a_forward_promise():
    assert _run_intent_claim("I started the server") is None


def test_tn_let_me_know_verb_not_in_closed_set():
    assert _run_intent_claim("Let me know if that works") is None


def test_tn_check_verb_not_in_closed_set():
    assert _run_intent_claim("I'll check the logs") is None


def test_tn_a_question_not_a_declarative_promise():
    assert _run_intent_claim("Should I run the tests?") is None


def test_tn_quoted_inside_backticks():
    text = "Docs example: `I'll run the tests` is the phrasing to detect."
    assert _run_intent_claim(text) is None


def test_tn_fenced_code_block():
    text = "```\nI'm going to run the migration\n```"
    assert _run_intent_claim(text) is None


def test_tn_empty_text():
    assert _run_intent_claim("") is None


# --- _last_stop_index: the position of the most recent Stop/SubagentStop row ---
def test_last_stop_index_none_when_absent():
    assert _last_stop_index([_post()]) is None


def test_last_stop_index_finds_the_only_stop():
    hist = [_post(), _stop("I'll run the tests now.")]
    assert _last_stop_index(hist) == 1


def test_last_stop_index_picks_the_latest_of_several():
    hist = [_stop("first"), _post(), _stop("second"), _post()]
    assert _last_stop_index(hist) == 2


def test_last_stop_index_counts_subagent_stop_too():
    hist = [_substop("I'll run the tests now.")]
    assert _last_stop_index(hist) == 0


def test_last_stop_index_sees_a_wrapper_typed_stop_row():
    hist = [_wrapper_typed(
        "Stop", session_id="s1", last_assistant_message="I'll run the tests now.")]
    assert _last_stop_index(hist) == 0


def test_last_stop_index_empty_history():
    assert _last_stop_index([]) is None


def test_last_stop_index_none_history():
    assert _last_stop_index(None) is None


# --- _bash_call_after: discharge-evidence scan ---
def test_bash_call_after_true_when_bash_follows():
    hist = [_stop("I'll run the tests now."), _post("pytest -q", exitCode=0)]
    assert _bash_call_after(hist, 0) is True


def test_bash_call_after_true_when_failed_bash_terminal_follows():
    hist = [_stop("I'll run the tests now."), _failure("pytest -q")]
    assert _bash_call_after(hist, 0) is True


def test_bash_call_after_sees_a_wrapper_typed_terminal_row():
    hist = [_stop("I'll run the tests now."), _wrapper_typed(
        "PostToolUse", tool_name="Bash", tool_input={"command": "pytest -q"},
        tool_response={"stdout": "1 passed", "exitCode": 0})]
    assert _bash_call_after(hist, 0) is True


def test_bash_call_after_false_when_nothing_follows():
    hist = [_stop("I'll run the tests now.")]
    assert _bash_call_after(hist, 0) is False


def test_bash_call_after_false_when_only_non_bash_follows():
    hist = [_stop("I'll run the tests now."),
            {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Read",
                          "tool_input": {}, "tool_response": {}}}]
    assert _bash_call_after(hist, 0) is False


def test_bash_call_after_false_when_only_pretooluse_follows():
    hist = [_stop("I'll run the tests now."), _pre("pytest -q")]
    assert _bash_call_after(hist, 0) is False


def test_bash_call_after_ignores_bash_calls_before_the_index():
    hist = [_post("pytest -q", exitCode=0), _stop("I'll run the tests now.")]
    assert _bash_call_after(hist, 1) is False


# --- run_promised_gate: end-to-end verdict ---
def test_fires_when_promise_has_no_bash_evidence_since():
    hist = [_stop("I'll run the tests now.")]
    f = run_promised_gate(history=hist)
    assert f is not None and f.pattern_id == "gate.run_promised"


def test_fires_citing_the_promised_text():
    hist = [_stop("I'll run the tests now.")]
    f = run_promised_gate(history=hist)
    assert f is not None and "I'll run" in f.message


def test_silent_when_no_stop_row_exists_yet():
    assert run_promised_gate(history=[_post()]) is None


def test_silent_when_prior_stop_made_no_promise():
    hist = [_stop("Here's a summary of what I found.")]
    assert run_promised_gate(history=hist) is None


def test_silent_when_a_bash_call_discharges_it():
    hist = [_stop("I'll run the tests now."), _post("pytest -q", exitCode=0)]
    assert run_promised_gate(history=hist) is None


def test_silent_when_wrapper_typed_bash_call_discharges_it():
    """ADR 0039 shape: wrapper-only event types must not make the gate false-fire."""
    hist = [_wrapper_typed(
                "Stop", session_id="s1", last_assistant_message="I'll run the tests now."),
            _wrapper_typed(
                "PostToolUse", tool_name="Bash", tool_input={"command": "pytest -q"},
                tool_response={"stdout": "1 passed", "exitCode": 0})]
    assert run_promised_gate(history=hist) is None


def test_silent_when_the_discharging_bash_call_failed():
    # discharge is "did anything run", not "did it succeed" -- a failed Bash call still proves the
    # word matched the world (something ran); a bad RESULT is a different gate's concern
    hist = [_stop("I'll run the tests now."), _post("pytest -q", exitCode=1)]
    assert run_promised_gate(history=hist) is None


def test_silent_when_the_discharging_bash_call_has_failure_terminal():
    hist = [_stop("I'll run the tests now."), _failure("pytest -q")]
    assert run_promised_gate(history=hist) is None


def test_fires_only_for_the_most_recent_prior_turn():
    # an OLDER promise, superseded by a more recent inert Stop, is not re-litigated -- only the
    # immediately prior turn is ever checked
    hist = [_stop("I'll run the tests now."), _stop("Here's a summary of what I found.")]
    assert run_promised_gate(history=hist) is None


def test_fires_again_across_a_second_unfulfilled_turn():
    # turn 1 promises with nothing said turn 2 either -- turn 2's own silence is itself
    # inspectable as "the prior turn" for a THIRD Stop's evaluation
    hist = [_stop("I'll run the tests now."), _stop("Still thinking about this.")]
    f = run_promised_gate(history=hist)
    assert f is None  # turn 2 made no promise of its own -- nothing for a hypothetical turn 3 to cite yet
    # (turn 1's own dropped promise was already the subject of turn 2's OWN evaluation, not re-derived here)


def test_silent_empty_history():
    assert run_promised_gate(history=[]) is None


def test_silent_none_history():
    assert run_promised_gate(history=None) is None
