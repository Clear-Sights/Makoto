"""tests for the completion gate and the discharge helpers it shares with gate.dropped.

Real-payload shapes (a located done-claim in last_assistant_message). Every blocking case has
a matching silent case, and the FP-guards are explicit: a bare done-word is inert, and a
dropped ledger touch fails open against the live filesystem so a real edit never false-blocks.

The commitments-store and retraction-reconcile tests that used to live here went with the store
itself (2026-09-18): gate.advance was its only reader and it is cut.
"""
from makoto.checks.otherPoint import completion_gate
from makoto.kit import _discharged, _path_components, _suffix_match


def test_completion_bare_doneword_is_inert():
    # the verified 11.7% FP of the old chain pattern: a bare done-word must NOT fire.
    assert completion_gate("Done with the parts I can do", touched_keys=set()) is None


def test_completion_located_not_touched_bites():
    f = completion_gate("Done - added to src/auth.py", touched_keys=set())
    assert f is not None and f.file == "src/auth.py"


def test_completion_located_touched_is_silent():
    assert completion_gate("Done - added to src/auth.py",
                           touched_keys={"src/auth.py"}) is None


def test_completion_dotless_changelog_claim_discharges_against_extended_touch():
    assert completion_gate("I added a hand-written CHANGELOG entry",
                           touched_keys={"/repo/CHANGELOG.md"}) is None


def test_completion_dotless_changelog_claim_still_blocks_without_evidence():
    assert completion_gate("I added a hand-written CHANGELOG entry", touched_keys=set(),
                           fs_exists=lambda _p: False) is not None


def test_completion_fails_open_when_filesystem_shows_it():
    # ledger dropped the touch, but the file exists on disk -> fail open (no FP).
    assert completion_gate("Done - added to src/auth.py", touched_keys=set(),
                           fs_exists=lambda p: p == "src/auth.py") is None


def test_completion_not_a_doneclaim_is_silent():
    assert completion_gate("I will add to src/auth.py next", touched_keys=set()) is None


# --- reconcile -----------------------------------------------------------------
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


# --- _suffix_match: dotless well-known file references ----------------------------------------
def test_suffix_match_dotless_filename_matches_recognized_extension():
    bare = _path_components("CHANGELOG")
    assert _suffix_match(bare, _path_components("/repo/CHANGELOG.md")) is True
    assert _suffix_match(bare, _path_components("/repo/docs/CHANGELOG.rst")) is True


def test_suffix_match_dotless_filename_keeps_component_boundary_firewall():
    bare = _path_components("CHANGELOG")
    assert _suffix_match(bare, _path_components("/repo/CHANGELOG_ARCHIVE.md")) is False
    assert _suffix_match(bare, _path_components("/repo/OLD_CHANGELOG.md")) is False
    assert _suffix_match(_path_components("auth.py"), _path_components("/repo/auth_helper.py")) is False
    assert _suffix_match(_path_components("auth.py"), _path_components("/repo/auth.py.md")) is False
    assert _suffix_match(_path_components("auth.py"), _path_components("/repo/auth.py")) is True


# --- reconcile: an unverified retraction (no R, no U) stays blocked by DEFAULT (engine line 342)
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


# --- discharge helpers: path identity and suffix matching --------------------------------

def test_path_components_drops_home_tilde():
    # gates.py `if c and c != "~"`: the home '~' (and empty components) are dropped so a
    # '~/.claude/...' commitment suffix-discharges against an absolute write. The `or` mutant would
    # retain '~' (and empties), breaking the suffix match.
    from makoto.kit import _path_components
    assert _path_components("~/a/b") == ["a", "b"]
