"""Line-level pinning tests for gate.dropped's discharge logic — close the mutation-audit
survivors (scripts/audit_lines.py --module gates) that the happy-path unit tests leave un-pinned.

Each test names the (lineno, kind) survivor it kills and is constructed so the specific single-
token mutant (comparator swap / bool swap / if-negation / return-flip) flips this test's verdict.
A blocking gate whose discharge comparators are unpinned can drift its FP/FN rate with no test
reddening — exactly what makoto forbids. fs_exists/fs_size/fs_read are injected so the content-
depth branches (size, strip-empty, counter selection) are reachable without real files.

These tests + the unit tests + the live battery kill 82/94 dropped-path line-mutants
(scripts/audit_lines.py --module gates). The remaining 12 are ACCEPTED EQUIVALENT mutants —
they change no behavior on any input dropped_gate can actually receive (documented per the
audit_lines convention, line 143 "or document as equivalent/dead"):
  - _drop_discharged 671 [RETURN/CONST] `return True` (unknown-kind fail-open): `kind` is one of
    exactly {named_artifact, named_symbol, count, line_range} — the four _drop_extract emits — so
    this arm is unreachable.
  - _drop_extract_forward_claims 573 [RETURN] `return []` (empty-text guard): dropped_gate guards
    `if not text: return None` BEFORE calling, so _drop_extract is never reached with empty text.
  - _drop_touched 638 / _drop_discharged 659 [RETURN] `return False`->None: both falsy; the caller
    only branches on truthiness (`if discharged: continue`), so False and None are indistinguishable.
  - _drop_extract_forward_claims 609 [BOOL] artifact `.ext` re-check: `loc` reached here already
    matched _DROP_PATH (basename WITH extension), so the secondary `re.search(file.ext)` is always
    true — flipping the `or` changes nothing on a reachable `loc`.
  - _drop_discharged 645/648 [BOOL] `fs_read is not None and path` / `fs_size and path`: the live
    runner and every test always pass callable fs_read/fs_size and a truthy path, so the guard's
    short-circuit arm is never the deciding term.
  - _drop_extract_forward_claims 577 [CMP/BOOL/RETURN] span-overlap dedup: a perf/precedence
    optimization; on the gate's BINARY output (fire iff any claim undischarged) double-counting an
    overlapping span cannot change fire-vs-silent, so no input distinguishes the mutant.
"""
from makoto.stopchecks.stopcheck_dropped import dropped_gate
from makoto.checks import normalize_path


def _call(text, *, touched=(), empty=(), reads=None, exists=(), sizes=None):
    reads = reads or {}
    sizes = sizes or {}
    exists_set = {normalize_path(p) for p in exists}
    return dropped_gate(
        text, touched_keys=set(touched),
        fs_exists=lambda p: normalize_path(p) in exists_set,
        fs_size=lambda p: sizes.get(normalize_path(p)),
        fs_read=lambda p: reads.get(normalize_path(p)),
        empty_keys=set(empty),
    )


# --- _drop_discharged 651 [CMP/RETURN]: artifact content non-empty -> discharged --------------
def test_artifact_nonempty_content_discharges():
    # content present + non-empty -> silent. Mutant `> 0`->`<= 0` would FIRE here.
    assert _call("Let me create cfg.yaml", reads={"cfg.yaml": "data: 1\n"}) is None


def test_artifact_whitespace_only_content_fires():
    # content present but strips to empty -> NOT discharged -> fires. Pins `.strip()` + `> 0`.
    assert _call("Let me create cfg.yaml", reads={"cfg.yaml": "   \n\t "}) is not None


# --- _drop_discharged 653 [CMP/RETURN]: artifact on-disk size != 0 -> discharged --------------
def test_artifact_no_content_but_exists_nonzero_size_discharges():
    # content None, file exists, size>0 -> silent. Mutant `!= 0`->`== 0` would FIRE here.
    assert _call("Let me create cfg.yaml", exists={"cfg.yaml"}, sizes={"cfg.yaml": 12}) is None


