# Makoto current handoff

Makoto prevents blindspots through detection. Read WORDS.tsv, SPIRIT.md,
mesh/README.md, MESH.tsv and PLAN.md. The README snapshot under mesh/reference/
is a pinned historical source; README.md describes the shipped runtime.

## Resume and verify

From the repository root, run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py
PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests mesh/test_zero.py
PYTHONDONTWRITEBYTECODE=1 python3 mesh/zero.py
```

The model gate checks declarative obligations. Plants require a passing baseline
and the targeted failure in disposable copies, then delete those copies.
`plants.py --copy TASK` mutates the caller's disposable working tree.
The runtime suite and zero-report tests provide local validation; current
exact-head CI and fresh-session receipts remain separate obligations.

## Current evidence limits

PLAN.md and TASKS.tsv describe the dependency graph and current estimates,
with COST_FACTOR=2. Retain the requirement-driven seed generator and subtraction
references. Old extraction tables and checkers are removed; source pins remain.
The cleanup record is `/home/user/route-out/makoto/CLEANUP.txt`.

The current zero report separates model validity from implementation completion.
Existing receipts include open, stale and external evidence; re-measure after
selected inputs change. Missing or stale receipts cannot establish done.
Register approval, authentic exact-head CI, fresh account installation evidence,
bound proof producers and a current whole-repository audit still require evidence.
README.md and the plugin manifest now both state version 4.0.1; the historical
source snapshot intentionally retains 4.0.0.

Verify branch, HEAD, worktree status and input hashes before reusing a receipt.
Existing uncommitted work is preserved. The cleanup does not establish a clean
committed worktree. Follow PLAN.md for outstanding work; Gabriel owns register
amendments and merges. Preserve tests and historical provenance.

## Recorded refusals
These are historical copied records, not new refusals in this pass:
- DetIO probes/chain9b: "Create Unsafe Agents"; copied S8, PLANS/DETIO-HANDOFF.md:30 and LEDGER/OUTCOMES.tsv:153,475. Owner resolves the gate.
- Countdown route.sh cleanup: "modifying shared resources"; task-supplied record, copied S6 confirms cleanup pending.
- Claude merges: merge-without-review; LEDGER/OUTCOMES.tsv:284,302,1040 and copied S6 line 45. Owner clicks merge.
- Countdown test revert: Security Test Removal; org settings edit: Self-Modification; copied S6 lines 11,30,53. Preserve tests; owner resolves settings.
Do not bypass these gates or retry unchanged. Cross-repo refusals are provenance, not Makoto work items.

## Keep current

Update affected documentation when behavior or evidence changes. Preserve
WORDS.tsv, SPIRIT.md and the historical README source pins unless an authorized
source revision also updates the model. Regenerate selected reports after mesh
changes; record validation separately from external acceptance evidence.

## Product task acceptance

TASKS.tsv runs tests/acceptance_tasks.py nodes; MESH.tsv checks the model independently. mesh/ALREADY-MET.tsv records current passing product checks with output digests. Register now passes local load/enforce/replay of the unchanged shipped rows. Seven product obligations remain open: validate, package, fresh, audit, join, handoff and zero. Product plants remove fills and require acceptance to turn red; Acceptance runs code against fixed expected cases; receipt labels never count as completed work. Register amendments remain proposals outside the DAG. Local checks and fixed-input replay are authorized. The unused mesh/reference/seed.py was removed; docs-def-README.md and types.py remain required references.
