"""lexicons.py (L0) is the sole home for makoto's regexes + word-sets. Pins IDENTITY (each RX is
the SAME compiled object gates/retraction/citations use) and L0 purity (no in-package imports). The
identity assertions on the high-escape patterns (_TEST_RUNNER_RX, _ADMIT_CORE_RX, etc.) catch a
transcription drift as a unit failure, not only via corpus-FP after the fact."""
import ast
import re
from pathlib import Path


def test_lexicons_exports_all_regex_symbols():
    from makoto import lexicons
    for name in (
        "_DONE_WORDS_RX", "_NEGATION_RX", "_MAKOTO_ALLOW_RX", "JWT_CALLEE_RX",
        "_TEST_RUNNER_RX", "_FAILURE_SUMMARY_RX", "_FAILURE_MARKER_RX",
        "_ADMIT_CORE_RX", "_FORWARD_YET_RX", "_FORWARD_FUTURE_RX", "_ASIDE_RX",
        "_USER_CONCESSION_RX", "_SUCCESS_WORDS_RX", "_UNIVERSAL_RX",
        "_ENUMERATION_RX", "_CITATION_RX",
    ):
        assert isinstance(getattr(lexicons, name), re.Pattern), name
    assert isinstance(lexicons._CITATION_AUTHOR_STOPWORDS, frozenset)


def test_lexicons_is_L0_no_inpackage_imports():
    src = Path(__file__).resolve().parent.parent / "lexicons.py"
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("makoto"), f"L0 must not import makoto.*: {node.module}"
        if isinstance(node, ast.Import):
            for a in node.names:
                assert not a.name.startswith("makoto"), f"L0 must not import makoto.*: {a.name}"


def test_primitives_reuse_the_same_lexicon_objects():
    from makoto import lexicons
    from makoto.lib import claims, io
    from makoto import citations
    # identity: one edit governs every surface — each L1 primitive reuses the L0 lexicon object,
    # never a private re-compile. Covers the homes the dissolved predicates.helpers split into.
    assert claims._NEGATION_RX is lexicons._NEGATION_RX
    assert io._TEST_RUNNER_RX is lexicons._TEST_RUNNER_RX
    assert citations._CITATION_AUTHOR_STOPWORDS is lexicons._CITATION_AUTHOR_STOPWORDS
    assert citations._CITATION_RX is lexicons._CITATION_RX


def test_gate_and_retraction_lexicons_live_in_lexicons():
    """StopCheck + retraction regexes/word-sets are L0 vocabulary in lexicons.py (spec §3b row 5)."""
    import re
    from makoto import lexicons as L
    assert L._PRODUCE_VERB_RX.search("I wrote the file")
    assert L._UNIVERSAL_DONE_RX.search("everything is done.")
    assert L._GREEN_CLAIM_RX.search("tests pass")
    assert "the" in L._GREEN_UNIVERSAL_PREMOD and "__init__.py" in L._EMPTY_OK
    assert L._RETRACT_VERB_RX.search("skipping it")
    assert L._RETRACT_REASON_RX.search("for now")
    assert isinstance(L._RETRACT_POST_RX, re.Pattern)


def test_fence_span_rx_is_the_single_source_for_fenced_spans():
    # dedup U2: the ```fenced``` span regex (DOTALL triple-backtick block) lives in exactly ONE place;
    # lib.claims._code_spans and retraction._fenced_spans both consume THIS object (identity), so the
    # byte-identical `re.finditer(r"```.*?```", ..., re.DOTALL)` re-inline at lib/claims.py + retraction.py:63
    # is gone. Identity (not equality) is the re-checkable single-source artifact.
    from makoto import lexicons, retraction
    from makoto.lib import claims
    text = "before ```done\ncode``` mid ```x``` end"
    spans = [(m.start(), m.end()) for m in lexicons._FENCE_SPAN_RX.finditer(text)]
    assert [text[a:b] for a, b in spans] == ["```done\ncode```", "```x```"]   # DOTALL: span crosses newline
    assert claims._FENCE_SPAN_RX is lexicons._FENCE_SPAN_RX
    assert retraction._FENCE_SPAN_RX is lexicons._FENCE_SPAN_RX


def test_integ_vocab_is_the_single_source_for_the_integrity_wordset():
    # dedup U3: the integrity/audit/verification alternation lives in exactly ONE place. pattern_1_4
    # (suppression-flag KEY) and pattern_1_2 (env-gated audit body/key) BOTH consume lexicons._INTEG_VOCAB
    # (identity), so the byte-identical `audit|verif|integrit|...` alternation is not re-declared per
    # detector. It is a raw alternation STRING (each consumer anchors it differently), not a PreCheck.
    from makoto import lexicons
    from makoto.prechecks import precheck_1_4, precheck_1_2
    assert isinstance(lexicons._INTEG_VOCAB, str)
    assert "audit" in lexicons._INTEG_VOCAB and "provenance" in lexicons._INTEG_VOCAB
    assert precheck_1_4._INTEG is lexicons._INTEG_VOCAB        # p14._INTEG stays the L0 object
    assert precheck_1_2._INTEG_VOCAB is lexicons._INTEG_VOCAB  # 1.2 consumes the same source, no second copy
