"""docs/demo/ was the one part of this repository no test touched.

Two properties, both of which have already caught a real defect:

1. `_naturalsize` formats byte counts the way `humanize.naturalsize` did before that package
   was dropped. The table below is humanize 4.16.0's REAL output, recorded by running it; it is
   not what anyone expected humanize to say. The first hand-written version of `_naturalsize`
   passed every value the demo actually produces and was still wrong on three: it said
   "1 Bytes" for one byte, "1000.0 GB" where humanize carries to "1.0 TB", and it had no unit
   above TB. The boundary rows (999_999_999_999 and friends) are the rows that catch that
   class of bug -- a divisor-only test passes right through it, because the demo's own numbers
   are all under a kilobyte and never leave the "Bytes" branch at all.

2. Re-rendering the screenshots reproduces the committed SVGs byte for byte. That is what makes
   those images evidence rather than decoration: if anyone edits an SVG by hand, or changes the
   renderer without regenerating, this goes red. It also means the README's claim that every
   visible line is genuine logged output stays checkable instead of being taken on trust.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "docs" / "demo"
_ABSOLUTE_PATH = re.compile(r"(?<![\w>])(/[^\s\"'`<>]+)")

# humanize 4.16.0, naturalsize(value), recorded from actual calls.
HUMANIZE_TABLE = [
    (0, "0 Bytes"),
    (1, "1 Byte"),                       # singular -- the obvious thing to get wrong
    (2, "2 Bytes"),
    (110, "110 Bytes"),                  # the three values the shipped demo really produces
    (636, "636 Bytes"),
    (652, "652 Bytes"),
    (999, "999 Bytes"),
    (1000, "1.0 kB"),                    # decimal, not binary: 1000 and not 1024
    (1024, "1.0 kB"),
    (1500, "1.5 kB"),
    (1234567, "1.2 MB"),
    (5000000000, "5.0 GB"),
    (999999999999, "1.0 TB"),            # carries on the ROUNDED value, not the raw one
    (10**13, "10.0 TB"),
    (10**16, "10.0 PB"),
    (10**27, "1.0 RB"),                  # the 2022 SI prefixes exist and humanize knows them
    (10**30, "1.0 QB"),
]


def _render_svg():
    spec = importlib.util.spec_from_file_location("_demo_render_svg", DEMO / "render_svg.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_naturalsize_matches_the_recorded_humanize_output():
    naturalsize = _render_svg()._naturalsize
    wrong = [(value, naturalsize(value), expected)
             for value, expected in HUMANIZE_TABLE if naturalsize(value) != expected]
    assert not wrong, f"got != humanize 4.16.0 for {len(wrong)} values: {wrong}"


def test_rerendering_reproduces_the_committed_screenshots_exactly():
    """Regenerating must leave the committed screenshots byte-for-byte unchanged."""
    scenarios = ("block", "receipt", "configchange")
    screenshot_paths = [DEMO / "screenshots" / f"{scenario}.svg" for scenario in scenarios]
    before = {path: path.read_bytes() for path in screenshot_paths}

    render = subprocess.run([sys.executable, str(DEMO / "render_svg.py")],
                            cwd=REPO, capture_output=True, text=True)
    assert render.returncode == 0, f"render_svg.py exited {render.returncode}:\n{render.stderr}"

    after = {path: path.read_bytes() for path in screenshot_paths}
    assert before == after, "re-rendering changed the committed screenshots"


def test_regenerating_demo_logs_is_byte_identical_and_machine_independent():
    """The README's committed demo logs must reproduce without local paths leaking in."""
    scenarios = ("block", "receipt", "configchange")
    log_paths = [DEMO / "logs" / f"{scenario}.json" for scenario in scenarios]
    before = {path: path.read_bytes() for path in log_paths}

    first = subprocess.run([sys.executable, str(DEMO / "render_demo.py")],
                           cwd=REPO, capture_output=True, text=True)
    assert first.returncode == 0, f"first render_demo.py exited {first.returncode}:\n{first.stderr}"
    first_logs = {path: path.read_bytes() for path in log_paths}

    second = subprocess.run([sys.executable, str(DEMO / "render_demo.py")],
                            cwd=REPO, capture_output=True, text=True)
    assert second.returncode == 0, f"second render_demo.py exited {second.returncode}:\n{second.stderr}"
    second_logs = {path: path.read_bytes() for path in log_paths}

    assert first_logs == second_logs, "two consecutive demo renders produced different logs"

    changed = [path.relative_to(REPO) for path in log_paths if before[path] != first_logs[path]]
    assert not changed, f"regenerating changed committed demo logs: {changed}"

    repo = REPO.resolve()
    leaked = []
    for path, contents in second_logs.items():
        for value in _strings(json.loads(contents)):
            for absolute_path in _ABSOLUTE_PATH.findall(value):
                if not Path(absolute_path).is_relative_to(repo):
                    leaked.append((path.relative_to(REPO), absolute_path))
    assert not leaked, f"demo logs contain absolute paths outside the repository: {leaked}"


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)
