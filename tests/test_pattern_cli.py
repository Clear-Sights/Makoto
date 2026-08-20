"""tests for `makoto pattern list` and `makoto pattern show <id>` CLI."""
from makoto.__main__ import _cmd_pattern_list, _cmd_pattern_show


def test_pattern_list_prints_table_of_all_patterns(capsys):
    """`makoto pattern list` shows header + every pattern id from the live catalog."""
    rc = _cmd_pattern_list()
    assert rc == 0
    out = capsys.readouterr().out
    assert "ID" in out and "POSTURE" in out and "DESCRIPTION" in out
    from makoto.registry import load_precheck_catalog
    listed_ids = {line.split()[0] for line in out.splitlines()[2:] if line.strip()}
    live_ids = {check.id for check in load_precheck_catalog()}
    assert listed_ids == live_ids, "pattern list must print one row for every live catalog id"


def test_pattern_show_known_id_prints_full_detail(capsys):
    """`makoto pattern show content.verifier_predicate_weakened` includes id, posture, keywords, retry_hint, and source."""
    rc = _cmd_pattern_show("content.verifier_predicate_weakened")
    assert rc == 0
    out = capsys.readouterr().out
    assert "id" in out and "content.verifier_predicate_weakened" in out
    assert "posture" in out
    assert "keywords" in out
    field_table, source_preview = out.split("---\n", 1)
    assert "predicate" in field_table
    # source preview present
    assert "source:" in source_preview or "regex_file_predicate" in source_preview


def test_pattern_show_unknown_id_returns_2_with_helpful_stderr(capsys):
    """`makoto pattern show 9.99` exits 2 with stderr listing available ids."""
    rc = _cmd_pattern_show("9.99")
    assert rc == 2
    err = capsys.readouterr().err
    assert "9.99" in err
    assert "available" in err.lower()
    assert "content.verifier_predicate_weakened" in err  # at least one real id is suggested
