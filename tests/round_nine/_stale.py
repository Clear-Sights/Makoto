"""Shared shape for round nine's gate.stale_pass plants: pytest's own lastfailed record under the
project root names a live failing node, and the turn stops on a claim. Underscore-prefixed: the
runner skips it."""
import json

ROW = "gate.stale_pass"
NODE = "tests/test_x.py::test_red"
TEST = "def test_red():\n    " + "as" + "sert 1 == 2\n"


def cache(entries):
    return {".pytest_cache/v/cache/lastfailed": json.dumps(entries),
            "tests/test_x.py": TEST}


def stop(text, cwd="{cwd}"):
    return {"hook_event_name": "Stop", "last_assistant_message": text, "cwd": cwd}


def case(name, text, entries=None, cwd="{cwd}", files=None):
    f = cache({NODE: True} if entries is None else entries)
    f.update(files or {})
    return dict(name=name, row=ROW, files=f, events=[stop(text, cwd)])
