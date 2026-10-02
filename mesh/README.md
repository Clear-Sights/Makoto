# Makoto final-program mesh

The mesh starts from WORDS.tsv, SPIRIT.md and the `docs-def` README snapshot in reference/docs-def-README.md. SOURCES.tsv pins these exact inputs. REQUIREMENTS.tsv is the reviewable interpretation of their clauses; foreign project clauses remain explicit scope exclusions. The new owner request supersedes SPIRIT's older six-artifact formation limit.

SLOTS.tsv defines one layer of final-program responsibilities, not Python call sites. Ports use `one[T]` or `many[list[T]]`, `many[set[T]]`, `many[map[K,V]]`; `option[T]` permits absence. Maps and records are open, collection lengths are unrestricted, and no particular implementation algorithm is required. Mathematical payload definitions are constants at the top of check.py. WIRES.tsv gives every opening between these responsibilities, including evidence inputs, output, and state feedback across invocations. Persisted history and fired keys enter at PROGRAM_INPUT on the next invocation; the one-layer graph is deliberately acyclic within an invocation.

Each requirement identifies an actual output port and a finite behavioral partition of that port. Cases read `input-class:permitted-result`; classification is specified by the source-backed text, not by implementation tags. `universe` is the loosest definitely inhabited relation, `allowed` is the upper requirement envelope, and `required` is its lower envelope. Separate requirements on the same port describe separate facets of its behavior. Their accepted relations are intersections of CONSTRAINTS rows for that requirement. The checker computes:

- MISSING-CONSTRAINT = accepted − allowed.
- OVER-CONSTRAINT = required − accepted.

An absent constraint admits the full universe, so it can fail. An empty constraint excludes required behavior, so it can fail. No implementation order, hard collection bound or private algorithm is imposed. TIGHTEN.tsv records the computed descent from unconstrained envelopes to zero. Finite partitions are a declarative abstraction of the source requirements, not a proof of the accuracy of today's recognizers. Source interpretation remains inspectable in REQUIREMENTS.tsv; source changes invalidate the snapshot.

FILLS.tsv maps requirement-needed support units to slots; SLOTS lists the entry bindings. CANDIDATE means only that the unit exists, PARTIAL means some proof code exists, and OPEN means no proof producer is bound. These statuses never certify semantics. Every current runtime/test function is classified: the existing helper functions support the required detection or explicit acceptance tests. No runtime function was found removable solely from these requirements. SUBTRACT.tsv instead removes the old bottom-up extraction and seed units from the active model tools. The old seed unit is identified by original path/name and its preserved AST; replacing seed.py is subtraction of that original unit, not a requirement to delete the new file. No constraint is written for a subtracted unit. Old artifacts live only under reference/.

Run only these model tools during formation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 mesh/seed.py
PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py
PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py
```

check.py parses source with AST; it never imports runtime modules. Every named check is computed and has a hostile plant in plants.py. Plants verify a passing baseline and the targeted failing diagnostic in disposable, credential-free copies, then delete them. `plants.py --copy TASK` supports route's check-after-removal protocol and leaves one private copy whose path is printed. Checks do not invoke hooks, test collection, gates, installation, git writes or network access.

PLAN.md, TASKS.tsv, MESH.tsv and PREDICTIONS.tsv are generated from the wiring. SUBTRACT is first; every ready dependency enters the same wave. Shared source-file writes require one writer or a new scope measurement. Each step predicts PRESENT/ABSENT, cost and a re-measure/EXTERNAL failure edge. No BLOCKED terminal exists in the seed.

A model exit of zero means every declared shape is reachable, traced, type-compatible, neither missing nor over-constrained, and routed. It does not mean the implementation is DONE. Register semantics, current validation, package, fresh-session and audit evidence still must fill the proof slots against the same selected inputs. The final join requires all of them; missing or stale receipts yield not_done. No receipts, external verification, installation or clean-worktree proof are fabricated here. Requested changes remain uncommitted.
