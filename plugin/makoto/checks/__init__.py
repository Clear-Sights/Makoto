"""makoto.checks — a flat detector-catalog package.

Every check is one `.py` file directly in this directory — no category sub-folders.
Discovery lives in `makoto.registry`, which globs `checks/*.py` and imports each module
exporting a `CHECK` object duck-typing `.id` / `.applies_at` (one of
"Pre"/"Post"/"Stop"/"SubagentStop"/"SessionStart") / `.posture`, plus an optional
`EXTRA_CHECKS` list for a module with more than one surface. Dropping a file into this
directory is the whole of registering a check. Files whose name starts with `_` are
package plumbing and the scan skips them.

`makoto.kit` is the one owner of the shared primitives (`normalize_path`,
`detect_locations`, ...); every consumer, plugin or test, imports them from there
directly rather than through a second re-export route here.
"""
