"""atom_source_edited must count a source edit made via Bash (`sed -i`, a shell redirect),
not only via the Edit/Write/MultiEdit/NotebookEdit tools -- the same defect class as the
edit-tool-only reads elsewhere in this module, isolated to this one atom."""
from __future__ import annotations

from makoto.substrate._canonAtoms import atom_source_edited


def _bash(cmd, **result):
    return {"name": "Bash", "input": {"command": cmd}, "result": result}


def _edit(file_path):
    return {"name": "Edit", "input": {"file_path": file_path, "old_string": "a", "new_string": "b"},
            "result": {}}


def test_sed_inplace_on_source_file_fires():
    assert atom_source_edited([_bash("sed -i 's/old_value/new_value/' src/app.py")], "")


def test_shell_redirect_into_source_file_fires():
    assert atom_source_edited([_bash("echo 'x = 1' > src/app.py")], "")


def test_redirect_into_dev_null_does_not_fire():
    assert not atom_source_edited([_bash("pytest -q > /dev/null")], "")


def test_sed_inplace_on_test_file_does_not_fire():
    assert not atom_source_edited([_bash("sed -i 's/a/b/' tests/test_x.py")], "")


def test_plain_bash_with_no_edit_does_not_fire():
    assert not atom_source_edited([_bash("pytest -q")], "")


def test_edit_tool_still_fires_unaffected():
    assert atom_source_edited([_edit("src/app.py")], "")
