"""state/commitments.py is the home of the surfaced-retraction detector + reconcile (spec §4 -
Task 9; relocated from verdict/retraction.py in the Stage-2 directory restructure, seam 2 —
it is commitment-reconciliation logic, so it lives with the commitments store).

The engine-dissolution pins (engine no longer importable; run_stop_checks moved to L3 dispatch)
live in tests/test_dispatch_owns_run_stop_checks.py after Task 10 deleted engine.py."""


def test_commitments_module_owns_the_retraction_cluster():
    from makoto.state import commitments
    for name in ("reconcile", "detect_hidden_retraction", "surfaced_retraction_locations",
                 "_surfaced_retraction_locations", "_fenced_spans",
                 "_retract_interrogative_or_conditional", "_retract_recommitted"):
        assert hasattr(commitments, name), name

# (test_commitments_only_imports_downward moved: the no-upward-edge property — commitments never
# imports verdict/dispatch/a named check — is enforced by tests/test_import_direction.py, seam 7.)
