# Makoto SEED derived from MESH

## Derivation verdict
IMPOSSIBLE under the literal current checks: four required predicates contain unconditional `&& false`, while distance 0 requires all nine checks to pass. This is a contradiction in the goal terms, not an external failure. Nearest restatement: preserve the nine semantic acceptance bars, replace the four provisional false checks with deciding semantic/receipt/content checks and hostile plants, and normalize route citations and plant behavior. That restatement requires a separately authorized MESH change; EXTRA is none in this pass. The graph below is the complete remaining obligation graph for that restatement, not a claim that the unchanged MESH can reach zero.

## Law and measurement
Owner instruction, Gabriel 2026-10-02 01:05–01:07Z: "countdown cannot fail that's kinda the point, it's a literal countdown to perfect via the shortest possible route". This quotation is supplied in the task; it is absent from the current WORDS.tsv and is not assigned a fabricated row id. WORDS.tsv WHY supplies the existing shortest-path purpose; DONE supplies packaged, installed, fresh-session proof and whole-current-repo cleanliness.
Distance is the number of unmet semantic MESH holes. Starting recorded distance: 5 of 9. Four recorded met holes remain invariants: rule-behavior, observation, hook-output, source-pins. No MESH checks or plants were run for this derivation; statuses are reused only as recorded, not freshly certified. Recheck affected invariants after implementation and reopen them on a measured miss.
No local implementation miss is terminal: re-measure distance from current state and re-derive. Re-plan on cost overruns, changed inputs or invalid evidence. Only an entirely external cause has an EXTERNAL edge. The sole logical stop is contradictory goal terms, reported as IMPOSSIBLE with the nearest restatement above.

## Route input contract and scope
TASKS.tsv uses task, deps, brief, inputs, check, hand, piece, citation, estimate_tokens. Inputs are relative modifiable future paths, not permission to edit them during this seed pass. Each task keeps the exact MESH check and piece; task citations use the resolvable WORDS.tsv DONE key. Original MESH citation for every step is `SPIRIT.md: ## Acceptance checks`; its acceptance prose remains authoritative, but that literal string is not recognized by route-intent.py (see LACKS.md).
No hooks, credentials, publishing, pushing or merging are authorized. Owner approval applies to register amendments and fresh-session operations; hand=yes expresses that boundary. Other workers must not handle credentials. External public evidence may be read in a later authorized execution. This pass edits only PLAN.md, TASKS.tsv, LACKS.md and untracked VERDICT-SEED.txt.
Route config sources: REPO_DIR=/home/user/makoto; MESH_FILE=MESH.tsv; SEED_FILE=PLAN.md; WORDS_FILES=WORDS.tsv,SPIRIT.md; WHY=the verbatim WORDS.tsv WHY row. No runnable GATE_CMD/PLANTS_CMD pair can certify the unchanged contradictory checks and incompatible plants; do not invent successful commands or launch route tail (which commits/pushes). No PROJECT.env is created.

## Dependency graph and WAVES
Wave 1: register-alignment || package-consistency. Wave 2: fresh-installation || complete-validation, each after both wave-1 steps. Wave 3: whole-repo-clean after both wave-2 steps. These are all five not-met holes, including statuses labeled blocked in the input. Independent work shares no implementation outputs: register changes preserve package metadata; wave-2 validators use separate test files. A discovered overlap requires re-derivation.
Three waves maximize concurrency for these evidence dependencies: both final-behavior proofs need aligned rules and a selected package; the final audit needs both proofs. Wave-2 receipts must bind the same final implementation inputs, including their validators. Changing those inputs reopens affected proofs rather than accepting stale receipts. The final audit is semantic validation, not an additional route-tail publish/cleanup task.
Predicted distance trajectory after successful waves: 5 → 3 → 1 → 0. Estimated implementation effort: 31,000 tokens, 155 worker-minutes; wave critical path 60 + 30 + 30 = 120 minutes excluding external waits. Estimates are planning budgets, not success evidence.

### WAVE 1 — register-alignment
- id: register-alignment
- depends-on: none
- piece: owner-approved register and regression attribution
- citation: WORDS.tsv DONE; WORDS.tsv WHY; MESH provenance `SPIRIT.md: ## Acceptance checks`
- action: Recover public pushed register audit inputs in a disposable checkout or reconstruct missing inputs from cited obligations; account for all 33 historical replay regressions, 61 unresolved shapes and four conflicts against current evidence; obtain Gabriel approval of predicates and attributed amendments; preserve source pins and subject binding; prove each retained family with slip and silent-control cases.
- predicted PRESENT: owner-approved current register, verbatim citations, attributed removals, shared family cases and complete replay accounting.
- predicted ABSENT: uncited predicates, unexplained regressions, unresolved current shapes/conflicts and weakened subject binding.
- predicted cost: 12000 tokens; 60 worker-minutes; external wait unbounded.
- deciding MESH check (verbatim): `test -s REGISTER.md && test -s CITATIONS.tsv && test -s REPLAY.tsv && test -s REGISTER-PROPOSAL.md && false`
- failure edge: re-measure distance from current state and re-derive.
- entirely external edge: EXTERNAL: Gabriel register approval unavailable or public audit source service unavailable.


