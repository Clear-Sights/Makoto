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


def load_prechecks(path: Path | None = None) -> list[PreCheck]:
    """parse patterns.toml -> list[PreCheck]. Empty file -> empty list.

    Unknown TOML keys (forensic-catalog fields dropped in 1.0.3, future expansion)
    are silently ignored — only the keys in _PATTERN_FIELDS are passed to the
    constructor. Keeps the loader forward-compatible with TOML metadata that
    isn't (yet) hot-path data.

    When path is None, resolves to makoto/data/patterns.toml.
    """
    if path is None:
        path = Path(__file__).parent / "data" / "patterns.toml"
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
