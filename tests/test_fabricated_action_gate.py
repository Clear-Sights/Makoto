"""gate.fabricated_action — the assistant claims a completed TOOL action ("I ran `X`") in a turn where
it made NO tool calls. FP-safe by design: a closed tool-verb lexicon (reasoning verbs excluded), a
DISTINCTIVE object (backticked/path/url — bare words rejected), negation/future/quoted guards, and
discharge on ANY tool activity this turn (presence-of-work, NOT command-text matching — so it is
immune to command paraphrase and to invisible Workflow/Agent/Task tools). Signal half pinned too."""
import json

from makoto.stopchecks.stopcheck_fabricated_action import _action_signal, fabricated_action_gate


def _tool_call(name="Bash", cmd="x"):
    # one PreToolUse event this turn, production events-table row shape (id, ts, event_type, cwd, payload)
    return (1, "t", "PreToolUse", "/r", json.dumps({
        "tool_name": name, "tool_input": {"command": cmd}, "tool_response": {"stdout": "ok"}}))


def _stop():
    return (2, "t", "Stop", "/r", "{}")


# --- discharge / gate behavior (presence-of-work) ---
def test_fires_when_no_tool_calls_this_turn():
    f = fabricated_action_gate("I ran `pytest tests/ -q`.", history=[])
    assert f is not None and f.pattern_id == "gate.fabricated_action"


def test_silent_when_a_tool_call_happened_this_turn():
    # even a DIFFERENT command discharges — the claim is backed by real tool work, paraphrase aside
    assert fabricated_action_gate("I ran `pytest tests/ -q`.",
                                  history=[_tool_call(cmd="python -m pytest tests/ -q --tb=short")]) is None


def test_silent_when_invisible_tool_ran_this_turn():
    # a Workflow launch carries no Bash command but IS a PreToolUse event -> discharges (no false fire)
    assert fabricated_action_gate("I launched `wf_abc123`.",
                                  history=[_tool_call(name="Workflow", cmd="")]) is None


def test_fires_when_tool_work_was_only_a_PRIOR_turn():
    # a tool call last turn, then a Stop boundary, then a tool-less turn that claims an action -> fires
    hist = [_tool_call(), _stop()]
    f = fabricated_action_gate("I ran `pytest tests/ -q`.", history=hist)
    assert f is not None and f.pattern_id == "gate.fabricated_action"


def test_silent_when_no_claim():
    assert fabricated_action_gate("I verified the logic.", history=[]) is None


# --- PRIOR-TURN recap (seed FP) — a truthful recap of an earlier turn on a summary turn ---
def test_silent_on_prior_turn_recap_summary_turn():
    """Seed FP: a tool-less summary turn that recaps work done EARLIER. turn_tool_calls counts only
    this turn, so the truthful recap read as fabricated. The prior-turn frame fails open."""
    assert fabricated_action_gate(
        "Earlier this session I ran scripts/validate.sh and it passed; this turn I'm just summarizing.",
        history=[]) is None


def test_silent_on_trailing_prior_turn_frame():
    """The frame can trail the verb too ('I ran X previously')."""
    assert fabricated_action_gate("I ran scripts/validate.sh previously.", history=[]) is None


def test_TP_intact_present_turn_claim_zero_tool_calls_fires():
    """The real TP MUST still fire: a present-turn 'I ran X' with zero tool calls this turn and NO
    prior-turn frame."""
    f = fabricated_action_gate("I ran scripts/deploy.sh and it succeeded.", history=[])
    assert f is not None and f.pattern_id == "gate.fabricated_action"


# --- TP: a concrete tool-action claim yields its object ---
def test_tp_ran_backticked_command():
    assert _action_signal("I ran `pytest tests/ -q`.") == "pytest tests/ -q"


def test_tp_ran_path():
    assert _action_signal("I executed scripts/deploy.sh against staging.") == "scripts/deploy.sh"


# --- TN: not a tool-action claim -> silent ---
def test_tn_reasoning_verb():
    assert _action_signal("I verified the logic is correct.") is None


def test_tn_future():
    assert _action_signal("I will run the migration.") is None


def test_tn_negation():
    assert _action_signal("I did not run the suite.") is None


def test_tn_quoted_prose_object():
    # 'I ran X' inside prose with a bare non-distinctive object -> not a fire (X is not backticked/path/url)
    assert _action_signal("the doc says I ran X earlier.") is None


def test_tn_bare_verb_no_distinctive_object():
    # "I ran tests" — bare word object, no backtick/path/url -> too FP-prone, silent
    assert _action_signal("I ran tests and it was fine.") is None


def test_tn_future_word_preceding_the_claim_is_suppressed():
    # the _NEG/_FUTURE guard inspects the 24 chars BEFORE the "I <verb>" match: a future framing
    # there suppresses the claim. Pins the OR guard's future arm (kills the L45 or->and mutant).
    assert _action_signal("Let me check, I ran `setup.py`.") is None


def test_tn_negation_word_preceding_the_claim_is_suppressed():
    # the negation arm of the same guard: a "not ... I ran `x`" framing is not a completed action.
    assert _action_signal("It's not true that I ran `deploy.sh`.") is None
