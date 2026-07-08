"""tests for the three gates + reconcile (retraction) and the commitments store.

Real-payload shapes (a located done-claim in last_assistant_message, an open
commitment un-windowed by session). Every blocking case has a matching silent case,
and the FP-guards are explicit: a bare done-word is inert, and a dropped ledger touch
fails open against the live filesystem so a real edit never false-blocks.
"""
import sqlite3

from makoto import commitments as C
from makoto.checks.undischargedCommitment import advance_gate
from makoto.checks.claimedProduceAbsent import completion_gate
from makoto.checks._shared import _discharged
from makoto.retraction import reconcile, detect_hidden_retraction


def _conn():
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.execute(
        "CREATE TABLE commitments (commitment_key TEXT PRIMARY KEY, session_id TEXT, "
        "location TEXT, qty_min REAL, qty_max REAL, status TEXT NOT NULL DEFAULT 'open', "
        "retract_param TEXT, created_event_id INTEGER, ts TEXT)")
    return c


# --- enter / sourcing (records, never blocks) ---------------------------------
def test_source_commitment_unlocated_inert_located_accepted():
    assert C.source_commitment("explore the cache") is None          # unlocated -> inert
    c = C.source_commitment("add rate-limit to `src/auth.py`")
    assert c and c["location"] == "src/auth.py"


def test_open_commitments_roundtrip_unwindowed_and_idempotent():
    conn = _conn()
    c = C.source_commitment("add rate-limit to `src/auth.py`")
    C.record_commitment(conn, "s", c, created_event_id=1)
    C.record_commitment(conn, "s", c, created_event_id=2)            # same promise -> no dup
    opens = C.open_commitments(conn, "s")
    assert len(opens) == 1 and opens[0]["location"] == "src/auth.py"


def test_set_status_discharges_commitment():
    conn = _conn()
    key = C.record_commitment(conn, "s", C.source_commitment("add x to `a/b.py`"),
                              created_event_id=1)
    C.set_status(conn, key, "discharged")
    assert C.open_commitments(conn, "s") == []


# --- completion gate -----------------------------------------------------------
def test_completion_bare_doneword_is_inert():
    # the verified 11.7% FP of the old chain pattern: a bare done-word must NOT fire.
    assert completion_gate("Done with the parts I can do", touched_keys=set()) is None


def test_completion_located_not_touched_bites():
    f = completion_gate("Done - added to src/auth.py", touched_keys=set())
    assert f is not None and f.file == "src/auth.py"


def test_completion_located_touched_is_silent():
    assert completion_gate("Done - added to src/auth.py",
                           touched_keys={"src/auth.py"}) is None


def test_completion_fails_open_when_filesystem_shows_it():
    # ledger dropped the touch, but the file exists on disk -> fail open (no FP).
    assert completion_gate("Done - added to src/auth.py", touched_keys=set(),
                           fs_exists=lambda p: p == "src/auth.py") is None


def test_completion_not_a_doneclaim_is_silent():
    assert completion_gate("I will add to src/auth.py next", touched_keys=set()) is None


# --- advance gate --------------------------------------------------------------
_OPEN = [{"location": "src/auth.py", "qty_min": None, "qty_max": None}]


def test_advance_no_signal_is_silent():
    assert advance_gate("still working on the parser", _OPEN, touched_keys=set()) is None


def test_advance_blocks_on_undischarged_commitment():
    # the TP: a UNIVERSAL completion claim ("everything is done") contradicted by a promised
    # path with no trace. This is the verifiable contradiction the gate exists to catch.
    f = advance_gate("Everything is done — all complete.", _OPEN, touched_keys=set())
    assert f is not None and f.file == "src/auth.py"


def test_advance_self_heals_from_filesystem():
    assert advance_gate("Everything is done — all complete.", _OPEN, touched_keys=set(),
                        fs_exists=lambda p: p == "src/auth.py") is None


def test_advance_discharged_by_ledger_is_silent():
    assert advance_gate("Everything is done — all complete.", _OPEN,
                        touched_keys={"src/auth.py"}) is None


