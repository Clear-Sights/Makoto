def test_predicates_helpers_module_is_gone():
    import importlib
    try:
        importlib.import_module("makoto.prechecks.helpers")
    except ModuleNotFoundError:
        return
    raise AssertionError("predicates/helpers.py must be DISSOLVED — no shim (CLAUDE.md #4)")
