"""makoto.substrate._declared -- the flat checks/ package's own hand-maintained manifest of
pattern IDs that SHOULD resolve to a live module (SPEC-5 Task 2 Step 6). `{id: file_stem}`.

Every check module landed in this package (Tasks 3-9's ~19 prechecks, ~11 stopchecks, the
merging Assay checks, and the 27 canon fingerprints) is meant to add ONE entry here alongside
dropping in its own `.py` file -- the two are meant to move together.

Only ONE of those two directions is machine-audited, and only over the KEYS. `orphan_ids` (in
`checks.undeclaredFalsifiable`) walks manifest -> reality: an ID listed here that no live
`CHECK.id` matches is reported, which is why this manifest exists at all -- a deleted module, a
module whose `CHECK.id` changed, or an entry that never got a module written for it all leave a
lingering key that gets caught.

Two gaps are NOT covered, and neither is enforced anywhere else:
  * The file_stem VALUES are never read by any code -- `orphan_ids` iterates keys only. They are
    documentation, not a validated mapping, so renaming a module's `.py` file while keeping its
    `CHECK.id` leaves a stem here pointing at a file that no longer exists, silently.
  * The reality -> manifest direction is unaudited. `orphan_modules` reports on-disk modules that
    expose no loader-valid `CHECK`; it never compares the catalog against this manifest, so a
    perfectly live module that was simply never added here is caught by nothing -- and an
    unlisted module has no key to dangle, so its later deletion goes unreported too.
Keeping this file complete and its stems truthful is therefore still a hand-maintenance duty.

Started as exactly the live catalog (just this task's own new check) so the completeness check
reported zero drift at rest; grows by one line per module landed.
"""
DECLARED_IDS: dict[str, str] = {
    "gate.undeclared_falsifiable": "undeclaredFalsifiable",
    # content.cert_verify_disabled, content.jwt_signature_disabled, content.cert_none_mode,
    # content.timing_unsafe_compare, content.jwt_none_alg, content.paramiko_host_key_weakened,
    # content.cert_reqs_none moved to Ward, 2026-07-13 (github.com/Clear-Sights/Ward) -- hard
    # denies with no deterministic substitute, dangerous regardless of intent or honesty, a
    # third axis distinct from this project's sincerity charter.
    "content.verifier_predicate_weakened": "verifierPredicateWeakened",
    "content.env_gated_audit": "envGatedAudit",
    "content.integrity_suppression_flag": "integritySuppressionFlag",
    "content.verifier_exit_masking": "verifierExitMasking",
    "content.verifier_body_hollowed": "verifierBodyHollowed",
    "content.deferred_checkbox_theater": "deferredCheckboxTheater",
    "content.phantom_citation": "phantomCitation",
    "content.unsourced_webfetch": "unsourcedWebfetch",
    "content.fabricated_commit_sha": "fabricatedCommitSha",
    "content.self_mute_guard": "selfMuteGuard",
    "content.illusory_authorship_trailer": "illusoryAuthorshipTrailer",
    "event.thrash_revert": "writeThrashRevert",
    # SPEC-5 Task 4: the stop-gate catalog (formerly makoto/stopchecks/stopcheck_*.py + engines),
    # migrated into this flat package with descriptive names. Declared `.id`s are UNCHANGED from
    # the pre-migration stopchecks/ catalog -- only the filename/import path moved.
    "gate.hollow_test": "hollowTest",
    "gate.liveness": "deadPureStatement",
    "gate.completion": "claimedProduceAbsent",
    "gate.advance": "undischargedCommitment",
    "gate.dropped": "silentlyDroppedCommitment",
    "gate.green_claim": "falseGreenClaim",
    "gate.stale_pass": "stalePytestCache",
    "gate.fabricated_action": "fabricatedToolAction",
    "gate.named_test": "namedTestTeeth",
    "gate.canon": "canonTimeoutRecur",
    "gate.self_wired": "selfWiredCheck",
    # SPEC-5 Task 9: 17 of the 27 canon session fingerprints (THE_CANON,
    # REF-lever-graded-primitives/signalminer/grade_planted.py), split BLOCK/ADVISE across two
    # gate modules that share their atom/decode substrate via _canonAtoms.py (see that module's
    # docstring for the scope cut and canonFingerprints.py's for the two-module split rationale).
    "gate.canon_fingerprints": "canonFingerprints",
    "gate.canon_fingerprints_advisory": "canonFingerprintsAdvisory",
    # SPEC-5 (Makoto absorbs Assay): the declared-Plan / contract-dependency subsystem, ported
    # by shape from Assay's plan/gaps.py + patterns/{contract_order,stale_establisher}.py.
    "gate.contract_order": "contractOrder",
    "gate.stale_establisher": "staleEstablisher",
    # An agnostic (gate.canon-sense) claimed-running-but-nothing-runs check, mirroring
    # gate.completion's claim-vs-ledger shape but for ongoing process/service liveness.
    "gate.claimed_running": "claimedRunningAbsent",
    # The forward-looking sibling of gate.claimed_running: a first-person run-intent promise
    # ("I'll run the tests") left with no Bash evidence anywhere in history by the next turn.
    "gate.run_promised": "runIntentUnfulfilled",
    # Immediate completed-remote-action sibling: a pushed/merged/live claim must be backed by a
    # successful Bash git-push or an explicitly recognized remote-mutating tool call.
    "gate.claimed_shipped": "claimedShippedAbsent",
}
