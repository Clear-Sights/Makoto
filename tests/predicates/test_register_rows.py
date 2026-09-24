"""content.last_wins (A4), content.bound_as_count (B23), event.nested_budget (E11): each fires on
its instance and stays silent on the form it asks for."""
import pytest

from makoto.checks import spec
from makoto.registry import load_precheck_catalog

_CATALOG = {c.id: c for c in load_precheck_catalog()}


def _fires(cid, tool, tool_input):
    ev = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": "/r"}
    return spec.predicate(current_event=ev, history=[], pattern=_CATALOG[cid]) is not None


@pytest.fixture(autouse=True)
def _stock_bash_limits(monkeypatch):
    monkeypatch.delenv("BASH_DEFAULT_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("BASH_MAX_TIMEOUT_MS", raising=False)


@pytest.mark.parametrize("path,content,fires", [
    ("/r/a.py", "M = {'a': 1, 'b': 2, 'a': 3}\n", True),
    ("/r/a.py", "M = {'a': 1, 'a': 1}\n", False),
    ("/r/a.py", "M = {'a': 1, 'b': 3}\n", False),
    ("/r/a.json", '{"x": {"k": true, "k": null}}', True),
    ("/r/a.json", '{"x": {"k": true, "j": null}}', False),
    ("/r/a.md", "{'a': 1, 'a': 3}", False),
])
def test_last_wins(path, content, fires):
    assert _fires("content.last_wins", "Write", {"file_path": path, "content": content}) is fires


@pytest.mark.parametrize("path,content,fires", [
    ("/r/tests/test_x.py", "def test_a():\n    assert len(xs) <= 500\n", True),
    ("C:\\r\\tests\\test_x.py", "def test_a():\n    assert s.count('a') < 3\n", True),
    ("/r/tests/test_x.py", "def test_a():\n    assert len(xs) == 500\n", False),
    ("/r/tests/test_x.py", "def test_a():\n    assert elapsed < 2.0\n", False),
    ("/r/src/x.py", "assert len(xs) <= 500\n", False),
    # unittest-style call form (reword2): same "ceiling not exact count" shape as the ast.Assert
    # case above, just spelled as self.assertLess(len(x), N) / assertLessEqual(...).
    ("/r/tests/test_x.py", "class T:\n    def test_a(self):\n        self.assertLess(len(results), 10)\n", True),
    ("/r/tests/test_x.py",
     "class T:\n    def test_a(self):\n        self.assertLessEqual(xs.count('a'), 3)\n", True),
    ("/r/tests/test_x.py",
     "class T:\n    def test_a(self):\n        self.assertEqual(len(results), 10)\n", False),
])
def test_bound_as_count(path, content, fires):
    assert _fires("content.bound_as_count", "Write", {"file_path": path, "content": content}) is fires


@pytest.mark.parametrize("tool_input,fires", [
    ({"command": "cd x && PYTHONPATH=$PWD/p timeout 1500 python -m pytest", "timeout": 600000}, True),
    ({"command": "timeout 3m make"}, True),
    ({"command": "nohup timeout -k 5 -s KILL 900 x", "timeout": 600000}, True),
    ({"command": "timeout 90 make"}, False),
    ({"command": "timeout 3m make", "timeout": 200000}, False),
    ({"command": "timeout 20m make", "run_in_background": True}, False),
    ({"command": "echo timeout 900"}, False),
])
def test_nested_budget(tool_input, fires):
    assert _fires("event.nested_budget", "Bash", tool_input) is fires


def test_nested_budget_reads_the_raised_ceiling(monkeypatch):
    monkeypatch.setenv("BASH_MAX_TIMEOUT_MS", "1800000")
    assert not _fires("event.nested_budget", "Bash", {"command": "timeout 1500 x", "timeout": 1800000})
