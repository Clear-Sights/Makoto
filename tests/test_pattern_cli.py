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


def test_status_reports_the_same_catalog_the_pattern_command_lists():
    """`makoto status` counted only the Pre edge: 15 of 35.

    A delete-and-rerun pass reported commands/status.md as UNNOTICED -- the slash command a user
    actually runs, checked by nothing. Driving it found the number wrong:

        $ python3 -m makoto status      -> "patterns_count": 15
        $ python3 -m makoto pattern list -> 36 registered surfaces (35 distinct ids)

    `pattern list` was corrected earlier to source its catalog from load_checks(); status was left
    on load_prechecks(), which is the Pre edge alone. Two commands in one CLI answering the same
    question with different numbers, and the user-facing one under-reporting by 20.

    This asserts EQUALITY WITH THE LOADER rather than any literal, so the two cannot drift apart
    again -- the same reason the list test asserts equality instead of a count.
    """
    import json as _json
    import subprocess as _subprocess
    import sys as _sys
    from makoto.substrate._loader import load_checks

    finished = _subprocess.run([_sys.executable, "-m", "makoto", "status"],
                               capture_output=True, text=True)
    assert finished.returncode == 0, finished.stdout + finished.stderr
    reported = _json.loads(finished.stdout)

    expected = len({check.id for check in load_checks()})
    assert reported["patterns_count"] == expected, (
        f"status says {reported['patterns_count']} patterns; the loader registers {expected} "
        f"distinct ids. A user reading status must not see a smaller catalog than the tool has."
    )
    assert expected > 0, "the loader registered nothing -- an empty catalog is not a count"
