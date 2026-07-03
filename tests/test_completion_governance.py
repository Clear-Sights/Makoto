"""Direct-call governance probe for completion_gate's production-claim detector.

These are DIRECT gate-function calls only (no dispatch / no run_stop_checks). They pin the
verb-governs-the-located-path-as-direct-object rule: a produce verb whose direct object is a
DIFFERENT noun ("the logic", "the handler") and whose located path sits across a subordinator /
read-frame ("so … config.yaml", "to read from settings.json") is an inert REFERENCE, not a
self-production claim — it must stay silent. A genuine production claim ("I wrote config.yaml")
must still fire.
"""
from makoto.stopchecks.stopcheck_completion import completion_gate


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
