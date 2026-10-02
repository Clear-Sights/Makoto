# Makoto: top-down seed from final-program wiring

Requirements open ports; transformed wires order work. Raw program inputs are local slot bindings (SLOTS input-sources). WIRE-RULE.tsv records the applied classification; wire_rule.py rejects identity wires and detects missing transformed passes. Layer 1 closes only source-backed definite constraints. Layers 2+ use signed deterministic feedback within that closed space: surplus deletion reduces excess, while required deletion increases missing and is forbidden. SymPy simplifies every slot relation before and after the loop. tighten.py computes the least finite requirement relations to a fixpoint, and check.py rejects a stale TIGHTEN.tsv. SUBTRACT is first. Each later wave contains every ready slot, giving maximal concurrency under this one-layer dependency graph. Candidate units in shared files must be edited by one writer or re-measured into disjoint scopes; evidence files are per slot.

The shape model passes independently of implementation. OPEN, PARTIAL and CANDIDATE are explicit implementation absences, not proof receipts. TASKS check the declared model obligations; they do not run hooks, gates or certify implementation completion. PREDICTIONS.tsv records this distinction. Each task brief predicts PRESENT/ABSENT and a token cost from mesh/COSTS.tsv. Each task uses the cheapest passing measured run of its class across repositories; classes without a passing run use the largest passing run of any class. A class is the task-name prefix before the first hyphen (including subtract and fill). Failed attempts never set estimates. The project rule stops a job over twice its cheapest logged passing run of the same class.

Failure edges are re-measure and re-derive, or EXTERNAL for unavailable owner decisions, current CI receipts, installation or audit evidence. EXTERNAL returns to the same slot on changed input. There is no BLOCKED terminal and no countdown decrement for stale or absent evidence. The join emits done only when every current proof input is present.

Route TASKS format: /home/user/mz-route/tools/route/route-USAGE.md and route-digest.md. All MESH rows correspond to task ids and have plants that mutate the current disposable working tree. This is a reviewable plan; route execution and its tail are outside this request. Register amendments require Gabriel; merging remains with Gabriel.

Configuration for a later authorized model-only route:
```text
REPO_DIR=/home/user/makoto
WHY=Makoto prevents blindspots through detection
WORDS_FILES=WORDS.tsv,SPIRIT.md,mesh/reference/docs-def-README.md
MESH_FILE=MESH.tsv
SEED_FILE=PLAN.md
GATE_CMD=PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py
PLANTS_CMD=PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py
```

These are declarations, not commands executed during formation. Model checks do not replace the product acceptance gates.

Wave 1: subtract (predicted 208231 tokens)
Wave 2: configure, decode (predicted 1187212 tokens)
Wave 3: observe, rules (predicted 1187212 tokens)
Wave 4: evaluate, register (predicted 1187212 tokens)
Wave 5: once (predicted 593606 tokens)
Wave 6: advance, emit (predicted 1187212 tokens)
Wave 7: persist, validate (predicted 1187212 tokens)
Wave 8: package (predicted 593606 tokens)
Wave 9: audit, fresh (predicted 1187212 tokens)
Wave 10: join (predicted 593606 tokens)
Wave 11: handoff (predicted 593606 tokens)
Wave 12: zero (predicted 593606 tokens)

At the final zero step: model distance = missing + over + structural violations = 0. Implementation distance reaches 0 only after current register, validation, package, fresh-session and whole-repo evidence realize the join contract. No such external receipts are invented in this pass.

Required route outputs: each slot owns its declared mesh/evidence/<slot>.json receipt; register also owns mesh/evidence/register-proposal.md. The zero task writes mesh/evidence/zero.json by running PYTHONDONTWRITEBYTECODE=1 python3 mesh/zero.py. These files are retained proof artifacts for measurement and handoff, including reports of missing or external evidence. Zero reads mesh/, PLAN.md, TASKS.tsv and MESH.tsv without changing them; its output excludes itself from source pins. Model zero and implementation completion remain separate.

Scope: final Makoto detection, portable handoff, proof interfaces and seed. Foreign DetIO/Tiller/Countdown clauses are exclusions. Historical docs and old mesh artifacts are reference; no hook invocation/configuration, credentials, gate runs, publishing or merges.
