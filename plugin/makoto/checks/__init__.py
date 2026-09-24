"""makoto.checks — a flat detector-catalog package.

Every check is one `.py` file directly in this directory — no category sub-folders.
Discovery lives in `makoto.registry`, which globs `checks/*.py` and imports each module
exporting a `CHECK` object duck-typing `.id` / `.applies_at` (one of
"Pre"/"Post"/"Stop"/"SubagentStop"/"SessionStart") / `.posture`, plus an optional
`EXTRA_CHECKS` list for a module with more than one surface. Dropping a file into this
directory is the whole of registering a check. Files whose name starts with `_` are
package plumbing and the scan skips them.

Re-exports below keep `from makoto.checks import normalize_path`-shaped call sites
working. `makoto.kit` is stdlib-only, so this adds no import cost to hook events.
"""
from makoto.kit import (
    normalize_path,
    location_match,
    quantity_match,
    subject_binds,
    detect_location,
    detect_locations,
    detect_quantity,
    bash_nonempty_violation,
)

__all__ = [
    "normalize_path",
    "location_match",
    "quantity_match",
    "subject_binds",
    "detect_location",
    "detect_locations",
    "detect_quantity",
    "bash_nonempty_violation",
]
