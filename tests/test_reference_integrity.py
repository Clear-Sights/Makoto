import json

from makoto.reference_integrity import find_broken_references, main


def test_repository_local_references_resolve():
    assert find_broken_references(__import__("pathlib").Path(__file__).parent.parent) == []


def test_broken_reference_in_a_copy_fails(tmp_path, capsys):
    """A syntactically valid source path that names no file must make the gate red."""
    copy = tmp_path / "copy"
    docs = copy / "docs"
    docs.mkdir(parents=True)
    (docs / "note.md").write_text("[missing source](../strong-skills/register/ASYMMETRY.json)\n")
    (copy / "manifest.json").write_text(json.dumps({"source": "./also-missing.json"}))

    assert main(["--root", str(copy)]) == 1
    out = capsys.readouterr().out
    assert "ASYMMETRY.json" in out
    assert "also-missing.json" in out
    assert "FAIL" in out


def test_existing_relative_reference_passes(tmp_path):
    (tmp_path / "target.md").write_text("source\n")
    (tmp_path / "note.md").write_text("[source](target.md)\n")
    assert find_broken_references(tmp_path) == []


def test_manifest_path_field_is_resolved(tmp_path):
    (tmp_path / "README.md").write_text("source\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nreadme = "README.md"\n')
    assert find_broken_references(tmp_path) == []

    (tmp_path / "pyproject.toml").write_text('[project]\nreadme = "missing.md"\n')
    broken = find_broken_references(tmp_path)
    assert [finding.reference for finding in broken] == ["missing.md"]


def test_repo_rooted_inline_document_path_is_resolved(tmp_path):
    source = tmp_path / "makoto" / "checks" / "gate.py"
    source.parent.mkdir(parents=True)
    source.write_text("source\n")
    notes = tmp_path / "docs"
    notes.mkdir()
    (notes / "note.md").write_text("see `makoto/checks/gate.py`\n")
    assert find_broken_references(tmp_path) == []

    (notes / "note.md").write_text("see `makoto/checks/missing.py`\n")
    broken = find_broken_references(tmp_path)
    assert [finding.reference for finding in broken] == ["makoto/checks/missing.py"]
