"""gate.stale_pass — whole-suite pass-claim ✗ pytest's own on-disk lastfailed record.
Sentinels (a)-(d) per spec §1; (d) is the teeth arm (sole-killer for the gate body)."""
import json
import time

from makoto.checks.stalePytestCache import stale_pass_gate, GATE


def _cache(tmp_path, entries, live=()):
    d = tmp_path / ".pytest_cache" / "v" / "cache"
    d.mkdir(parents=True)
    (d / "lastfailed").write_text(json.dumps(entries))
    (tmp_path / "tests").mkdir(exist_ok=True)
    for rel, body in live:
        (tmp_path / rel).write_text(body)
    return str(tmp_path)


def test_d_teeth_live_failing_node_plus_clean_green_claim_FIRES(tmp_path):
    cwd = _cache(tmp_path, {"tests/t.py::test_red": True},
                 [("tests/t.py", "def test_red():\n    assert False\n")])
    f = stale_pass_gate("All tests pass now.", cwd=cwd)
    assert f is not None and f.pattern_id == "gate.stale_pass"
    assert "tests/t.py::test_red" in f.message


def test_a_stale_deleted_node_green_claim_silent(tmp_path):
    cwd = _cache(tmp_path, {"tests/gone.py::test_x": True})
    assert stale_pass_gate("All tests pass now.", cwd=cwd) is None


def test_b_teeth_framed_claim_silent(tmp_path):
    cwd = _cache(tmp_path, {"tests/t.py::test_red": True},
                 [("tests/t.py", "def test_red():\n    assert False\n")])
    assert stale_pass_gate(
        "I deliberately broke it to prove the test has teeth — with the mutation in, "
        "the rest of the tests pass as expected.", cwd=cwd) is None


def test_c_forward_framed_claim_silent(tmp_path):
    cwd = _cache(tmp_path, {"tests/t.py::test_red": True},
                 [("tests/t.py", "def test_red():\n    assert False\n")])
    assert stale_pass_gate("Once I fix the import, the tests pass.", cwd=cwd) is None


def test_subset_claim_silent(tmp_path):
    cwd = _cache(tmp_path, {"tests/t.py::test_red": True},
                 [("tests/t.py", "def test_red():\n    assert False\n")])
    assert stale_pass_gate("The parser tests pass.", cwd=cwd) is None


def test_no_claim_silent_even_with_live_failing_node(tmp_path):
    cwd = _cache(tmp_path, {"tests/t.py::test_red": True},
                 [("tests/t.py", "def test_red():\n    assert False\n")])
    assert stale_pass_gate("Refactored the loader.", cwd=cwd) is None


def test_green_cache_silent(tmp_path):
    cwd = _cache(tmp_path, {})
    assert stale_pass_gate("All tests pass now.", cwd=cwd) is None


def test_gate_export_shape():
    assert GATE.id == "gate.stale_pass"


def test_latency_budget_literal_lookup_class(tmp_path):
    """User-directed latency contract (2026-06-09): the gate is literal-lookup-class — a direct
    direct-pointer lookup, hard ceiling 200-300ms. Worst-case-SHAPED fixture (the full 50-entry
    cap, every node live so nothing early-exits the existence filter) run end-to-end 10×
    consecutively inside ONE 300ms budget => ≤30ms/call measured, 10× headroom under the ceiling.
    Falsifier: any enumeration primitive or unbounded read sneaking into the path blows this."""
    entries = {f"tests/t{i}.py::test_x{i}": True for i in range(50)}
    live = [(f"tests/t{i}.py", f"def test_x{i}():\n    assert False\n") for i in range(50)]
    cwd = _cache(tmp_path, entries, live)
    t0 = time.perf_counter()
    for _ in range(10):
        assert stale_pass_gate("All tests pass now.", cwd=cwd) is not None
    assert time.perf_counter() - t0 < 0.3


def test_no_claim_path_never_touches_disk(tmp_path):
    """Cheapest-first ordering falsifier: with NO whole-suite claim, the gate must exit before the
    disk lookup — an unreadable lastfailed (a directory at its path) would crash any
    disk-first ordering, so silence here pins claim-regex-FIRST."""
    bad = tmp_path / ".pytest_cache" / "v" / "cache" / "lastfailed"
    bad.mkdir(parents=True)                       # a DIRECTORY where the file should be
    assert stale_pass_gate("Refactored the loader.", cwd=str(tmp_path)) is None
