"""iter_tool_events — the shared history-walk helper the 4 fabrication gates use to read prior
tool events (full command + full tool_response) from the events-table rows _select_recent returns."""
import json

from makoto.lib.io import iter_tool_events


def test_iter_tool_events_yields_command_and_response():
    row = (1, "t", "live.posttooluse", "/repo", json.dumps({
        "tool_name": "Bash", "tool_input": {"command": "pytest -q"},
        "tool_response": {"stdout": "3 passed", "stderr": ""}}))
    out = list(iter_tool_events([row]))
    assert out == [("Bash", "pytest -q", "3 passed")]


def test_iter_tool_events_accepts_dict_rows():
    # measure_corpus_fp builds {"payload": <json>} dict rows — the helper must accept both shapes.
    row = {"payload": json.dumps({"tool_name": "Bash",
                                  "tool_input": {"command": "ls"},
                                  "tool_response": {"stdout": "a\nb"}})}
    assert list(iter_tool_events([row])) == [("Bash", "ls", "a\nb")]


def test_iter_tool_events_failopen_on_bad_row():
    assert list(iter_tool_events([(1, "t", "x", "/r", "{not json")])) == []
    assert list(iter_tool_events(None)) == []