# advance gate FP guards: the verifiable-contradiction fix. The advance signal is now an
# UNENUMERATED universal completion claim, NOT a bare phase-transition. These three near-
# misses are the FP surface that kept the gate FP-prone — each must stay inert even with an
# undischarged commitment open, because advancing past it there is legitimate triage, not a
# contradiction. Paired with the TP above, they pin the gate against both failure modes
# (suppress-to-zero turns the TP red; fire-on-everything turns these red).

def test_advance_bare_moving_on_is_inert():
    # a bare phase-transition makes NO completeness claim -> no contradiction (the removed FP)
    assert advance_gate("Moving on to the next phase.", _OPEN, touched_keys=set()) is None


def test_advance_scoped_done_is_inert():
    # "done with the parser" is SCOPED -> it does not claim the open auth commitment is done
    assert advance_gate("Done with the parser refactor.", _OPEN, touched_keys=set()) is None


def test_advance_negated_completion_is_inert():
    # honest admission of incompleteness must never fire (negation-guarded)
    assert advance_gate("Not everything is done yet, moving on.", _OPEN,
                        touched_keys=set()) is None


def test_advance_enumerated_completion_is_inert():
    # an ENUMERATED claim shows its scope ("all 5 of 5") -> bounded, not an unbounded
    # "everything"; advancing past an unrelated open commitment is not a contradiction
    assert advance_gate("All 5 of 5 tasks done.", _OPEN, touched_keys=set()) is None


# --- reconcile -----------------------------------------------------------------
def test_retract_subject_bound_clears_fakeexcuse_blocks():
    commit = {"location": "src/auth.py"}
    assert reconcile(commit, reason_result_at="src/auth.py",
                     recorded={"src/auth.py": {"exit": 1}}) == "cleared"
    # fakeexcuse.txt IS in `recorded`, but it does not subject-bind to the commitment.
    assert reconcile(commit, reason_result_at="fakeexcuse.txt",
                     recorded={"fakeexcuse.txt": {"exit": 0}}) == "blocked"


def test_forged_user_supersession_blocks_real_one_clears():
    commit = {"location": "src/auth.py"}
    assert reconcile(commit, user_claims=True, contract_changed=False) == "blocked"
    assert reconcile(commit, user_claims=True, contract_changed=True) == "cleared"


def test_hidden_retraction_flagged_vs_carry_forward():
    assert detect_hidden_retraction(dropped=True, reason=None) is True
    assert detect_hidden_retraction(dropped=False, reason=None) is False     # carried forward


# --- methodology arm: the subject-binding firewall must be EQUALITY ------------
def test_subject_binding_is_equality_not_substring():
    """If reconcile bound by substring instead of equality, fakeexcuse vectors would
    clear. Prove the firewall rejects a non-equal key even when it is 'contained'."""
    from makoto.checks import subject_binds
    assert subject_binds("src/auth.py", "src/auth.py") is True
    assert subject_binds("auth", "src/auth_helper.py") is False     # substring would WRONGLY bind


# --- _discharged: the empty-component suffix-match firewall guard (engine line 207) ---------
def test_discharged_empty_component_key_does_not_match():
    """_suffix_match's empty-list guard (`if not a_comps or not b_comps: return False`) keeps a
    key with no real path components ('~' alone) from suffix-matching ANY location. If that guard
    returned True instead, a bare-home touch would falsely discharge an open production claim and
    silence the gate. The committed path has real components; the only recorded touch is '~'."""
    assert _discharged("src/auth.py", {"~"}, None) is False         # '~' is not a touch of src/auth.py


# --- reconcile: an unverified retraction (no R, no U) stays blocked by DEFAULT (engine line 342)
def test_reconcile_unverified_retraction_defaults_blocked():
    """The default return is 'blocked': with NO recorded result (R) and NO user-supersession (U),
    a retraction is unverified and must not clear. If the default flipped to 'cleared', every
    hidden/unbacked retraction would silently pass the firewall."""
    assert reconcile({"location": "src/auth.py"}) == "blocked"
    # a user_claims with no contract change also stays blocked (not the default leg, but pins U)
    assert reconcile({"location": "src/auth.py"}, user_claims=True, contract_changed=False) == "blocked"


# --- completion gate: PRODUCTION-CLAIM BINDING (the 2026-06-01 measured-FP fix) ----------
# Fires only when a produce verb governs the path in ACTIVE voice, SAME clause, verb-before-
# path — "I created `X`". Inert on a mere mention, passive voice, an adjective false-match,
# a cross-clause verb, or a forward/negated frame. These near-misses are the FP guards that
# drove worst-case honest-corpus FP from 9.00% to a self-healing 2.42% without losing the TP.

