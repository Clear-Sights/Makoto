# MAKAUDIT findings ledger

Audit date: 2026-07-26. Baseline: commit `36c434f` was read in full before the sweep. The audit
walked all 15 Pre checks and all 21 discovered Stop surfaces (19 `may_block` surfaces plus the two
structurally advisory-only surfaces), their dispatcher wiring, the history/ledger ingest paths, and
the existing behavioral batteries. Findings are ranked by whether they can affect a blocking gate.

The literal first baseline run was host-invalid because inherited `commit.gpgsign=true` called an
unavailable signing service from tests that create temporary repositories:
`22 failed, 1629 passed, 1 skipped, 1 xfailed in 38.81s`. With signing disabled only through
process-local Git config (no repository/global config write), the valid baseline was:
`1651 passed, 1 skipped, 1 xfailed in 29.93s`.

## Fixed: six (FP, TP) pairs

| Tier | Defect and fix | FP test | TP test |
|---|---|---|---|
| BLOCK | `_dispatch._select_recent` sorted sequence evidence by non-monotonic wall time. It now orders by the ingest id, the same monotonic fact the ledger already trusts. | `test_fp_stop_history_uses_ingest_order_when_wall_clock_moves_backward` | `test_tp_stop_history_keeps_later_error_last_when_clock_moves_backward` |
| BLOCK | `ledger._upsert` replaced a colliding row's value but retained its old `session_id`, attributing another session's failure to the first session. Ownership now advances with the value. | `test_fp_cross_session_upsert_never_attributes_second_sessions_failure_to_first` | `test_tp_cross_session_upsert_attributes_failure_to_session_that_ran_it` |
| BLOCK | `decode_history_row` returned valid non-object JSON, then `iter_tool_events` called `.get` and silenced the affected Stop check through the per-check exception catcher. Non-dict envelopes are now skipped. | `test_fp_non_object_history_payload_is_inert_for_named_test_gate` | `test_tp_non_object_history_payload_does_not_hide_later_failed_named_test` |
| BLOCK | `is_test_runner` searched raw command text, so `cat pytest.log` made old failure text into a new `testrun` and falsely blocked a green claim. Test provenance now uses literal argv segments. | `test_fp_green_claim_ignores_failure_text_read_from_pytest_log` | `test_tp_green_claim_still_blocks_after_real_pytest_failure` |
| BLOCK | shipping evidence searched raw Bash text, so `echo 'git push origin main'` discharged a fabricated push. The same argv normalizer now requires a real, non-dry-run `git push`; real `git -C … push` is recognized. | `test_fp_real_git_push_still_discharges_claimed_shipped` | `test_tp_echoed_git_push_cannot_discharge_claimed_shipped` |
| BLOCK | The corpus harness asserted zero raw hollow-test fires while its own fixture names one deliberate hollow as the pinned TP. The expected set is now that exact function; the live adapter still honors its explicit exemption. | `test_fp_intentional_hollow_allow_remains_silent_in_live_adapter` | `test_tp_intentional_hollow_remains_detectable_before_exemption` |

Unfixed trace for the new file: `8 failed, 2 passed in 0.21s`. Fixed focused trace (new pairs plus
the affected prior batteries): `215 passed in 0.53s`.

Plant: `_select_recent` was deliberately changed back from `ORDER BY id` to `ORDER BY ts`.
`test_tp_stop_history_keeps_later_error_last_when_clock_moves_backward` went RED:
`1 failed in 0.25s`. The fix was restored and its pair returned `2 passed in 0.23s`.

During final verification the live MAKREL job published a sibling `/workspace/makoto` corpus whose
deliberate hollow fixture exposed the harness contradiction above:
`1 failed, 1660 passed, 1 skipped, 1 xfailed in 29.64s`. After correcting the exact expected TP
set, the final full suite was: `1663 passed, 1 skipped, 1 xfailed in 27.78s`.

## Unfixed findings

Count: **10** — **9 BLOCK-impacting**, **1 ADVISE**. These are not style requests; each is a
specific false decision or silent-failure path.

