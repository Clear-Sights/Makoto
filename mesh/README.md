# Makoto final-program mesh

The mesh starts from WORDS.tsv, SPIRIT.md and the `docs-def` README snapshot in reference/docs-def-README.md. SOURCES.tsv pins these exact inputs. REQUIREMENTS.tsv is the reviewable interpretation of their clauses; foreign project clauses remain explicit scope exclusions. The new owner request supersedes SPIRIT's older six-artifact formation limit.

SLOTS.tsv defines one layer of final-program responsibilities, not Python call sites. Ports use `one[T]` or `many[list[T]]`, `many[set[T]]`, `many[map[K,V]]`; `option[T]` permits absence. Maps and records are open, collection lengths are unrestricted, and no particular implementation algorithm is required. Mathematical payload definitions are constants at the top of check.py. WIRES.tsv gives every opening between these responsibilities, including evidence inputs, output, and state feedback across invocations. Persisted history and fired keys enter at PROGRAM_INPUT on the next invocation; the one-layer graph is deliberately acyclic within an invocation.

Each requirement identifies an actual output port and a finite behavioral partition of that port. Cases read `input-class:permitted-result`; classification is specified by the source-backed text, not by implementation tags. `universe` is the loosest definitely inhabited relation, `allowed` is the upper requirement envelope, and `required` is its lower envelope. Separate requirements on the same port describe separate facets of its behavior. Their accepted relations are intersections of CONSTRAINTS rows for that requirement. The checker computes:

- MISSING-CONSTRAINT = accepted − allowed.
- OVER-CONSTRAINT = required − accepted.

An absent constraint admits the full universe, so it can fail. An empty constraint excludes required behavior, so it can fail. No implementation order, hard collection bound or private algorithm is imposed. TIGHTEN.tsv records the computed descent from unconstrained envelopes to zero. Finite partitions are a declarative abstraction of the source requirements, not a proof of the accuracy of today's recognizers. Source interpretation remains inspectable in REQUIREMENTS.tsv; source changes invalidate the snapshot.

FILLS.tsv maps requirement-needed support units to slots; SLOTS lists the entry bindings. CANDIDATE means only that the unit exists, PARTIAL means some proof code exists, and OPEN means no proof producer is bound. These statuses never certify semantics. Every current runtime/test function is classified: the existing helper functions support the required detection or explicit acceptance tests. No runtime function was found removable solely from these requirements. SUBTRACT.tsv instead removes the old bottom-up extraction and seed units from the active model tools. The old seed unit is identified by original path/name and its preserved AST; replacing seed.py is subtraction of that original unit, not a requirement to delete the new file. No constraint is written for a subtracted unit. The retained reference files are the pinned README snapshot and original types.py required to compare subtraction units. The unused historical seed.py reference was removed; git history retains it. Obsolete reference tables, checkers and tightening logs have been removed.

Regenerate and verify the mesh:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 mesh/seed.py
PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py
PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py
```

check.py parses source with AST; it never imports runtime modules. Every named check is computed and has a hostile plant in plants.py. Plants verify a passing baseline and the targeted failing diagnostic in disposable, credential-free copies, then delete them. `plants.py --copy TASK` supports route's check-after-removal protocol by mutating the caller's current disposable working tree; the caller must create and delete that copy. The model checker does not import the runtime. Product plants execute unit acceptance in disposable copies without installation or network access.

PLAN.md, TASKS.tsv, MESH.tsv and PREDICTIONS.tsv are generated from the wiring. SUBTRACT is first; every ready dependency enters the same wave. Shared source-file writes require one writer or a new scope measurement. Each step predicts PRESENT/ABSENT, cost and a re-measure/EXTERNAL failure edge. No BLOCKED terminal exists in the seed.

A model exit of zero means every declared shape is reachable, traced, type-compatible, neither missing nor over-constrained, and routed. It does not mean the implementation is DONE. Register semantics, current validation, package, fresh-session and audit evidence still must fill the proof slots against the same selected inputs. The final join requires all of them; missing or stale receipts yield not_done. No receipts, external verification, installation or clean-worktree proof are fabricated here. Commit status is reported separately from model validity.

Revision 2026-10-02: `input-sources` declares each slot input's producer independently of WIRES, so deleting a transformed wire produces ADD. `output-from` lists the input ports transformed into each output; a string alias or absent/empty origin is a direct binding and produces FOLD. These are explicit mathematical declarations, not inferred semantics of candidate code. PROGRAM_INPUT has no transformation; its passes fold into the receiving function's local input binding. PROGRAM_OUTPUT is the full I/O sink for transformed function results. FOLD wires are dropped while input provenance remains; no slot merges were needed. The applied WIRE-RULE table retains the revision decisions, while check.py classifies the current mesh afresh.

`tighten.py` starts every requirement facet at its universe, checks that the constraints pass its envelope, then subtracts every optional case. The lower required envelope is the unique least relation by inclusion. Invariant nominal port carriers remain unchanged; independent facets remain separate. It iterates until no set changes and serializes every slot at each step, including the final fixed shape. check.py compares that serialization byte for byte with TIGHTEN.tsv. The kernel candidate-support narrower does not fit these independent relations; see tighten.py for the examined interface and reason.

Use `python3 mesh/wire_rule.py` to inspect current decisions, `python3 mesh/tighten.py` to regenerate tightening, and `python3 mesh/seed.py --plan-only` to regenerate the plan within the mesh/ and PLAN.md revision scope. Plants include an identity wire and stale tightening shape.

Cleanup 2026-10-02: generated Python bytecode was removed. Keep active mesh
infrastructure, subtraction references and `mesh/evidence/` receipts: they are
outputs of checks and historical measurements;
a passing model gate does not make stale receipts current. Re-run
`PYTHONDONTWRITEBYTECODE=1 python3 mesh/zero.py` after changing selected mesh or
plan inputs. It executes every product acceptance and reports open implementation obligations. Cleanup results live outside the repository at
`/home/user/route-out/makoto-r9/CLEANUP.txt`.

TASKS.tsv now selects executable product acceptance in tests/acceptance_tasks.py; TRACE.tsv names each requirement’s test. MESH.tsv keeps its separate model checks. plants.py verifies every product check is red when its fill is removed; an already red evidence task stays open. ALREADY-MET.tsv records only passing product checks, with SHA-256 output digests and retained output under mesh/evidence/product-checks/. Historical receipts alone do not establish current acceptance.

FIX16: register is local load/enforce/replay of the unchanged shipped rows.tsv. Gabriel owns amendments; register-proposal.md is outside the seed DAG. Local pytest, model checks, plants and fixed-input replay are authorized. Proof files are outputs and never accepted as implementation evidence.

Fixed done-tail cleanup 2026-10-02: the current inventory contains no scratch,
temporary, cache or untracked files to remove. All repository files are listed
in the route’s PROTECTED.txt and retained, including plugin metadata, required
references and evidence. The check and plant commands above remain unchanged.
This cleanup records file hygiene; it does not establish implementation completion.
