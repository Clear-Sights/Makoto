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
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "docs" / "demo"

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
    """Regenerate in place and ask git whether anything moved. Nothing should."""
    before = subprocess.run(["git", "status", "--porcelain", "docs/demo/screenshots"],
                            cwd=REPO, capture_output=True, text=True, check=True).stdout
    assert before == "", f"screenshots were already dirty before rendering:\n{before}"

    render = subprocess.run([sys.executable, str(DEMO / "render_svg.py")],
                            cwd=REPO, capture_output=True, text=True)
    assert render.returncode == 0, f"render_svg.py exited {render.returncode}:\n{render.stderr}"

    after = subprocess.run(["git", "status", "--porcelain", "docs/demo/screenshots"],
                           cwd=REPO, capture_output=True, text=True, check=True).stdout
    assert after == "", (
        "re-rendering changed the committed screenshots -- either an SVG was edited by hand, or "
        f"the renderer changed and the images were not regenerated:\n{after}"
    )
