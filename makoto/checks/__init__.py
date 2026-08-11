"""makoto.checks — ONE flat detector-catalog package (SPEC-5 Task 2, owner-revised layout).

Every standalone check lands as ONE descriptively-named `.py` file directly in
this directory — no category sub-folders. A family whose members are *exactly* parameterized
instances of one algorithm may instead share a named data-driven module, with its first member as
`CHECK` and further members in `EXTRA_CHECKS`; `agnosticRegex.py` is the concrete example. A
check module is discovered by convention (see `_loader.load_checks`): a module-level `CHECK`
object exposing `.id` / `.applies_at` (one of "Pre"/"Post"/"Stop"/"SubagentStop"/"SessionStart") /
`.posture`. Files whose name starts
with `_` (this `__init__.py`, `_loader.py`, `_primitives.py`) are package plumbing, never
detector modules, and the loader skips them.

`_primitives.py` (this package's one non-detector file besides the loader) holds the
pre-existing L0 path/quantity/location primitives that used to live at the top-level
`makoto/checks.py` module, before that name was claimed by this package (see that module's own
docstring for the relocation note). Re-exported here so every existing
`from makoto.checks import normalize_path`-shaped call site across the codebase — `ledger.py`,
`_dispatch.py`, `retraction.py`, `commitments.py`, several `stopchecks/*.py` modules, and their
tests — is byte-for-byte unaffected by this package's introduction.
"""
from makoto.substrate._primitives import (
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
