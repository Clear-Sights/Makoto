"""lib/pytest_cache — existence-filtered lastfailed reader. Spec §0/§1 (2026-06-09).

The §0 access contract is PINNED here: the module performs NO directory enumeration —
one determined cache file, then only paths named inside it (Makoto-not-Historia boundary)."""
import json
import os

from makoto.substrate import pytest_cache
from makoto.substrate.pytest_cache import stale_failing_node


def _mkcache(tmp_path, entries):
    d = tmp_path / ".pytest_cache" / "v" / "cache"
    d.mkdir(parents=True)
    (d / "lastfailed").write_text(json.dumps(entries))
    return str(tmp_path)


def test_missing_cache_is_silent(tmp_path):
    assert stale_failing_node(str(tmp_path)) is None
    assert stale_failing_node("") is None


def test_unparseable_or_nondict_cache_is_silent(tmp_path):
    d = tmp_path / ".pytest_cache" / "v" / "cache"
    d.mkdir(parents=True)
    (d / "lastfailed").write_text("{not json")
    assert stale_failing_node(str(tmp_path)) is None
    (d / "lastfailed").write_text('["a.py::test_x"]')
    assert stale_failing_node(str(tmp_path)) is None


def test_deleted_file_entry_is_filtered(tmp_path):
    """The measured staleness class (42/42 on this repo's green suite): pytest never clears an
    entry it cannot collect, so a deleted file's entry persists forever — filtered, silent."""
    cwd = _mkcache(tmp_path, {"tests/gone.py::test_x": True})
    assert stale_failing_node(cwd) is None


def test_deleted_function_entry_is_filtered(tmp_path):
    cwd = _mkcache(tmp_path, {"tests/t.py::test_gone": True})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("def test_alive():\n    pass\n")
    assert stale_failing_node(cwd) is None


def test_live_failing_node_survives(tmp_path):
    cwd = _mkcache(tmp_path, {"tests/t.py::test_red": True})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("def test_red():\n    assert False\n")
    assert stale_failing_node(cwd) == "tests/t.py::test_red"


def test_parametrize_id_stripped_and_class_method_final_segment(tmp_path):
    cwd = _mkcache(tmp_path, {
        "tests/p.py::test_p[case-1]": True,
        "tests/c.py::TestK::test_m": True,
    })
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "p.py").write_text("def test_p(x):\n    assert x\n")
    (tmp_path / "tests" / "c.py").write_text(
        "class TestK:\n    def test_m(self):\n        assert False\n")
    assert stale_failing_node(cwd) == "tests/c.py::TestK::test_m"  # first in sorted order


def test_module_level_entry_survives_on_file_existence(tmp_path):
    """A collection-error entry is module-level (no ::name); the file itself is the node."""
    cwd = _mkcache(tmp_path, {"tests/broken_collect.py": True})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "broken_collect.py").write_text("import nosuchmod\n")
    assert stale_failing_node(cwd) == "tests/broken_collect.py"


def test_absolute_and_escaping_paths_are_filtered(tmp_path):
    """Cross-project firewall: a node pointing outside cwd never counts as evidence."""
    cwd = _mkcache(tmp_path, {"/etc/passwd::test_x": True, "../other/t.py::test_y": True})
    assert stale_failing_node(cwd) is None


def test_async_def_name_survives(tmp_path):
    cwd = _mkcache(tmp_path, {"tests/a.py::test_aio": True})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "a.py").write_text("async def test_aio():\n    assert False\n")
    assert stale_failing_node(cwd) == "tests/a.py::test_aio"


def test_access_contract_no_enumeration_primitive_in_source():
    """§0 falsifier, static half: the module source contains no enumeration primitive."""
    import inspect
    src = inspect.getsource(pytest_cache)
    for needle in ("os.walk", "glob", "listdir", "scandir", "iterdir", "rglob"):
        assert needle not in src, f"enumeration primitive {needle!r} in pytest_cache"


def test_access_contract_no_enumeration_call_at_runtime(tmp_path, monkeypatch):
    """§0 falsifier, dynamic half: a full reader call never invokes an enumeration API."""
    def _boom(*a, **k):
        raise AssertionError("directory enumeration invoked")
    monkeypatch.setattr(os, "walk", _boom)
    monkeypatch.setattr(os, "listdir", _boom)
    monkeypatch.setattr(os, "scandir", _boom)
    cwd = _mkcache(tmp_path, {"tests/t.py::test_red": True})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("def test_red():\n    assert False\n")
    assert stale_failing_node(cwd) == "tests/t.py::test_red"


def test_entry_cap_fails_open(tmp_path):
    """Beyond the entry hot-path cap (50) entries are UNEXAMINED -> fail-open (silent)."""
    entries = {f"tests/gone_{i:04d}.py::test_x": True for i in range(250)}
    entries["tests/zz_live.py::test_red"] = True   # sorts BEYOND the cap
    cwd = _mkcache(tmp_path, entries)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "zz_live.py").write_text("def test_red():\n    assert False\n")
    assert stale_failing_node(cwd) is None


def test_oversize_file_read_is_capped_failopen(tmp_path):
    """A `def` beyond the per-file read cap is unseen -> entry filtered -> silent. The latency
    contract's byte half: truncation can only SILENCE the gate (FN-direction), never false-fire."""
    cwd = _mkcache(tmp_path, {"tests/big.py::test_tail": True})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "big.py").write_text(
        "# pad\n" * 60000 + "def test_tail():\n    assert False\n")
    assert stale_failing_node(cwd) is None
