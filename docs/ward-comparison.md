# Ward vs makoto-dev dispatch — comparison (evidence only, no changes proposed)

Sources read in full: `/workspace/ward/ward/dispatch.py`, `/workspace/ward/hooks/dispatch.sh`,
`/workspace/ward/ward/checks.py`, `/workspace/ward/SECURITY.md`,
`/home/user/makoto-dev/makoto/_dispatch.py`, `/home/user/makoto-dev/makoto/substrate/_loader.py`,
`/home/user/makoto-dev/makoto/substrate/factories.py`.

## 1. Ward's shape

- **One shim script**: `hooks/dispatch.sh` (28 lines) — `cd`s to `$CLAUDE_PLUGIN_ROOT`, verifies
  `ward/dispatch.py` exists and `python3` is on PATH, then execs `python3 -m ward.dispatch`,
  failing closed with a hardcoded deny JSON if any precondition is unmet
  (`/workspace/ward/hooks/dispatch.sh:12-27`).
- **One dispatcher**: `ward/dispatch.py` (79 lines) — `read_event` → `route` → `emit`, all in one
  file, importing exactly one thing from the package (`from ward.checks import evaluate`,
  `/workspace/ward/ward/dispatch.py:12`). `route()` is 8 lines
  (`/workspace/ward/ward/dispatch.py:37-44`): PreToolUse only, one `evaluate()` call, deny-or-`{}`.
- **One ordered CHECKS table**: `ward/checks.py:679-721` — a literal
  `list[tuple[str, str, str]]` of exactly 9 rows (id, description, retry hint), evaluated in table
  order by `evaluate()` (`/workspace/ward/ward/checks.py:736-751`), first match wins. The module's
  own docstring (`/workspace/ward/ward/checks.py:1-20`) states the axis these 9 checks cover
  (danger regardless of intent/honesty) and the invariant every row must satisfy (PreToolUse hard
  block, no softer tier — restated in `dispatch.py`'s own module docstring,
  `/workspace/ward/ward/dispatch.py:1-5`).
- **One SECURITY.md boundary doc**: `/workspace/ward/SECURITY.md` states Ward's guarantee ("a
  policy filter over a PreToolUse event," lines 3-8), explicitly disclaims what it is *not* ("not a
  filesystem confinement boundary or reference monitor," lines 9-16), and enumerates all 9 checks'
  **named non-claims** — exact bypass shapes each predicate deliberately does not catch (lines
  18-42, e.g. `forbidden_location.symlink_resolution`, `jwt_none_alg.variable_allowlist`). It also
  states the required host-side boundary that Ward is not (lines 66-92).
- **Minimal imports**: `dispatch.py` imports only `json`, `sys`, `typing`, and `ward.checks`
  (`/workspace/ward/ward/dispatch.py:6-12`). `checks.py` imports only stdlib
  (`ast, io, json, os, re, textwrap, tokenize, pathlib, typing` —
  `/workspace/ward/ward/checks.py:21-31`). No DB, no network, no cross-module fan-out.

## 2. Where makoto-dev already matches this discipline

- **One dispatcher file, thin orchestrator + row table for routing.** `_dispatch.py`'s `main()`
  (lines 825-867) is a short prologue (parse → verify chain → ingest) that hands off via a literal
  `HANDLERS: dict[str, Any]` table (`makoto/_dispatch.py:816-822`), explicitly modeled on the same
  "a capability is a row, never a module" discipline the comment cites for Detent's MOVES
  (`makoto/_dispatch.py:810-815`). This matches Ward's CHECKS-table discipline in spirit, one level
  up (routing events to handlers, not checks to findings).
- **Fail-closed / fail-open discipline stated up front, matching Ward's stated contract.** Ward:
  "a gate whose machinery cannot even start fails CLOSED" (`ward/dispatch.py:60-63`, mirrored in
  `hooks/dispatch.sh:6-9`). Makoto: `main()`'s docstring states an explicit HYBRID fail-mode
  (tamper-shaped payload → fail closed; transient infra → fail loud-allow; every can't-evaluate
  case is recorded, never silent) at `makoto/_dispatch.py:826-829`, with the same "never silent"
  framing Ward uses.
- **Ordered, first-match evaluation exists at the check level, just implemented differently.**
  Ward's `evaluate()` walks `CHECKS` in list order (`ward/checks.py:747-750`). Makoto's Stop-edge
  loop sorts checks by id and takes the worst finding via `_worst_finding`
  (`makoto/_dispatch.py:541-554`, `599-609`) rather than first-match, but the "one place decides
  the winner" discipline is the same shape.
- **Loader discovery is centralized in one file with a stated, load-bearing contract.**
  `substrate/_loader.py`'s module docstring (lines 1-22) states exactly what makes a file a check
  module (non-underscore-prefixed `.py` under `makoto/checks/`, `.id`/`.applies_at`/`.posture`
  duck-typed) and `scan()`/`discover()`/`load_checks()` (lines 127-177) are the single discovery
  path — comparable to how Ward's `CHECKS` table is the single enumeration path, though Makoto's is
  filesystem-scan-based rather than a literal table.
