"""Tests for tests.mint_event_gold -- Task 1's per-event mutation minter.

Two jobs, both load-bearing: (1) confirm the 3 representative real detectors have real per-event
ground truth (fp=False, fn=False) over their own minted fixtures; (2) prove the minter ITSELF is
falsifiable (Task 1's done-bar) -- a deliberately broken detector fed through the SAME
mint_and_check/mint_all machinery must redden its own minted set, in both directions (always-
silent -> fn=True; always-firing -> fp=True). Without this second half, a minter that always
reports "clean" would be indistinguishable from a real one.
"""
from __future__ import annotations

from tests.mint_event_gold import CATALOG, MintedDetector, mint_all, mint_and_check


# ---- the 3 representative categories the plan's own Verification section names -----------------
def test_catalog_covers_all_three_named_categories():
    categories = {d.category for d in CATALOG.values()}
    assert categories == {"content-scan-1.x", "event-shape", "stop-gate"}


def test_verifier_weakened_has_clean_per_event_ground_truth():
    report = mint_and_check(CATALOG["content.verifier_predicate_weakened"])
    assert report["fired_on_negative"] is False, "must NOT fire on a clean `==` comparison"
    assert report["fired_on_positive"] is True, "must fire on the SAME comparison loosened to .startswith()"
    assert report["fp"] is False and report["fn"] is False


def test_identical_retry_has_clean_per_event_ground_truth():
    report = mint_and_check(CATALOG["event.identical_retry"])
    assert report["fired_on_negative"] is False, "must NOT fire with no prior history"
    assert report["fired_on_positive"] is True, "must fire on the SAME retry preceded by its own deterministic failure"
    assert report["fp"] is False and report["fn"] is False


def test_named_test_gate_has_clean_per_event_ground_truth():
    report = mint_and_check(CATALOG["gate.named_test"])
    assert report["fired_on_negative"] is False, "must NOT fire when the claim matches a recorded PASS"
    assert report["fired_on_positive"] is True, "must fire on a claimed-pass-over-a-recorded-FAILED"
    assert report["fp"] is False and report["fn"] is False


def test_mint_all_reports_every_catalog_entry():
    report = mint_all()
    assert set(report) == set(CATALOG)
    assert all(r["fp"] is False and r["fn"] is False for r in report.values())


# ---- the minter's OWN falsifiability (Task 1's done-bar) ----------------------------------------
def test_minter_is_falsifiable_always_silent_detector_reddens_fn():
    broken = MintedDetector(id="broken-silent", category="stop-gate",
                            negative="anything", positive="anything", run=lambda f: False)
    report = mint_and_check(broken)
    assert report["fn"] is True, "an always-silent detector must redden fn on its own minted set"
    assert report["fp"] is False


def test_minter_is_falsifiable_always_firing_detector_reddens_fp():
    broken = MintedDetector(id="broken-loud", category="stop-gate",
                            negative="anything", positive="anything", run=lambda f: True)
    report = mint_and_check(broken)
    assert report["fp"] is True, "an always-firing detector must redden fp on its own minted set"
    assert report["fn"] is False


def test_minter_is_falsifiable_via_mint_all_with_an_injected_catalog():
    broken = MintedDetector(id="broken-silent", category="event-shape",
                            negative="x", positive="y", run=lambda f: False)
    report = mint_all({"broken-silent": broken})
    assert report["broken-silent"]["fn"] is True
