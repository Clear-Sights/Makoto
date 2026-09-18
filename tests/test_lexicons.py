"""lexicons.py (L0) is the sole home for makoto's regexes + word-sets. Pins single-sourcing (each
RX reaches its consumer by import, never by a private re-compile) and L0 purity (no in-package
imports). The pins on the high-escape patterns (_TEST_RUNNER_RX, _ADMIT_CORE_RX, etc.) catch a
transcription drift as a unit failure, not only via corpus-FP after the fact.

`is` ALONE CANNOT CARRY THAT CLAIM, measured 2026-09-18 and the reason `_no_local_rebind` exists:
`re.compile` memoizes on (pattern, flags), so a consumer that re-inlines the identical
`re.compile(r"```.*?```", re.DOTALL)` gets back the very object vocab.py compiled and every `is`
assertion here stays green. A plant that gave substrate/claims.py its own byte-identical copy of
_FENCE_SPAN_RX passed this file untouched. `is` still catches a DRIFTED copy, so it is kept; the
AST check below catches the byte-identical one, which is what the dedup campaign was about. The
cache is also bounded and `re.purge()`-able, so identity here was never load-bearing in either
direction."""
import ast
import re
from pathlib import Path


def _no_local_rebind(module, *names):
    """Assert `module`'s own source never assigns `names` at module level -- so the symbol can
    only have reached it by import. This is the half `is` cannot check: see this file's docstring
    on re.compile's memoization."""
    src = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    assigned = set()
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        for t in targets:
            if isinstance(t, ast.Name):
                assigned.add(t.id)
    for name in names:
        assert name not in assigned, (
            f"{module.__name__} assigns {name} itself -- it must import it from makoto.vocab, "
            f"and `is` cannot catch a byte-identical re-compile")


def test_lexicons_exports_all_regex_symbols():
    from makoto import vocab as lexicons
    for name in (
        "_NEGATION_RX", "_MAKOTO_ALLOW_RX", "JWT_CALLEE_RX",
        "_TEST_RUNNER_RX", "_FAILURE_SUMMARY_RX", "_SUCCESS_SUMMARY_RX", "_FAILURE_MARKER_RX",
        "_ADMIT_CORE_RX", "_FORWARD_YET_RX", "_FORWARD_FUTURE_RX", "_ASIDE_RX",
        "_USER_CONCESSION_RX", "_UNIVERSAL_RX",
        "_ENUMERATION_RX", "_CITATION_RX",
    ):
        assert isinstance(getattr(lexicons, name), re.Pattern), name
    assert isinstance(lexicons._CITATION_AUTHOR_STOPWORDS, frozenset)


def test_lexicons_is_L0_no_inpackage_imports():
    src = Path(__file__).resolve().parent.parent / "plugin" / "makoto" / "vocab.py"
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("makoto"), f"L0 must not import makoto.*: {node.module}"
        if isinstance(node, ast.Import):
            for a in node.names:
                assert not a.name.startswith("makoto"), f"L0 must not import makoto.*: {a.name}"


def test_primitives_reuse_the_same_lexicon_objects():
    from makoto import vocab as lexicons
    from makoto import kit as io
    from makoto.substrate import claims
    from makoto.state import citations
    # identity: one edit governs every surface — each L1 primitive reuses the L0 lexicon object,
    # never a private re-compile. Covers the homes the dissolved predicates.helpers split into.
    assert claims._NEGATION_RX is lexicons._NEGATION_RX
    assert io._TEST_RUNNER_RX is lexicons._TEST_RUNNER_RX
    assert citations._CITATION_AUTHOR_STOPWORDS is lexicons._CITATION_AUTHOR_STOPWORDS
    assert citations._CITATION_RX is lexicons._CITATION_RX
    _no_local_rebind(claims, "_NEGATION_RX")
    _no_local_rebind(io, "_TEST_RUNNER_RX")
    _no_local_rebind(citations, "_CITATION_AUTHOR_STOPWORDS", "_CITATION_RX")