- **An escape-hatch convention exists and is auditable, matching `ward-allow:`.** Ward's
  `ward-allow: <reason>` (`ward/checks.py:37,48-72`) is mirrored by Makoto's `makoto-allow:
  <reason>` (`makoto/substrate/factories.py:16-34`), both requiring a structured reason (a bare
  marker doesn't exempt) and both recording the suppression rather than silently dropping it
  (Ward: comment-token-bound exemption lines, `checks.py:42-72`; Makoto:
  `_record_exemption`/`set_exemption_sink`, `factories.py:37-63`, wired to an audit sink at
  `makoto/_dispatch.py:63-84`).
- **AST-only, "only active code" scanning shares the exact same mechanism.** Compare
  `factories.py`'s `parse_introduced`/`ast_introduced_predicate`
  (`makoto/substrate/factories.py:139-266`) to Ward's `_parse_introduced`/`_ast_introduced_check`
  (`ward/checks.py:99-202`) — same dedent-then-wrap-in-`if True:` fallback, same "unparseable
  fragment stays silent (FN-safe), never confirmed as active code" rule, same shared-scaffold /
  irreducible-node-match split. The `checks.py` docstring even states these 8 of Ward's 9 checks
  were **ported by shape from Makoto** (`ward/checks.py:1-19`), so this convergence is not
  coincidence — it is common ancestry.

## 3. Where makoto-dev doesn't match Ward's discipline

- **No single boundary doc analogous to SECURITY.md.** Ward's SECURITY.md states, in one place,
  what the whole system does and does not claim, and names 9 specific bypass shapes per check
  (`SECURITY.md:18-42`). Makoto has no equivalent single file. The nearest things are scattered:
  `makoto/_dispatch.py`'s own docstrings state per-mechanism scope/limits inline (e.g.
  `_self_verify_chain`'s "advisory-first, block-after-soak" note, lines 125-132; `_gates_enabled`'s
  FP-rate note, lines 306-321), each check module's own docstring states its own known
  false-negatives ("ACKNOWLEDGED FN" sections referenced at `makoto/substrate/_loader.py:70-73`),
  and `docs/MAKOTO-CONVENTIONS.md` (referenced at `makoto/_dispatch.py:571`) documents the
  `makoto-allow` convention — but no file plays SECURITY.md's role of stating the system's overall
  guarantee and its named non-claims in one place a reader can audit end to end.
- **Ownership of "what is a valid check" is scattered across three files, not one.** Ward's
  entire check contract — table row shape, evaluation order, escape hatch, AST scaffold — lives in
  one file, `ward/checks.py`. Makoto's equivalent concerns are split:
  - `makoto/substrate/_loader.py` owns discovery (`scan`/`discover`/`load_checks`) and the `Check`
    dataclass shape (lines 38-96).
  - `makoto/substrate/factories.py` owns the predicate-building scaffolds (`regex_file_predicate`,
    `ast_introduced_predicate`) and the `makoto-allow` exemption mechanism (lines 1-314).
  - `makoto/core/schema.py` (imported at `makoto/_dispatch.py:30` as
    `load_prechecks, PreCheck, Finding`) owns the Pre-tier catalog/schema that `_run_predicates`
    (`makoto/_dispatch.py:347-396`) consumes, and is a fourth locus (`load_prechecks`) that
    coexists with, but is explicitly stated as not yet superseding,
    `substrate._loader.load_checks` (`makoto/substrate/_loader.py:15-16`).
  A reader has to cross three-plus files to answer "what makes something a check, how is it
  discovered, and how does it fire" — Ward answers all three in one file.
- **No single literal table of every check, id, and description.** Ward's `CHECKS` list
  (`ward/checks.py:679-721`) is inspectable at a glance: 9 rows, each with id + description +
  retry hint, in firing order. Makoto's catalog is instead *discovered* by scanning
  `makoto/checks/*.py` for `CHECK` exports (`substrate/_loader.py:127-164`) plus a
  separately-loaded `load_prechecks()` TOML/schema catalog (`core/schema.py`, not read in full
  here but referenced at `makoto/_dispatch.py:30,357`) — two catalogs, neither a single readable
  table the way Ward's is. (`_blocking_gate_ids()`, `makoto/_dispatch.py:324-344`, is the closest
  thing to a materialized table, but it is a derived `frozenset` of ids, not a readable
  id→description→hint table.)
- **Makoto's dispatcher does much more than dispatch, by design — a very different blast radius
  from Ward's.** Ward's `dispatch.py` has zero I/O beyond stdin/stdout. Makoto's `_dispatch.py`
  owns SQLite lifecycle (`_ensure_db_initialized`, `_connect_with_retry`, lines 144-182), event
  ingestion/pruning (`_ingest_event`, `_prune_old_events`, lines 194-232), ledger/commitment/plan
  state machines (`run_stop_checks`, lines 399-557), posture folding and wire rendering
  (`_emit_decision`, lines 612-643), and audit-row writing (`_record_audit`, lines 646-675) — all
  in one 872-line file. This is not a defect relative to Ward (the two systems have different
  scope: Ward is a pure stateless filter, Makoto is a stateful session-tracking system), but it
  means "one file, minimal imports" is not an available target for Makoto's dispatcher the way it
  is for Ward's — only the *check-catalog* piece of Makoto is a fair comparison to Ward's
  `checks.py`, and that piece is the one that's split across three files (above).
- **No `hooks.sh`-equivalent wiring-failure doc/test pairing visible at the dispatch layer read
  here.** Ward's shim states its own known past failure mode inline (`PYTHONPATH` shadowing,
  `hooks/dispatch.sh:3-9`) and cites the regression test that pins it
  (`tests/test_dispatch_shim.py`). Makoto's `_dispatch.py` does not itself document an analogous
  wiring-failure history for its own hook entrypoint in the file read here (Makoto's own
  `tests/test_dispatch_shim.py` exists but was outside this task's required-reading list, so this
  is a scope note, not a confirmed gap).

## 4. What "reintegrating Ward's model" could mean for makoto-dev

Ranked roughly by how obvious/safe each is, most to least.

1. **OBVIOUS — Write a single `docs/SECURITY.md`-equivalent boundary doc for makoto-dev.**
   Consolidate the guarantee statement and the named non-claims that currently live scattered
   across check docstrings (e.g. `_gates_enabled`'s FP-rate note,
   `makoto/_dispatch.py:306-321`; each check's "ACKNOWLEDGED FN" section per
   `makoto/substrate/_loader.py:70-73`) into one file modeled on Ward's structure (Guarantee →
   Named non-claims per check family → Required host/operator boundary). This is additive
   documentation only, touches no code path, and the source material to draw from already exists
   in the codebase's own comments — the main work is aggregation and cross-referencing with
   file:line citations, not invention.

2. **OBVIOUS — Add a single literal `CHECKS`-style summary table (id, edge, posture, one-line
   description) as a generated or hand-maintained artifact,** distinct from the existing
   `load_checks()`/`load_prechecks()` discovery mechanisms (keep those as the executable source of
   truth; add a readable index alongside them, the way Ward's `CHECKS` list is itself both the
   executable table *and* the readable index because Ward only has 9 rows total). Safe because it
   is either generated from existing discovery functions (no new authority introduced) or,
   if hand-maintained, is checked against `load_checks()`'s output the same way
   `test_checks_taxonomy.py:141-142` already checks non-emptiness — extending that pattern to a
   declared-set-equals-discovered-set assertion (Makoto already has this exact pattern in
   `tests/test_gate_shape.py`'s `EXPECTED_*` declarations, confirmed at
   `tests/test_gate_shape.py:92-113` during Part 2 research) is low-risk.

3. **JUDGMENT-CALL — Consolidate check-catalog ownership from three files
   (`substrate/_loader.py`, `substrate/factories.py`, `core/schema.py`) toward something closer to
   Ward's one-file model.** Ward's single-file design is viable because Ward has 9 checks with one
   evaluation contract. Makoto has ~37 check modules across two coexisting catalogs (the
   `CHECK`-export scan and the still-live `load_prechecks()` TOML/schema path,
   `substrate/_loader.py:15-16`) with genuinely different lifecycles (Pre-tier keyword-prefiltered
   predicates vs. Stop-tier gates consuming `GateContext`). Merging these is a real architectural
   decision about whether the two catalogs should even *be* one thing, not a refactor with an
   obviously-safe destination — needs a human call on whether the Pre/Stop split is essential
   design or accidental history.

4. **JUDGMENT-CALL — Decide whether Makoto's dispatcher should be split the way Ward's
   shim/dispatcher pair is split (thin OS-level shim vs. all-Python dispatcher),** i.e. whether
   `_dispatch.py`'s non-routing responsibilities (DB lifecycle, ledger/plan/commitment state,
   posture folding, audit writing) belong in a *different* file from the routing table itself.
   Ward's separation works because Ward's dispatcher does nothing but route; Makoto's dispatcher
   is intentionally stateful and multi-stage per its own docstring (`makoto/_dispatch.py:1-17`).
   Splitting `HANDLERS`-table routing out from state-management would mirror Ward's "the whole
   routing is one row table, nothing else in the router" discipline, but touches the hot path for
   every hook event and needs a design owner's sign-off on where the new seam goes, not a
   mechanical move.

5. **JUDGMENT-CALL — Whether to fold `load_prechecks()` (schema.py-driven) fully into
   `substrate._loader.load_checks()`,** finishing the migration `_loader.py`'s own docstring
   already flags as incomplete ("coexists with, and does not yet supersede, `schema.load_prechecks`",
   `makoto/substrate/_loader.py:15-16`). This is Makoto's own stated unfinished migration, not a
   Ward-inspired addition — surfaced here because it is the concrete blocker to ever having a
   single Ward-style check table. Left as judgment-call because the migration's scope and risk
   were not evaluated in this task (no code changes were made or the schema.py file read in full).
