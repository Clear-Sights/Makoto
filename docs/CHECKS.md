# Checks

GENERATED FILE — do not hand-edit. Produced by `tools/generate_checks_table.py` from
`makoto.substrate._loader.load_checks()`, the same discovery function `_dispatch.py`
itself calls at dispatch time. This table cannot drift out of sync with the real check
registry because it is not a second catalog — it is a rendering of the first one. To
regenerate after adding/removing/editing a check:

```console
$ python3 tools/generate_checks_table.py
```

Total: 36 checks.

| id | edge | posture | description |
|---|---|---|---|
| `content.deferred_checkbox_theater` | Pre | BLOCK | DEFERRED checkbox theater on open T-item |
| `content.env_gated_audit` | Pre | BLOCK | env-gated audit/verification code (if os.environ.get(...)/os.getenv(...) gating an integrity op) |
| `content.fabricated_commit_sha` | Pre | BLOCK | fabricated commit SHA/tag presented as proof of a commit (no git commit/tag ran) |
| `content.illusory_authorship_trailer` | Pre | BLOCK | illusory Claude/Anthropic authorship or generation attribution (Co-Authored-By/Claude-Session/noreply@anthropic.com/"Generated with Claude") in a commit or written content |
| `content.illusory_interruption_claim` | Pre | BLOCK | illusory "interrupted by user" claim (no genuine interruption recorded this session) in a commit or written content |
| `content.integrity_suppression_flag` | Pre | BLOCK | integrity-named suppression flag (_skip/_bypass/_inapplicable=true) in a .toml without ADR backlink |
| `content.phantom_citation` | Pre | BLOCK | phantom citation — Author-Year not in the canonical CITATIONS.md set |
| `content.self_mute_guard` | Pre | BLOCK | makoto self-mute — disabling/un-wiring makoto via settings.json |
| `content.unsourced_webfetch` | Pre | BLOCK | WebFetch URL never seen in any prior tool_result this session |
| `content.verifier_body_hollowed` | Pre | BLOCK | verifier neutered — body hollowed (return-True/pass/assert-True) or a broad except swallows the failure, on the integrity-check surface |
| `content.verifier_exit_masking` | Pre | BLOCK | verifier exit-code masking (\|\| true / ; true / set +e on a test/build/lint runner) |
| `content.verifier_predicate_weakened` | Pre | BLOCK | verifier predicate weakened — loose-comparator shape |
| `event.identical_retry` | Pre | BLOCK | byte-identical Bash retry immediately following that SAME call's deterministic failure -- no intervening state change |
| `event.thrash_revert` | Pre | BLOCK | whole-file A->B->A self-revert (no net progress) |
| `gate.contract_order` | Pre | BLOCK | declared-plan contract gap -- a Write/Edit/MultiEdit/NotebookEdit advances a plan node whose passthrough-establisher is not yet DONE |
| `gate.advance` | Stop | BLOCK | gate.advance |
| `gate.canon` | Stop | BLOCK | gate.canon |
| `gate.canon_fingerprints` | Stop | BLOCK | gate.canon_fingerprints |
| `gate.canon_fingerprints_advisory` | Stop | ADVISE | gate.canon_fingerprints_advisory |
| `gate.claimed_running` | Stop | BLOCK | gate.claimed_running |
| `gate.claimed_shipped` | Stop | BLOCK | gate.claimed_shipped |
| `gate.completion` | Stop | BLOCK | gate.completion |
| `gate.contract_order` | Stop | BLOCK | gate.contract_order |
| `gate.dropped` | Stop | BLOCK | gate.dropped |
| `gate.fabricated_action` | Stop | BLOCK | gate.fabricated_action |
| `gate.green_claim` | Stop | BLOCK | gate.green_claim |
| `gate.hollow_test` | Stop | BLOCK | gate.hollow_test |
| `gate.liveness` | Stop | BLOCK | gate.liveness |
| `gate.named_test` | Stop | BLOCK | gate.named_test |
| `gate.plan_item_drift` | Stop | ADVISE | gate.plan_item_drift |
| `gate.relative_path_citation` | Stop | ADVISE | gate.relative_path_citation |
| `gate.run_promised` | Stop | BLOCK | gate.run_promised |
| `gate.self_wired` | Stop | ADVISE | gate.self_wired |
| `gate.stale_establisher` | Stop | advise | gate.stale_establisher |
| `gate.stale_pass` | Stop | BLOCK | gate.stale_pass |
| `gate.undeclared_falsifiable` | Stop | advise | gate.undeclared_falsifiable |
