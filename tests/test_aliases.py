"""checks/_aliases.py -- SPEC-C item 3 (one namespace). A legacy id must resolve to its current
canonical form FOREVER, so a rename never breaks an operator's existing MAKOTO_DISABLE_PATTERNS
config or a script/dashboard matching on the old string.
"""
from makoto.substrate._aliases import LEGACY_TO_CANONICAL, canonical, is_legacy


def test_known_legacy_ids_resolve_to_their_canonical_form():
    assert canonical("makoto.contract_order") == "gate.contract_order"
    assert canonical("makoto.stale_establisher") == "gate.stale_establisher"
    assert canonical("write.thrash_revert") == "event.thrash_revert"
    assert canonical("makoto.forbidden_location") == "event.forbidden_location"
    assert canonical("makoto.identical_retry") == "event.identical_retry"


def test_an_unaliased_id_resolves_to_itself():
    assert canonical("gate.completion") == "gate.completion"
    assert canonical("some.unknown.id") == "some.unknown.id"


def test_is_legacy_distinguishes_aliased_from_canonical():
    assert is_legacy("makoto.contract_order") is True
    assert is_legacy("gate.contract_order") is False


def test_every_canonical_target_is_a_real_live_id():
    """A dangling alias (pointing at an id nothing discovers anymore) would be an illusory
    resolution -- it would "work" but land on a check that no longer exists."""
    from makoto.substrate._loader import discover
    live_ids = {c.id for c in discover()}
    for legacy, canon in LEGACY_TO_CANONICAL.items():
        assert canon in live_ids, f"{legacy!r} aliases to {canon!r}, which is not a live check id"


def test_disabled_pattern_ids_expands_a_legacy_id_to_its_canonical_form(monkeypatch):
    import makoto._dispatch as D
    monkeypatch.setenv("MAKOTO_DISABLE_PATTERNS", "makoto.contract_order")
    disabled = D._disabled_pattern_ids()
    assert "makoto.contract_order" in disabled
    assert "gate.contract_order" in disabled


def test_disabled_pattern_ids_passes_through_an_already_canonical_id(monkeypatch):
    import makoto._dispatch as D
    monkeypatch.setenv("MAKOTO_DISABLE_PATTERNS", "gate.contract_order")
    disabled = D._disabled_pattern_ids()
    assert disabled == {"gate.contract_order"}
