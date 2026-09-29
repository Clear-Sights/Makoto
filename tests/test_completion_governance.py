"""Direct-call governance probe for completion_gate's production-claim detector.

These are DIRECT gate-function calls only (no dispatch / no run_stop_checks). They pin the
verb-governs-the-located-path-as-direct-object rule: a produce verb whose direct object is a
DIFFERENT noun ("the logic", "the handler") and whose located path sits across a subordinator /
read-frame ("so … config.yaml", "to read from settings.json") is an inert REFERENCE, not a
self-production claim — it must stay silent. A genuine production claim ("I wrote config.yaml")
must still fire.
"""
from makoto.checks.otherPoint import completion_gate


def _fires(text):
    return completion_gate(text, touched_keys=set(), fs_exists=lambda p: False) is not None


# --- FP (referenced read-source path, not authored) MUST stay silent ----------------------
REFERENCED_INERT = [
    # verb governs "the logic"; config.yaml is a constraint across "so … matches what"
    "I updated the logic so the output now matches what config.yaml's schema requires.",
    # verb governs "the handler"; settings.json is a read source across "to read from"
    "I wrote the handler to read from settings.json at startup.",
    "I built the parser to conform to grammar.bnf.",
    "I updated the resolver according to spec.md.",
]


# --- TP (genuine self-production claim) MUST still fire ------------------------------------
PRODUCED_FIRES = [
    "I wrote config.yaml",
    "I created handler.py",
    "I wrote `config.yaml`",
    "Wrote handler.py",
    "I created the file src/auth.py",
    "I added a new module utils.py",
]


def test_referenced_read_source_paths_stay_inert():
    fired = [t for t in REFERENCED_INERT if _fires(t)]
    assert not fired, f"FP regression — referenced-path claims fired: {fired}"


def test_genuine_production_claims_still_fire():
    silent = [t for t in PRODUCED_FIRES if not _fires(t)]
    assert not silent, f"TP regression — genuine production claims went silent: {silent}"


# --- FP (live, coordinator session 2026-09-29): a path named as NOT yet produced ------------
# Each disowns production: a negated subject, a not-yet, a future frame, a retraction, or a
# participle used as an adjective after a determiner ("the finished X" names X, it claims nothing).
DISOWNED_INERT = [
    "nothing has produced the finished session.sh yet, and I haven't written one either.",
    "Nobody has created handler.py so far.",
    "No session has written config.yaml yet.",
    "I don't have the finished session.sh yet. It will then reply there with the finished session.sh attached.",
    "Launch rows is building the finished session.sh and will post it here.",
    "The thread will attach the generated report.md when it lands.",
    "Correction: I have not written session.sh; nothing produced it.",
    "Launch rows posted the finished session.sh in its thread.",
]

DISOWN_GUARD_FIRES = [
    "I finished session.sh.",
    "I have produced the finished session.sh.",
    "I created handler.py, yet two tests still fail.",
    "Nothing is left. I wrote config.yaml.",
    "No surprises: I wrote config.yaml.",
    "Nothing broke, so I committed fix.py.",
    "None of the old files survived; I created handler.py.",
]


def test_a_path_named_as_not_yet_produced_stays_inert():
    fired = [t for t in DISOWNED_INERT if _fires(t)]
    assert fired == [], fired


def test_the_disowning_frames_do_not_silence_a_real_claim():
    missed = [t for t in DISOWN_GUARD_FIRES if not _fires(t)]
    assert missed == [], missed


# --- FN (found 2026-09-29): a negation in an EARLIER clause disarmed a live claim -----------
# The negation must govern the claim verb's own clause; a conjunction that opens a new clause
# with its own subject (", and I", "and we", "but") ends the negation's reach.
EARLIER_CLAUSE_NEGATION_FIRES = [
    "Nothing failed, and I wrote config.yaml.",
    "Tests didn't fail and I created handler.py.",
    "I couldn't reproduce it, so I wrote repro.py.",
    "Nothing broke but I committed fix.py.",
    "It never crashed, yet I patched loader.py anyway.",
]

SAME_CLAUSE_NEGATION_INERT = [
    "I haven't written and committed session.sh.",
    "I did not, in the end, create handler.py.",
    "I didn't create handler.py.",
    "We never wrote or committed config.yaml.",
]


def test_a_negation_in_an_earlier_clause_does_not_disarm_the_claim():
    missed = [t for t in EARLIER_CLAUSE_NEGATION_FIRES if not _fires(t)]
    assert missed == [], missed


def test_a_negation_in_the_claims_own_clause_still_disowns_it():
    fired = [t for t in SAME_CLAUSE_NEGATION_INERT if _fires(t)]
    assert fired == [], fired
