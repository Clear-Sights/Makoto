"""makoto.checks — ONE flat detector-catalog package (SPEC-5 Task 2, owner-revised layout).

Every check lands as ONE descriptively-named `.py` file directly in this directory — no
category sub-folders. Discovery is by convention and lives in `makoto.registry`
(`scan`/`discover`/`load_checks`/`load_precheck_catalog`), NOT in this file: that scan globs
`checks/*.py` and imports each module exporting a `CHECK` object that duck-types `.id` /
`.applies_at` (one of "Pre"/"Post"/"Stop"/"SubagentStop"/"SessionStart") / `.posture`, plus an
optional `EXTRA_CHECKS` list for a module with more than one surface (e.g. `contractOrder.py`'s
dual Pre+Stop pair). Nothing here enumerates the catalog: dropping a file into this directory is
the whole of registering a check, and there is no hand-maintained list that a new file can fall
out of sync with. Files whose name starts with `_` (this `__init__.py`, `_worldpaths.py`) are
package plumbing, never detector modules, and the scan skips them.

The names re-exported below are the deterministic path/quantity/location primitives, imported
from `makoto.kit` — their home since the substrate merge (they were `substrate/_primitives.py`
before that, and the top-level `makoto/checks.py` module before this package claimed the name).
The re-export keeps every `from makoto.checks import normalize_path`-shaped call site working
unchanged: `state/ledger.py`, `state/plan.py`, `state/commitments.py`, `context.py`, several
detector modules in this directory, and `tests/test_checks.py`. It adds nothing to hook-event
import cost — `makoto.kit` is stdlib-only and `dispatch.py` already imports it at module level.
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