def test_artifact_exists_zero_size_fires():
    # exists but zero-byte -> NOT discharged -> fires. Pins `size != 0`.
    assert _call("Let me create cfg.yaml", exists={"cfg.yaml"}, sizes={"cfg.yaml": 0}) is not None


# --- _drop_touched 636 [BOOL]: a touch in empty_keys (zero-byte write) does NOT discharge -----
def test_artifact_touched_but_empty_write_fires():
    # touched the file, but the write produced zero substance (empty_keys) -> a hollow touch is
    # not a real create -> fires. Mutant dropping `and ... not in empties` would go SILENT.
    assert _call("Let me create cfg.yaml", touched={"cfg.yaml"}, empty={"cfg.yaml"}) is not None


def test_artifact_touched_nonempty_discharges():
    # the matched silent case: a real (non-empty) touch discharges.
    assert _call("Let me create cfg.yaml", touched={"cfg.yaml"}) is None


# --- _drop_discharged 660 [BOOL/CMP]: counter selection test-vs-def across the threshold -------
def test_count_tests_uses_test_counter_not_def_counter():
    # "write 3 tests" with 2 test-defs + 2 helper-defs: test-counter=2 (<3) -> FIRES.
    # Mutant selecting the def-counter would see 4 (>=3) -> SILENT -> reddens.
    body = ("def test_a():\n    pass\ndef test_b():\n    pass\n"
            "def helper_one():\n    pass\ndef helper_two():\n    pass\n")
    assert _call("I will write 3 tests in t.py", reads={"t.py": body}) is not None


# --- _drop_discharged 662 [BOOL/CMP/NOT]: test-counter==0 falls back to def-counter -----------
def test_count_tests_zero_test_defs_falls_back_to_def_counter():
    # "write 2 tests" but the file has 2 NON-test defs (setup/teardown), 0 `def test*`:
    # test-counter=0 -> fallback to def-counter=2 (>=2) -> discharged -> SILENT.
    # Mutant `found == 0`->`found != 0` skips the fallback -> found stays 0 (<2) -> FIRES -> reddens.
    body = "def setup():\n    pass\ndef teardown():\n    pass\n"
    assert _call("I will write 2 tests in t.py", reads={"t.py": body}) is None


# --- _drop_resolve_location 626/627 [NOT/RETURN]: resolve a bare path via a touched suffix -----
def test_symbol_resolves_via_touched_suffix_for_content_read():
    # claim names utils.py; the touched key is the deeper pkg/utils.py holding the def. Discharge
    # needs resolve to suffix-match so fs_read hits the right path -> silent. Mutant negating the
    # suffix-match (or flipping the return) fails to resolve -> reads None -> FIRES -> reddens.
    body = "def foo():\n    return 1\n"
    assert _call("I will add def foo to utils.py",
                 touched={"pkg/utils.py"}, reads={"pkg/utils.py": body}) is None


# --- dropped_gate 690/692/694 [CMP/NOT]: the fire message names the right claim kind -----------
def test_fire_message_count_names_the_count():
    f = _call("I will add 3 helper functions to utils.py")
    assert f is not None and "claimed 3" in f.message


def test_fire_message_line_range_names_the_lines():
    f = _call("I will edit lines 10-20 of parser.py")
    assert f is not None and "lines 10-20" in f.message


def test_fire_message_named_symbol_names_the_symbol():
    f = _call("I will add def validate_seal to gates.py")
    assert f is not None and "validate_seal" in f.message and "define" in f.message


# --- _drop_extract_forward_claims 587 [CMP/NOT]: a reversed line-range normalizes lo<=hi -------
def test_reversed_line_range_normalizes_in_message():
    # "lines 20-10" must report "lines 10-20". Mutant flipping `hi < lo` swaps (or never swaps),
    # producing "lines 20-10" -> message assertion reddens.
    f = _call("I will edit lines 20-10 of parser.py")
    assert f is not None and "lines 10-20" in f.message


# --- _drop_extract_forward_claims 592 [BOOL]: a count claim with NO location is not extracted --
def test_count_without_location_is_silent():
    # "add 3 functions" carries no path -> not a located claim -> never extracts -> silent.
    # Mutant dropping the `not m.group('loc')` guard would extract+fire -> reddens.
    assert _call("I will add 3 functions to make it faster") is None