1. **BLOCK — the ledger still cannot retain two sessions at one key.**
   `makoto/record/db.py:66-75` makes `key` the sole primary key and
   `makoto/record/ledger.py:67-76` upserts on that key. The landed ownership fix prevents a false
   attribution, but a later session still erases the earlier session's evidence; executed
   reproduction: `older_session_evidence_erased=True`. A complete fix requires a schema migration
   to a composite `(session_id, key)` identity (and decisions for the sessionless `read_key` CLI),
   not another upsert tweak. That migration is too broad for a zero-FP audit pass.

2. **BLOCK — truncated stdin bypasses every check.**
   `makoto/_dispatch.py:832-840` maps invalid/truncated JSON to loud-allow exit 0. This was found by
   following the external-input path from `sys.stdin.read()` to its terminal disposition; the code
   explicitly confirms the bypass. A fix needs host-level framing/retry or a product decision to
   block malformed pipes. Treating every transient truncation as tamper could itself stop honest
   sessions, so this pass does not spend the FP claim.

3. **BLOCK — a broken check can disappear at import time.**
   `makoto/substrate/_loader.py:127-163` converts import errors and malformed `CHECK`/`EXTRA_CHECKS`
   exports to `None`/skip. `gate.undeclared_falsifiable` can advise only if it itself still imports;
   it is not an independent root of trust. Existing taxonomy fault-injection tests deliberately
   prove the skip. A fix needs a manifest outside the scanned package or a loader error surface
   whose own import cannot disappear with the catalog; failing closed on arbitrary import errors
   would risk bricking every Stop.

4. **BLOCK — runtime check exceptions are silent.**
   `makoto/_dispatch.py:541-557` catches both each `check.run` exception and any outer Stop failure
   without recording even the dispatch-error fact used by Pre checks. The malformed-envelope fix
   closes one executed trigger, not the general shape. A fix must thread the audit root/event id
   into `run_stop_checks` and record the exact failed check while preserving evaluation of siblings;
   changing fail-open policy to block needs separate FP evidence.

5. **BLOCK — the one-hour history window can false-block a truthful running claim.**
   `makoto/_dispatch.py:235-243` drops older events; `claimedRunningAbsent.py:52-56,121-129` then
   interprets no visible launch as unfulfilled even when a still-running process was launched 61
   minutes earlier. The module already names this limit. A fix needs a durable process identity
   (PID/port/service) and live probe, not a larger arbitrary window.

6. **BLOCK — pooled process evidence has no target coreference.**
   `makoto/checks/claimedRunningAbsent.py:42-50,95-109` lets the latest unrelated lifecycle-shaped
   call decide the claim. Executed fault: a successful `python -m http.server 8000` followed by an
   unrelated failing `curl localhost:9999/health` blocks “I started the server and it is running.”
   Fixing it requires extracting and matching process/port identity across prose and commands; a
   loose match would create new false blocks.

7. **BLOCK — any current-turn tool call backs a claimed concrete action.**
   `makoto/checks/fabricatedToolAction.py:70-81` silences “I ran `scripts/deploy.sh`” after an
   unrelated `Read`; the existing battery and a direct replay both prove it. A safe fix needs
   command/action coreference while retaining non-Bash tool aliases and paraphrases. Substring
   matching would repeat the command-evidence defect fixed above.

8. **BLOCK — any Bash call discharges any run promise.**
   `makoto/checks/runIntentUnfulfilled.py:96-122` lets `pwd` discharge “I'll run the tests now”;
   executed reproduction returned silent. A fix needs promise-to-command classification and
   coreference across runner, service, and deploy vocabularies, with an explicit unknown case.

9. **BLOCK — any successful remote mutation backs any shipping claim.**
   `makoto/checks/claimedShippedAbsent.py:78-109` lets `git push origin docs` discharge “I merged
   PR #42.” The argv fix proves the command ran, but not that it is the claimed deed. A fix needs
   target/ref/PR coreference across Bash and closed MCP tool inputs without guessing.

10. **ADVISE — an unreadable chain verifies as intact.**
    `makoto/record/ledger.py:303-318` returns `None` for both a valid/absent chain and `OSError`;
    `_self_verify_chain` therefore cannot distinguish loss of access from integrity. The chain
    self-check is advisory today, so this cannot block. A fix needs a three-state result
    (`intact`, `broken(index)`, `unevaluable(error)`) and caller/receipt migration.

No performance change was landed: the audit found no measured Stop-path regression that justified
changing behavior. The existing `os.walk` prohibition remains intact.
