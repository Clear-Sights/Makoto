"""Dedup campaign (ported from the stale public-repo branch's 6c633af/dd5c436/df23576):
drifted duplicate implementations collapsed to canonical definitions, each pinned two ways —
an IDENTITY assertion (the call sites share the same object, not a copy that happens to agree)
and a behavioral check on the shared primitive.

NOT ported: 94d4b73 (callee_chain unification into the factories module). The current layout
already addressed it differently: `kit.py` (rank 1) may not import `substrate._stdlib_ast_helpers`
(rank 2) under the pipeline-order firewall (tests/test_import_direction.py), and the duplication
is a REGISTERED exemption with its reason on record in
tests/test_no_alpha_duplicate_functions.py::_EXEMPT_PAIRS. Forcing the old port would violate
the firewall that superseded it.
"""
from __future__ import annotations

import json


# ---- 6c633af: one row-decode-plus-wrapper-fallback step (kit.decode_history_event) ------------
def test_decode_history_event_falls_back_to_the_wrapper_event_type():
    from makoto.kit import decode_history_event
    row = (1, "ts", "PostToolUse", "/repo",
           json.dumps({"tool_name": "Bash", "tool_input": {"command": "x"},
                       "tool_response": {"error_code": 1}}))
    assert decode_history_event(row)["hook_event_name"] == "PostToolUse"


def test_a_payloads_own_event_name_still_wins_over_the_wrapper():
    from makoto.kit import decode_history_event
    row = (1, "ts", "WrapperType", "/repo",
           json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                       "tool_input": {"command": "x"}}))
    assert decode_history_event(row)["hook_event_name"] == "PostToolUse"


def test_identical_retry_sees_a_wrapper_only_row_like_its_sibling():
    """The original drift: identicalRetryInterdiction's hand-rolled decoder read only the
    payload, so gate.identical_retry was BLIND to rows canon.timeout/canon.recur acted on,
    from the same table, for the same concept. Both now share kit.decode_history_event."""
    from makoto.checks.identicalRetryInterdiction import _most_recent_completed_bash_call
    from makoto.checks.canonTimeoutRecur import _decode_row as canon_decode
    row = (1, "ts", "PostToolUse", "/repo",
           json.dumps({"tool_name": "Bash", "tool_input": {"command": "x"},
                       "tool_response": {"stderr": "SyntaxError: bad", "exitCode": 1}}))
    assert canon_decode(row)[0] == "PostToolUse"
    assert _most_recent_completed_bash_call([row]) is not None


# ---- dd5c436: shared lexicon + pushed-branch extraction ---------------------------------------
def test_offer_and_first_person_regexes_are_the_one_vocab_object():
    from makoto.vocab import _OFFER_COND_RX, _FIRST_PERSON_RX
    from makoto.state import commitments, plan
    assert commitments._OFFER_COND_RX is _OFFER_COND_RX
    assert plan._OFFER_COND_RX is _OFFER_COND_RX
    assert commitments._FIRST_PERSON_RX is _FIRST_PERSON_RX
    assert plan._FIRST_PERSON_RX is _FIRST_PERSON_RX


def test_extract_pushed_branch_is_shared_and_strips_trailing_punctuation():
    from makoto.kit import extract_pushed_branch
    import makoto.checks.claimedShippedAbsent as csa
    assert csa.extract_pushed_branch is extract_pushed_branch
    assert extract_pushed_branch("pushed the work to `feat/x`,") == "feat/x"
    assert extract_pushed_branch("nothing of the sort") is None


def test_unsourced_webfetch_uses_the_canonical_row_unwrap():
    import makoto.checks.unsourcedWebfetch as uw
    from makoto.kit import raw_payload_str
    assert uw.raw_payload_str is raw_payload_str
