"""tests for `makoto pattern list` and `makoto pattern show <id>` CLI."""
from makoto.substrate._loader import load_checks
from makoto.__main__ import _cmd_pattern_list, _cmd_pattern_show


def test_pattern_list_prints_table_of_all_patterns(capsys):
    """The CLI prints exactly every check surface the live loader registered."""
    rc = _cmd_pattern_list()
    assert rc == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert "ID" in lines[0] and "DESCRIPTION" in lines[0]
    listed_ids = [line.split(maxsplit=1)[0] for line in lines[2:]]
    assert listed_ids == [check.id for check in load_checks()]


def test_pattern_show_known_id_prints_full_detail(capsys):
    """`makoto pattern show content.verifier_predicate_weakened` includes id, fire_level, keywords, retry_hint, and source."""
    rc = _cmd_pattern_show("content.verifier_predicate_weakened")
    assert rc == 0
    out = capsys.readouterr().out
    assert "id" in out and "content.verifier_predicate_weakened" in out
    assert "posture" in out
    assert "keywords" in out
    assert "predicate" in out
    # source preview present
    assert "source:" in out or "regex_file_predicate" in out


def test_pattern_show_accepts_a_live_stop_check_id(capsys):
    """An id discoverable from the loader is also inspectable through the CLI."""
    rc = _cmd_pattern_show("gate.stale_establisher")
    assert rc == 0
    out = capsys.readouterr().out
    assert "id" in out and "gate.stale_establisher" in out
    assert "applies_at" in out and "Stop" in out


def test_pattern_show_unknown_id_returns_2_with_helpful_stderr(capsys):
    """`makoto pattern show 9.99` exits 2 with stderr listing available ids."""
    rc = _cmd_pattern_show("9.99")
    assert rc == 2
    err = capsys.readouterr().err
    assert "9.99" in err
    assert "available" in err.lower()
    assert "content.verifier_predicate_weakened" in err  # at least one real id is suggested
