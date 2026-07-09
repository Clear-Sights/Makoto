"""PreCheck + Finding dataclasses + TOML loader.

PreCheck fields are the minimum data needed at hot-path dispatch:
  id / fire_level / description / retry_hint / predicate_module / keywords.

The 1.0.3 collapse dropped intent / motivation / evidence from the dataclass
(forensic catalog metadata). Those facts belong in TOML row comments, not in
the Python dataclass — predicates never read them at runtime. load_prechecks
silently ignores extra TOML keys so existing rows continue to load.
"""
from __future__ import annotations
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


# Fields the runtime knows about; extra TOML keys are dropped at load time.
_PATTERN_FIELDS = frozenset({
    "id", "fire_level", "description",
    "retry_hint", "predicate_module", "keywords",
})

# The ONLY admissible fire_level (warning-tier-elimination, 2026-06-02). makoto has no
# non-blocking resting state: a pattern either BLOCKS (proven material — zero corpus-FP, teeth,
# discriminating) or it is CUT. The former "warning"/"disabled"/"shadow" tier was an illusory
# word — a hedge that emits a finding nobody acts on, the same weakening-qualifier shape makoto
# itself flags, turned inward. load_prechecks REJECTS any other level so the tier cannot silently
# return (makoto-follows-makoto: the invariant is enforced in code, not just intent).
_ALLOWED_FIRE_LEVELS = frozenset({"error"})


@dataclass(frozen=True)
class PreCheck:
    """one declarative pattern definition (hot-path schema)."""
    id: str
    fire_level: str                                          # "error" ONLY — see _ALLOWED_FIRE_LEVELS
    description: str                                          # human-facing; interpolated into Finding.message
    retry_hint: str = ""                                      # agent-facing imperative remediation hint
    predicate_module: str = ""                                # dotted path to the predicate function
    keywords: list[str] = field(default_factory=list)         # substring prefilter triggers; >=1 for active patterns


@dataclass(frozen=True)
class Finding:
    """one finding emitted by a predicate — what fired, where, with what message."""
    pattern_id: str
    file: str
    line: int
    level: str
    message: str
    retry_hint: str = ""
    snippet: str = ""
    source_event_id: int = 0   # provenance: the events.id this finding was derived from.
                               # Stamped centrally at the dispatch boundary (where event_id is
                               # in scope) via dataclasses.replace — predicates stay pure detectors
                               # and never thread it themselves. A live-dispatched finding always
                               # carries a non-zero id (enforced by test_source_event_id.py); a 0
                               # marks a finding built outside the hot path (a direct unit call).


def _load_prechecks_from_toml(path: Path) -> list[PreCheck]:
    """The ORIGINAL toml-parsing path, unchanged -- still the mechanism for any EXPLICIT `path`
    override (install.py's own patterns_path re-count, and every test that hands load_prechecks
    a synthetic fixture toml to exercise the loader/validation in isolation). Only the DEFAULT
    (path=None) case below was migrated to the checks/ catalog; explicit-path callers keep
    reading real TOML exactly as before -- no change in their observable behavior."""
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


def load_prechecks(path: Path | None = None) -> list[PreCheck]:
    """The live Pre-tier catalog -> list[PreCheck]. Empty file -> empty list.

    SPEC-C item 2 (Pre-tier cutover, 2026-07-07): the DEFAULT case (`path=None`, what
    `_dispatch.py`'s real hot path calls) sources from `checks._loader.discover()` -- each
    Pre-tier module's own self-describing `CHECK` export. This is the "one registration"
    unification: a check's keywords/retry_hint/description live in ONE place (the module
    itself), not duplicated between a TOML row and the Python file. SPEC-C item 2 step 3
    (2026-07-08): `data/patterns.toml` itself is DELETED -- it was already superseded for the
    default path, and its own consumers (install.py's patterns_path re-count, tests/conftest.py's
    `loaded_pattern` fixture) were migrated to the same default, loader-backed path first.
    `_load_prechecks_from_toml` (below) still exists and is still exercised -- by tests that hand
    this function their OWN synthetic fixture toml via an explicit `path`, unrelated to the now-
    deleted real file -- so an arbitrary toml file can still be parsed on request.

    The `_ALLOWED_FIRE_LEVELS` invariant (makoto has no non-blocking Pre tier) is restated
    for the new source as: every discovered Pre-tier CHECK's posture must be BLOCK (checked
    case-insensitively, matching `_dispatch._blocking_gate_ids()`'s own comparison) -- a
    posture other than BLOCK on a Pre-tier CHECK raises exactly like a bad fire_level did.
    """
    if path is not None:
        return _load_prechecks_from_toml(path)
    from makoto.substrate._loader import discover
    from makoto.verdict import posture as _posture
    live = [c for c in discover() if c.applies_at == "Pre" and c.predicate_module]
    bad = [c for c in live if str(c.posture).strip().lower() != _posture.BLOCK]
    if bad:
        ids = ", ".join(f"{c.id}={c.posture!r}" for c in bad)
        raise ValueError(
            f"makoto has no non-blocking tier: every Pre-tier check must be posture=BLOCK or be CUT. "
            f"Offending rows: {ids}. See the warning-tier-elimination cert.")
    return [PreCheck(id=c.id, fire_level="error", description=c.description,
                      retry_hint=c.retry_hint, predicate_module=c.predicate_module,
                      keywords=list(c.keywords))
            for c in live]