def test_completion_unbacked_production_claim_bites():
    assert completion_gate("Done — I created src/auth.py.", touched_keys=set()) is not None
    f = completion_gate("Wrote the migration to db/migrations/0007.sql", touched_keys=set())
    assert f is not None and f.file == "db/migrations/0007.sql"

def test_completion_mere_path_mention_is_inert():
    # a path REFERENCED, with no produce verb governing it -> not a production claim
    assert completion_gate("Done reviewing. See src/auth.py for the details.",
                           touched_keys=set()) is None

def test_completion_passive_voice_is_inert():
    # "was written for X" describes the spec/another subject, not "I produced X"
    assert completion_gate("Done. The transport spec was written for src/http.py.",
                           touched_keys=set()) is None

def test_completion_built_in_adjective_is_inert():
    # 'built-in' must NOT match the produce verb 'built' (word-boundary fix)
    assert completion_gate("These are built-in; src/auth.py is unchanged.",
                           touched_keys=set()) is None

def test_completion_cross_clause_verb_is_inert():
    # the produce verb governs a different clause's noun ("deletions landed"), not the path
    assert completion_gate("The deletions landed; the docs/note.md change is still pending.",
                           touched_keys=set()) is None

def test_completion_negated_admission_is_inert():
    # an admission ("haven't written X") is 2.8's job, not a false completion claim
    assert completion_gate("I haven't written src/auth.py yet.", touched_keys=set()) is None

def test_completion_production_claim_self_heals_on_disk():
    # fail-open: a genuine production claim whose file exists on disk does NOT block
    assert completion_gate("Done — I created src/auth.py.", touched_keys=set(),
                           fs_exists=lambda p: p == "src/auth.py") is None


# --- source_commitment: FORWARD-PROMISE BINDING (advance gate's FP surface) ---------------

def test_source_commitment_requires_forward_promise():
    # a forward promise binds a path -> commitment
    c = C.source_commitment("I'll add rate limiting to `src/auth.py`")
    assert c and c["location"] == "src/auth.py"

def test_source_commitment_past_production_is_not_a_commitment():
    # "added X" is a completion (the completion gate owns it), never a forward commitment
    assert C.source_commitment("I added rate limiting to src/auth.py") is None

def test_source_commitment_bare_reference_is_inert():
    # a path merely referenced with no promise verb records no commitment (advance FP guard)
    assert C.source_commitment("See src/auth.py for the existing implementation.") is None


# --- line-falsifiability pins (audit_lines survivors the writer mis-closed; controller-verified) ---
def test_reconcile_reason_without_recorded_stays_blocked():
    # retraction.py `reason_result_at is not None AND recorded is not None`: a subject-bound reason
    # with recorded=None must NOT enter the R-branch. The `or` mutant would enter and evaluate
    # `reason_result_at in None`, crashing; the `and` keeps it blocked (fakeexcuse firewall).
    assert reconcile({"location": "src/auth.py"},
                     reason_result_at="src/auth.py", recorded=None) == "blocked"


def test_reconcile_user_claim_with_defaulted_contract_change_blocked():
    # retraction.py signature default `contract_changed=False`: a user claim with the contract-change
    # arg OMITTED stays blocked. Flipping the default to True would clear a forged supersession.
    assert reconcile({"location": "src/auth.py"}, user_claims=True) == "blocked"


def test_reconcile_contract_change_with_defaulted_user_claim_blocked():
    # retraction.py signature default `user_claims=False`: a contract change with the user-claim arg
    # OMITTED stays blocked. Flipping the default to True would clear with no user supersession.
    assert reconcile({"location": "src/auth.py"}, contract_changed=True) == "blocked"


def test_path_components_drops_home_tilde():
    # gates.py `if c and c != "~"`: the home '~' (and empty components) are dropped so a
    # '~/.claude/...' commitment suffix-discharges against an absolute write. The `or` mutant would
    # retain '~' (and empties), breaking the suffix match.
    from makoto.checks._shared import _path_components
    assert _path_components("~/a/b") == ["a", "b"]