### WAVE 1 — package-consistency
- id: package-consistency
- depends-on: none
- piece: version and marketplace agreement
- citation: WORDS.tsv DONE; WORDS.tsv WHY; MESH provenance `SPIRIT.md: ## Acceptance checks`
- action: Reconcile README title with the selected manifest version and retain marketplace source ./plugin; do not install or configure hooks. Register work preserves this package invariant; if it changes package inputs, re-measure and re-derive dependencies.
- predicted PRESENT: README title equal to # Makoto plus manifest version, and marketplace source ./plugin.
- predicted ABSENT: version disagreement and invalid marketplace source.
- predicted cost: 2000 tokens; 10 worker-minutes; external wait unbounded.
- deciding MESH check (verbatim): `python3 -c 'import json,pathlib; v=json.load(open("plugin/.claude-plugin/plugin.json"))["version"]; assert pathlib.Path("README.md").read_text().splitlines()[0]=="# Makoto "+v; m=json.load(open(".claude-plugin/marketplace.json")); assert m["plugins"][0]["source"]=="./plugin"'`
- failure edge: re-measure distance from current state and re-derive.
- entirely external edge: EXTERNAL: execution host unavailable.


### WAVE 2 — fresh-installation
- id: fresh-installation
- depends-on: register-alignment,package-consistency
- piece: fresh account behavioral receipt
- citation: WORDS.tsv DONE; WORDS.tsv WHY; MESH provenance `SPIRIT.md: ## Acceptance checks`
- action: For the final selected implementation revision, obtain a public source-pinned receipt from an owner-operated fresh account/session proving intended version loaded, actual slip blocked, look-alike silent and no runtime errors through an existing hook-free entry point; implement deterministic receipt validation and missing-plugin sensitivity. If no such entry point exists, re-derive an authorized hook-free implementation rather than claiming installation.
- predicted PRESENT: current revision/version-bound fresh-session receipt with observed slip/control results and missing-plugin rejection.
- predicted ABSENT: historical-only receipts, another version, fabricated observations, runtime errors and hook or credential installation.
- predicted cost: 6000 tokens; 30 worker-minutes; external wait unbounded.
- deciding MESH check (verbatim): `test -s FRESH-INSTALL-RECEIPT.tsv && false`
- failure edge: re-measure distance from current state and re-derive.
- entirely external edge: EXTERNAL: owner-operated fresh account/session unavailable or installation service unavailable.


### WAVE 2 — complete-validation
- id: complete-validation
- depends-on: register-alignment,package-consistency
- piece: local suite and exact-head CI
- citation: WORDS.tsv DONE; WORDS.tsv WHY; MESH provenance `SPIRIT.md: ## Acceptance checks`
- action: Run all local tests and affected met-hole checks; obtain public receipts for all five CI jobs on the exact final selected implementation head; implement deterministic revision/job receipt validation with wrong-revision rejection. Receipt-only changes must not be called new implementation proof; any tested-input change invalidates receipts and triggers re-derivation.
- predicted PRESENT: passing local suite, preserved four met-hole bars and five green exact-implementation-head CI receipts.
- predicted ABSENT: failing local checks, skipped/missing required jobs, another-head receipts and stale input pins.
- predicted cost: 5000 tokens; 25 worker-minutes; external wait unbounded.
- deciding MESH check (verbatim): `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests && test -s CI-RECEIPT.tsv && false`
- failure edge: re-measure distance from current state and re-derive.
- entirely external edge: EXTERNAL: remote CI service unavailable or required owner-triggered CI run unavailable.


### WAVE 3 — whole-repo-clean
- id: whole-repo-clean
- depends-on: fresh-installation,complete-validation
- piece: whole current content audit and clean worktree
- citation: WORDS.tsv DONE; WORDS.tsv WHY; MESH provenance `SPIRIT.md: ## Acceptance checks`
- action: Audit all current tracked and ignored non-history content with credential contents excluded from worker access; verify evidence and current input pins, remove authorized stale/dead/duplicate material, implement content verification with a harmless synthetic-secret plant, and prove clean durable checkout after accepted changes are committed. Finalize receipt/checker changes before selecting the final implementation head; re-measure if this audit changes tested inputs. Keep the requested untracked verdict outside the eventual execution checkout rather than weaken cleanliness.
- predicted PRESENT: current-content audit, current pins, planted synthetic-secret rejection, durable clean worktree and all nine acceptance bars met.
- predicted ABSENT: credentials/private infrastructure in deliverable, stale/dead/duplicate content, unexplained worktree changes and unmeasured input changes.
- predicted cost: 6000 tokens; 30 worker-minutes; external wait unbounded.
- deciding MESH check (verbatim): `git diff --check && test -z "$(git status --porcelain --untracked-files=all)" && false`
- failure edge: re-measure distance from current state and re-derive.
- entirely external edge: EXTERNAL: filesystem or authorized commit service unavailable.

## Distance 0
The seed ends only when all nine current semantic checks pass against the same selected inputs, hostile plants reject removed prerequisites, installed behavior is proven in a fresh session, the package agrees, and the whole durable repository is clean outside history. Under the nearest restatement, successful wave 3 measures distance 0. Under unchanged literal MESH, distance 0 is IMPOSSIBLE; an estimated trajectory never substitutes for measurement.
