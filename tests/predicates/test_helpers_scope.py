from makoto.substrate.claims import claims_success

def _stop(text): return {"hook_event_name": "Stop", "last_assistant_message": text}

def test_success_lexicon_matches_synonyms_beyond_done():
    for w in ("shipped", "all green", "fully optimal", "the full ablation", "everything verified"):
        assert claims_success(_stop(f"I {w} now.")) is not None, w

def test_success_lexicon_respects_negation_window():
    assert claims_success(_stop("I have not fully finished.")) is None
