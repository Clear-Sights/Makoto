"""PreCheck + Finding dataclasses.

PreCheck fields are the minimum data needed at hot-path dispatch:
  id / fire_level / description / retry_hint / predicate_module / keywords.

The 1.0.3 collapse dropped intent / motivation / evidence from the dataclass
(forensic catalog metadata). Those facts belong in the check module's own
docstring, not in the Python dataclass — predicates never read them at runtime.

The `load_prechecks()` TOML-adapter loader that used to live here (schema.py owning a second,
parallel catalog alongside `substrate._loader`) was retired 2026-08-16: the migration to a
single discovery path (`substrate._loader.load_checks`/`load_precheck_catalog`) is complete.
`PreCheck` itself survives as a convenience dataclass for hand-constructing synthetic pattern
fixtures in unit tests that call a predicate directly without going through the loader; the live
Pre-tier catalog is `substrate._loader.load_precheck_catalog()`, whose rows are `Check`
instances, not `PreCheck` instances -- the two are structurally similar but no longer the same
type, and nothing at runtime converts one into the other.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PreCheck:
    """one declarative pattern definition -- test-fixture convenience shape ONLY (the live
    Pre-tier catalog is `substrate._loader.load_precheck_catalog()`, whose rows are `Check`
    instances, not this class). Kept for tests that hand-construct a synthetic pattern to call
    a predicate directly, unit-test style."""
    id: str
    fire_level: str                                          # "error" ONLY, by convention -- no longer runtime-checked here
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


