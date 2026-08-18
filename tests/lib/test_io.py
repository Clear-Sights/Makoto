"""lib/io.py (L1) — tool/event I/O parsing, renamed. Pins new names + behaviour. (kit.py's
import purity is enforced by tests/test_import_direction.py, seam 7.)"""


def test_io_exports_renamed_symbols():
    from makoto import kit as mio
    for name in ("raw_payload_str", "bash_output_text", "is_failing_testrun", "is_test_runner",
                 "failure_terminal_result"):
        assert callable(getattr(mio, name)), name


def test_io_old_names_gone():
    from makoto import kit as mio
    for old in ("_bash_output_text", "looks_like_failing_testrun", "command_is_test_runner"):
        assert not hasattr(mio, old), f"no alias: {old}"


def test_io_behaviour_preserved():
    from makoto.kit import bash_output_text, is_failing_testrun, is_test_runner
    assert bash_output_text({"stdout": "ok", "stderr": ""}) == "ok\n"
    assert is_failing_testrun("=== 3 failed ===") is True
    assert is_failing_testrun("=== 681 passed, 3 xfailed ===") is False
    assert is_test_runner("python -m pytest tests/ -q") is True
    assert is_test_runner("cat tests/old_failure.log") is False


def test_failure_terminal_result_has_one_stable_shape_and_safe_fallback():
    from makoto.kit import classify_failure, failure_terminal_result

    assert failure_terminal_result({"error": "Connection error", "is_interrupt": True}) == {
        "error": "Connection error", "interrupted": True,
    }
    missing_detail = failure_terminal_result({"is_interrupt": False})
    assert missing_detail == {"error": "tool call failed", "interrupted": False}
    assert classify_failure(missing_detail["error"]) is None


# --- behavioral cases redistributed verbatim from the dissolved tests/predicates/test_helpers.py (idealization: name<->content) ---

def test_bash_output_text_dict_joins_stdout_and_stderr():
    """L186 (`or ""`): stdout and stderr are coalesced with `or ""` then joined.
    Mutating the stderr coalesce to `and ""` drops the stderr text ('o\\ne' -> 'o\\n').
    Pins the `or` fallback so Bash stderr is preserved in the ledger row."""
    from makoto.kit import bash_output_text
    assert bash_output_text({"stdout": "o", "stderr": "e"}) == "o\ne"


def test_bash_output_text_list_branch_joins_block_text():
    """L188 NOT (isinstance list) + L189 RETURN (the joined string): a list
    tool_response of content blocks joins their text with spaces. Negating the
    isinstance check skips this branch (-> '' fallback); nulling the return -> None.
    Pins both: the list branch fires and returns the joined block text."""
    from makoto.kit import bash_output_text
    assert bash_output_text([{"text": "a"}, {"text": "b"}]) == "a b"
    assert bash_output_text(["x", "y"]) == "x y"


def test_bash_output_text_string_input_returned_verbatim():
    """L192 NOT (isinstance str) + L193 RETURN (tool_response): a bare-string
    tool_response is returned verbatim. Negating the isinstance check falls through
    to '' ; nulling the return -> None. Pins both: 'hello' -> 'hello'."""
    from makoto.kit import bash_output_text
    assert bash_output_text("hello") == "hello"


def test_bash_output_text_unknown_type_returns_empty_string():
    """L194 RETURN: the final fallback returns '' for an unhandled type (e.g. None,
    int). Mutating to `return None` breaks the str contract — the helper is a public
    audit target. Pins `return ""`."""
    from makoto.kit import bash_output_text
    assert bash_output_text(None) == ""
    assert bash_output_text(123) == ""
