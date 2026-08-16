"""Test-only TOML-pattern-file parser, relocated here 2026-08-16 from
`makoto/vocab.py`'s `_load_prechecks_from_toml` when `schema.load_prechecks()` (and its
explicit-`path` TOML branch) was retired as part of finishing the `registry` migration.

This was never exercised by any live, non-test caller -- the production default path had already
moved to the checks/ catalog; only tests handed this function a synthetic fixture TOML to
exercise TOML-parsing/validation in isolation. Kept as a plain function (not reattached to any
runtime module) because nothing at runtime reads TOML pattern files anymore.
"""
from __future__ import annotations
import tomllib
from pathlib import Path

from makoto.vocab import PreCheck

_PATTERN_FIELDS = frozenset({
    "id", "fire_level", "description",
    "retry_hint", "predicate_module", "keywords",
})

_ALLOWED_FIRE_LEVELS = frozenset({"error"})


def load_toml_patterns(path: Path) -> list[PreCheck]:
    """Parse a `[[pattern]]`-table TOML file into `list[PreCheck]`. Empty file -> empty list.
    Rejects any `fire_level` other than "error" (mirrors the retired production invariant)."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    rows = data.get("pattern", [])
    patterns = [PreCheck(**{k: v for k, v in r.items() if k in _PATTERN_FIELDS})
                for r in rows]
    bad = [p for p in patterns if p.fire_level not in _ALLOWED_FIRE_LEVELS]
    if bad:
        ids = ", ".join(f"{p.id}={p.fire_level!r}" for p in bad)
        raise ValueError(
            f"makoto has no non-blocking tier: every pattern must be fire_level='error' or be CUT. "
            f"Offending rows: {ids}. See the warning-tier-elimination cert.")
    return patterns
