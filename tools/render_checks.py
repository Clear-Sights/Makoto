#!/usr/bin/env python3
"""Render README check counts from makoto.registry.

    python3 tools/render_checks.py --check
    python3 tools/render_checks.py --write

Standard library only.
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugin"
sys.path.insert(0, str(PLUGIN))

from makoto.registry import _ADVISORY_ALLOWLIST, load_checks  # noqa: E402

README = REPO / "README.md"
MARKER = "check-counts"


def render_counts() -> list[str]:
    pre = load_checks(edge="Pre")
    stop = load_checks(edge="Stop")
    gates = [check for check in stop if check.may_block]
    advisory = [check for check in gates if check.id in _ADVISORY_ALLOWLIST]
    blocking = [check for check in gates if check.id not in _ADVISORY_ALLOWLIST]
    return [
        f"- **{len(pre)} pre-checks** (all blocking)",
        f"- **{len(stop)} Stop checks** (all checks registered at the Stop edge)",
        f"- **{len(gates)} end-of-turn gates** (`may_block=True`)",
        f"- **{len(blocking)} blocking end-of-turn gates** (not advisory-allowlisted)",
        f"- **{len(advisory)} advisory end-of-turn gates** (advisory-allowlisted)",
    ]


def _region(text: str, path: Path) -> tuple[int, int, list[str]]:
    lines = text.split("\n")
    begin = end = None
    for index, line in enumerate(lines):
        if line.startswith(f"<!-- BEGIN GENERATED: {MARKER}"):
            if begin is not None:
                raise SystemExit(f"{path}: a second {MARKER} BEGIN marker at line {index + 1}")
            begin = index
        elif line.startswith(f"<!-- END GENERATED: {MARKER}") and end is None:
            end = index
    if begin is None or end is None or end <= begin:
        raise SystemExit(f"{path}: no {MARKER} marker region")
    return begin + 1, end, lines


def main(argv: list[str]) -> int:
    if argv[1:] not in (["--check"], ["--write"]):
        print("usage: render_checks.py --check | --write", file=sys.stderr)
        return 2
    write = argv[1] == "--write"
    start, stop, lines = _region(README.read_text(encoding="utf-8"), README)
    fresh = ["", *render_counts(), ""]
    committed = lines[start:stop]
    if committed == fresh:
        if not write:
            print("check counts match makoto.registry")
        return 0
    if write:
        lines[start:stop] = fresh
        README.write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {README.relative_to(REPO)}")
        return 0
    print("GENERATED CHECK-COUNT DRIFT -- README.md disagrees with makoto.registry:", file=sys.stderr)
    for line in difflib.unified_diff(
        committed, fresh, fromfile="README.md (committed)", tofile="makoto.registry (current)",
        lineterm="",
    ):
        print(line, file=sys.stderr)
    print("Run: python3 tools/render_checks.py --write", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