def test_gate_lexicons_live_in_lexicons():
    """StopCheck regexes/word-sets are L0 vocabulary in lexicons.py (spec §3b row 5). The
    retraction half of this test went with the retraction vocabulary itself (2026-09-18): its
    only reader was state/commitments.py, which was cut once nothing read GateContext.opens."""
    from makoto import vocab as L
    assert L._PRODUCE_VERB_RX.search("I wrote the file")
    assert L._UNIVERSAL_DONE_RX.search("everything is done.")
    assert L._GREEN_CLAIM_RX.search("tests pass")
    assert "the" in L._GREEN_UNIVERSAL_PREMOD and "__init__.py" in L._EMPTY_OK


def test_fence_span_rx_is_the_single_source_for_fenced_spans():
    # dedup U2: the ```fenced``` span regex (DOTALL triple-backtick block) lives in exactly ONE
    # place; substrate.claims._code_spans consumes it by import, so the byte-identical
    # `re.finditer(r"```.*?```", ..., re.DOTALL)` re-inline at lib/claims.py is gone. It had a
    # second consumer, state/commitments.py::_fenced_spans, until that store was cut 2026-09-18.
    from makoto import vocab as lexicons
    from makoto.substrate import claims
    text = "before ```done\ncode``` mid ```x``` end"
    spans = [(m.start(), m.end()) for m in lexicons._FENCE_SPAN_RX.finditer(text)]
    assert [text[a:b] for a, b in spans] == ["```done\ncode```", "```x```"]   # DOTALL: span crosses newline
    assert claims._FENCE_SPAN_RX is lexicons._FENCE_SPAN_RX
    _no_local_rebind(claims, "_FENCE_SPAN_RX")


def test_integ_vocab_is_the_single_source_for_the_integrity_wordset():
    # dedup U3: the integrity/audit/verification alternation lives in exactly ONE place. pattern_1_4
    # (suppression-flag KEY) and pattern_1_2 (env-gated audit body/key) BOTH consume lexicons._INTEG_VOCAB
    # (identity), so the byte-identical `audit|verif|integrit|...` alternation is not re-declared per
    # detector. It is a raw alternation STRING (each consumer anchors it differently), not a PreCheck.
    from makoto import vocab as lexicons
    from makoto.checks import integritySuppressionFlag, envGatedAudit
    assert isinstance(lexicons._INTEG_VOCAB, str)
    assert "audit" in lexicons._INTEG_VOCAB and "provenance" in lexicons._INTEG_VOCAB
    assert integritySuppressionFlag._INTEG is lexicons._INTEG_VOCAB        # p14._INTEG stays the L0 object
    assert envGatedAudit._INTEG_VOCAB is lexicons._INTEG_VOCAB  # content.env_gated_audit consumes the same source, no second copy


def test_the_recorded_verdict_parsers_are_one_object_under_every_spelling():
    """The EVIDENCE side of a named-test claim moved to its reachable home 2026-09-18 -- the
    recorded-marker parsers to `vocab` (rank 0) and the history walk over them to `kit` (rank 1)
    -- so three consumers reach them without a lateral check-to-check import and
    `kit.compute_delta` no longer needs a call-time back-edge into a named check module.

    `namedTestTeeth` still SPELLS them, because its own tests and this file address them there.
    That spelling must stay a re-export and never become a second copy: a plant that rebinds
    `recorded_failed_names` in the check module to a stub is exactly the drift the move exists to
    prevent, and nothing reddened on it until this pin existed. Identity, not equality -- two
    parsers that agree today are still two parsers.
    """
    from makoto import vocab as lexicons, kit
    from makoto.checks import namedTestTeeth as ntt
    for name in ("_TESTNAME_RX", "_REC_FAIL_LEAD_RX", "_REC_FAIL_TRAIL_RX", "_REC_PASS_LEAD_RX",
                 "_REC_PASS_TRAIL_RX", "_recorded_names", "recorded_failed_names",
                 "recorded_passed_names"):
        assert getattr(ntt, name) is getattr(lexicons, name), f"{name} is no longer one object"
    assert ntt.current_named_verdicts is kit.current_named_verdicts
    # ...and the new C12 gate reads the same objects rather than its own pair.
    from makoto.checks import unnamedFailure as uf
    assert uf._TESTNAME_RX is lexicons._TESTNAME_RX
    assert uf.current_named_verdicts is kit.current_named_verdicts
