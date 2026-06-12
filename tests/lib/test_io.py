"""lib/io.py (L1) — tool/event I/O parsing, renamed. Pins new names + behaviour + L1 purity."""
import ast
from pathlib import Path


def test_io_exports_renamed_symbols():
    from makoto.lib import io as mio
    for name in ("raw_payload_str", "bash_output_text", "is_failing_testrun", "is_test_runner"):
        assert callable(getattr(mio, name)), name


def test_io_old_names_gone():
    from makoto.lib import io as mio
    for old in ("_bash_output_text", "looks_like_failing_testrun", "command_is_test_runner"):
        assert not hasattr(mio, old), f"no alias: {old}"


def test_io_behaviour_preserved():
    from makoto.lib.io import bash_output_text, is_failing_testrun, is_test_runner
    assert bash_output_text({"stdout": "ok", "stderr": ""}) == "ok\n"
    assert is_failing_testrun("=== 3 failed ===") is True
    assert is_failing_testrun("=== 681 passed, 3 xfailed ===") is False
    assert is_test_runner("python -m pytest tests/ -q") is True
    assert is_test_runner("cat tests/old_failure.log") is False


def test_io_is_L1_imports_only_L0():
    src = Path(__file__).resolve().parents[2] / "lib" / "io.py"
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("makoto"):
            assert node.module == "makoto.lexicons", f"L1 io may import only L0 lexicons: {node.module}"


# --- behavioral cases redistributed verbatim from the dissolved tests/predicates/test_helpers.py (idealization: name<->content) ---

def test_bash_output_text_dict_joins_stdout_and_stderr():
    """L186 (`or ""`): stdout and stderr are coalesced with `or ""` then joined.
    Mutating the stderr coalesce to `and ""` drops the stderr text ('o\\ne' -> 'o\\n').
    Pins the `or` fallback so Bash stderr is preserved in the ledger row."""
    from makoto.lib.io import bash_output_text
    assert bash_output_text({"stdout": "o", "stderr": "e"}) == "o\ne"


def test_bash_output_text_list_branch_joins_block_text():
    """L188 NOT (isinstance list) + L189 RETURN (the joined string): a list
    tool_response of content blocks joins their text with spaces. Negating the
    isinstance check skips this branch (-> '' fallback); nulling the return -> None.
    Pins both: the list branch fires and returns the joined block text."""
    from makoto.lib.io import bash_output_text
    assert bash_output_text([{"text": "a"}, {"text": "b"}]) == "a b"
    assert bash_output_text(["x", "y"]) == "x y"


def test_bash_output_text_string_input_returned_verbatim():
    """L192 NOT (isinstance str) + L193 RETURN (tool_response): a bare-string
    tool_response is returned verbatim. Negating the isinstance check falls through
    to '' ; nulling the return -> None. Pins both: 'hello' -> 'hello'."""
    from makoto.lib.io import bash_output_text
    assert bash_output_text("hello") == "hello"


def test_bash_output_text_unknown_type_returns_empty_string():
    """L194 RETURN: the final fallback returns '' for an unhandled type (e.g. None,
    int). Mutating to `return None` breaks the str contract — the helper is a public
    audit target. Pins `return ""`."""
    from makoto.lib.io import bash_output_text
    assert bash_output_text(None) == ""
    assert bash_output_text(123) == ""