# --- _drop_extract_forward_claims 584 [BOOL]: a line-range claim with NO location is silent -----
def test_line_range_without_location_is_silent():
    assert _call("I will edit lines 10-20 to clean it up") is None


# --- _drop_extract_forward_claims 609 [BOOL]: an artifact surface must look like file.ext -------
def test_artifact_without_extension_is_silent():
    # "create thewidget" has no .ext -> not a named artifact -> silent. Mutant dropping the
    # `re.search(file.ext)` guard would treat the bare word as an artifact and fire -> reddens.
    assert _call("Let me create thewidget for the page") is None


# --- _drop_extract_forward_claims 600 [BOOL]: a NEGATED symbol frame stays silent --------------
def test_negated_symbol_frame_is_silent():
    # "won't add" is not a forward frame -> never extracts (pins frame-matching, not _negated).
    assert _call("I won't add def legacy_shim to gates.py — it is not needed") is None


def test_symbol_with_preceding_negation_is_silent():
    # a REAL forward frame ("let me add def ...") whose preceding context negates it ("instead of")
    # -> _negated() skips it. Pins _drop_extract 600 [BOOL]: mutant `or`->`and` would un-skip and
    # fire. The conservative FP-avoiding read (the agent committed to the alternative, not this).
    assert _call("Instead of patching it, let me add def foo_shim to bar_zzz.py") is None


# --- _drop_discharged 669 [CMP/RETURN]: line_range content non-empty -> discharged -------------
def test_line_range_nonempty_content_discharges():
    # a line-range claim whose file (no touch) has non-empty content -> silent. Mutant `> 0`->`<= 0`
    # would FIRE. Distinct branch from the artifact case (651) — same logic, different kind.
    assert _call("I will edit lines 10-20 of parser.py", reads={"parser.py": "code()\n"}) is None


def test_line_range_whitespace_content_fires():
    # content strips to empty -> NOT discharged -> fires. Pins the line_range strip+`> 0`.
    assert _call("I will edit lines 10-20 of parser.py", reads={"parser.py": "   \n"}) is not None


# --- _drop_discharged 670 [CMP/RETURN]: line_range on-disk exists + size != 0 -> discharged ----
def test_line_range_exists_nonzero_size_discharges():
    # content None, file exists with size>0 -> silent. Mutant `!= 0`->`== 0` would FIRE.
    assert _call("I will edit lines 10-20 of parser.py",
                 exists={"parser.py"}, sizes={"parser.py": 40}) is None


def test_line_range_exists_zero_size_fires():
    assert _call("I will edit lines 10-20 of parser.py",
                 exists={"parser.py"}, sizes={"parser.py": 0}) is not None


# --- _drop_discharged: conventional-empty (_EMPTY_OK) discharge (consolidation T2.4) -----------
def test_conventional_empty_init_on_disk_discharges():
    # "I'll create pkg/__init__.py" + the file exists at size 0: emptiness IS the deliverable
    # (mirrors _common._discharged's _EMPTY_OK rule). FIRED before the T2.4 fix (live-probed).
    assert _call("I'll create pkg/__init__.py to make it a package.",
                 exists={"pkg/__init__.py"}, sizes={"pkg/__init__.py": 0}) is None


def test_conventional_empty_touched_empty_write_discharges():
    # a recorded zero-byte Write of __init__.py discharges: the empty Write IS the work.
    assert _call("I'll create pkg/__init__.py to make it a package.",
                 touched={"pkg/__init__.py"}, empty={"pkg/__init__.py"}) is None


def test_nonconventional_empty_still_fires():
    # the fix must NOT widen: an empty notes.py is still an undischarged production claim.
    assert _call("I'll create notes.py with the summary.",
                 exists={"notes.py"}, sizes={"notes.py": 0}) is not None


def test_line_range_conventional_empty_discharges():
    # line_range arm: a claimed edit to a conventional-empty file discharges on exists+size0.
    assert _call("I will edit lines 1-2 of pkg/__init__.py",
                 exists={"pkg/__init__.py"}, sizes={"pkg/__init__.py": 0}) is None
