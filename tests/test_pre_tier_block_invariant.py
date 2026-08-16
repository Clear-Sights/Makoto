"""Pins the Pre-tier BLOCK-only invariant (warning-tier-elimination) now that it is no longer
re-enforced at load time by `schema.load_prechecks()` (retired 2026-08-16 -- migrated to
`substrate._loader.load_checks`/`load_precheck_catalog`, which do not raise on a bad posture).

makoto has no non-blocking Pre-tier resting state: a Pre-tier check either BLOCKs (proven
material) or is CUT. This test is the sole remaining enforcement of that invariant for the
Pre-tier catalog -- if it starts failing, a Pre-tier check shipped with a non-BLOCK posture and
must be fixed or removed, not softened.
"""
from makoto.substrate._loader import load_precheck_catalog


def test_every_pre_tier_check_is_block_posture():
    live = load_precheck_catalog()
    assert live, "Pre-tier catalog must be non-empty"
    bad = {c.id: c.posture for c in live if str(c.posture).strip().upper() != "BLOCK"}
    assert not bad, f"Pre-tier checks must all be posture=BLOCK (or be cut): {bad}"
