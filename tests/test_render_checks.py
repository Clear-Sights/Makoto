from __future__ import annotations

from tools import render_checks


def _readme(body: list[str]) -> str:
    return "\n".join([
        "before",
        "<!-- BEGIN GENERATED: check-counts | source: makoto.registry | regenerate: python3 tools/render_checks.py --write -->",
        "",
        *body,
        "",
        "<!-- END GENERATED: check-counts -->",
        "after",
    ])


def test_check_accepts_an_agreeing_committed_block(tmp_path, monkeypatch, capsys):
    readme = tmp_path / "README.md"
    readme.write_text(_readme(render_checks.render_counts()), encoding="utf-8")
    monkeypatch.setattr(render_checks, "README", readme)

    assert render_checks.main(["render_checks.py", "--check"]) == 0
    assert capsys.readouterr().out == "check counts match makoto.registry\n"


def test_check_rejects_drift_and_names_the_difference(tmp_path, monkeypatch, capsys):
    readme = tmp_path / "README.md"
    stale = render_checks.render_counts()
    stale[0] = "- **999 pre-checks** (all blocking)"
    readme.write_text(_readme(stale), encoding="utf-8")
    monkeypatch.setattr(render_checks, "README", readme)

    assert render_checks.main(["render_checks.py", "--check"]) == 1
    err = capsys.readouterr().err
    assert "README.md disagrees with makoto.registry" in err
    assert "- **999 pre-checks**" in err
    assert f"+- **{len(render_checks.load_checks(edge='Pre'))} pre-checks**" in err
