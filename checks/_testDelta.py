"""makoto.checks.testDelta -- Task 3, the domain correction (owner: "Makoto owns block +
redirect -- that is its entire domain"). This move started life in Lever's catalogue as
"test-delta redirect" but is REDIRECT-shaped (reactive to a test run that just completed, not a
proactive positive-positioning move) -- so per the owner's boundary it belongs here, not Lever.

Wired DIRECTLY into `_dispatch.py`'s PostToolUse branch, not the patterns.toml/load_prechecks
catalog (Pre-only) nor the Stop-gate catalog (Stop-only) -- neither covers a Post-edge advisory
today. This is a one-off wire, honestly disclosed at its call site, not hidden behind a catalog
entry that would misleadingly imply broader dispatch-loader coverage than exists.

`compute_delta` reuses `namedTestTeeth.py`'s OWN `recorded_failed_names`/`recorded_passed_names`
parsers (one implementation, never a second one) to diff the per-test verdict set between the
PRIOR recorded testrun output and the NEW one just produced -- grounding every downstream fix on
the delta itself, not a re-read of the full pytest wall of text.
"""
from __future__ import annotations

from typing import Optional

from makoto.checks.namedTestTeeth import recorded_failed_names, recorded_passed_names


def compute_delta(prior_output: str, new_output: str) -> Optional[str]:
    """None when there's nothing to say: no prior run to diff against, or no verdict flipped.
    "Newly failing" = named tests failing now that were NOT already failing in the prior run;
    "newly passing" = named tests passing now that WERE failing in the prior run (a genuine
    fix). A test that was already failing and is STILL failing is neither -- not new information,
    so it stays out of the delta (grounding on what CHANGED, not the whole persistent state)."""
    if not prior_output or not new_output:
        return None
    prior_failed = recorded_failed_names(prior_output)
    new_failed = recorded_failed_names(new_output)
    new_passed = recorded_passed_names(new_output)
    newly_failing = sorted(new_failed - prior_failed)
    newly_passing = sorted(new_passed & prior_failed)
    if not newly_failing and not newly_passing:
        return None
    parts = []
    if newly_failing:
        parts.append(f"{len(newly_failing)} newly failing: {', '.join(newly_failing)}")
    if newly_passing:
        parts.append(f"{len(newly_passing)} newly passing: {', '.join(newly_passing)}")
    return "; ".join(parts)
