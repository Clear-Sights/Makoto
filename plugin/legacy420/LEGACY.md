This directory preserves the complete tracked tree from
`e8032ec650e2e0361fecc31342ecff16b1e1994d` (the brief's 4.2.0 reference).
The original files, including their historical version labels, are unchanged.
`SOURCE.json` records every original path, SHA-256 digest, and Git file mode.

This runtime is opt-in. The active 5.0 hook imports `plugin/makoto2`; it never
imports this directory. Run the legacy runtime in a separate interpreter so
its original absolute `makoto2` imports resolve to its own modules:

```sh
cd plugin/legacy420/plugin
MAKOTO_STATE_DIR=/tmp/makoto-legacy-state python3 -s -m makoto2 < payload.json
```

Use a separate state directory for the legacy hook. Its historical configuration,
row register, CLI, fixtures, semantic checks, and compatibility exports are all
available here. Current packaging copies this directory along with the active
runtime, and the package smoke test executes the shipped legacy hook.

Run its original regression suite independently:

```sh
cd plugin/legacy420
python3 -m pytest -q --confcutdir=. tests mesh
```

The top-level `conftest.py` prevents collection into the active interpreter;
`tests/test_legacy420.py` checks all original bytes, imports every legacy runtime
and test module in another interpreter, and exercises the legacy hook in both
the source tree and a built package. `tests/acceptance_tasks.py` retains its
original opt-in completion checks, including checks for external evidence;
it is import-smoked but is not an unconditional passing regression suite.

The root `RESTORATIONS.tsv` locates all 403 pieces lost at the starting head.
Every one is restored. The gate's `NOLOSS.tsv` needs only its required header:
there are no claimed replacements or exclusions. The descriptive `NOLOSS-MAP.tsv`
is unchanged.
