"""retraction.py is the L2 home of the surfaced-retraction detector + reconcile (spec §4 - Task 9).

The engine-dissolution pins (engine no longer importable; run_stop_checks moved to L3 _dispatch)
live in tests/test_dispatch_owns_run_stop_checks.py after Task 10 deleted engine.py."""


def test_retraction_module_owns_the_retraction_cluster():
    from makoto import retraction
    for name in ("reconcile", "detect_hidden_retraction", "surfaced_retraction_locations",
                 "_surfaced_retraction_locations", "_fenced_spans",
                 "_retract_interrogative_or_conditional", "_retract_recommitted"):
        assert hasattr(retraction, name), name


def test_retraction_only_imports_downward():
    # L2 retraction may import L1 (checks) + L0 (lexicons) + stdlib only - no L2 sibling, no upward edge.
    import ast, inspect
    from makoto import retraction
    tree = ast.parse(inspect.getsource(retraction))
    makoto_mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("makoto."):
            makoto_mods.add(n.module)
    assert makoto_mods == {"makoto.checks", "makoto.lexicons"}, makoto_mods
