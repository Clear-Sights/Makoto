"""The launch checklist: START's launch line stays cheap."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def launch_lines(text: str) -> list[str]:
    return re.findall(r"^Run `sh tools/launch_check\.sh[^`]*`.*$", text, re.M)


def test_start_launches_without_the_suite():
    """The suite re-runs what main's merge already ran (76 s of 85): START's launch line never
    brings `--suite` back; it belongs before a step is called done."""
    lines = launch_lines((REPO / "START.md").read_text(encoding="utf-8"))
    assert len(lines) == 1, lines
    assert "--suite" not in lines[0], lines[0]


def test_the_launch_line_check_reads_red_on_its_plant():
    planted = "## Launch checklist\n\nRun `sh tools/launch_check.sh --suite` before anything else.\n"
    (line,) = launch_lines(planted)
    assert "--suite" in line
