"""tests for `makoto pattern list` and `makoto pattern show <id>` CLI."""
from makoto.__main__ import _cmd_pattern_list, _cmd_pattern_show


def test_pattern_list_prints_table_of_all_patterns(capsys):
    """`makoto pattern list` shows header + every pattern id from the live catalog."""
    rc = _cmd_pattern_list()
    assert rc == 0
    out = capsys.readouterr().out
    assert "ID" in out and "LEVEL" in out and "DESCRIPTION" in out
    # A representative span of live catalog ids appears
    for pid in ("content.verifier_predicate_weakened", "content.integrity_suppression_flag", "content.deferred_checkbox_theater", "content.phantom_citation", "content.verifier_exit_masking", "content.fabricated_commit_sha", "content.self_mute_guard"):
        assert pid in out, f"pattern {pid} missing from list output"


def test_pattern_show_known_id_prints_full_detail(capsys):
    """`makoto pattern show 1.1` includes id, fire_level, keywords, retry_hint, and source."""
    rc = _cmd_pattern_show("content.verifier_predicate_weakened")
    assert rc == 0
    out = capsys.readouterr().out
    assert "id" in out and "content.verifier_predicate_weakened" in out
    assert "fire_level" in out
    assert "keywords" in out
    assert "predicate" in out
    # source preview present
    assert "source:" in out or "regex_file_predicate" in out


def test_pattern_show_resolves_a_legacy_id_via_the_alias_table(capsys):
    """`makoto pattern show 1.1` (the check's OLD id, pre-SPEC-C-item-3 rename) still resolves to
    the same live check under its current canonical name."""
    rc = _cmd_pattern_show("1.1")
    assert rc == 0
    out = capsys.readouterr().out
    assert "content.verifier_predicate_weakened" in out


def test_pattern_show_unknown_id_returns_2_with_helpful_stderr(capsys):
    """`makoto pattern show 9.99` exits 2 with stderr listing available ids."""
    rc = _cmd_pattern_show("9.99")
    assert rc == 2
    err = capsys.readouterr().err
    assert "9.99" in err
    assert "available" in err.lower()
    assert "content.verifier_predicate_weakened" in err  # at least one real id is suggested
