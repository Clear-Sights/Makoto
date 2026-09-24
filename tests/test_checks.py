"""Unit tests for makoto.checks — the deterministic check primitives.

Cheap, deterministic, no DB. Asserts the path normalizer and the location detector.
"""
from makoto.checks import (
    normalize_path,
    detect_locations,
)


def test_normalize_path_empty_returns_empty_string():
    """Line-pin (L14 RETURN '\"\"'): empty input returns the empty string, not None.
    A None return is observable (crashes downstream .replace callers); reddens if the
    'return \"\"' is mutated to 'return None'."""
    assert normalize_path("") == ""


def test_normalize_path_forces_forward_slash():
    """Windows-portability fix: os.path.normpath emits '\\' separators on Windows,
    which would make the same logical path mismatch its POSIX-authored form. Both
    spellings of the same path must normalize identically regardless of platform.
    Reddens if the trailing '.replace(\"\\\\\\\\\", \"/\")' is dropped."""
    assert normalize_path("dir\\sub\\file.py") == normalize_path("dir/sub/file.py")
    assert "\\" not in normalize_path("dir\\sub\\file.py")


def test_detect_locations_yields_all_paths_in_order():
    locs = [loc for loc, _a, _b in detect_locations("wrote a.py then updated b/c.md")]
    assert locs == ["a.py", "b/c.md"]
