"""CHAIN-FORMAT v1 golden-vector conformance -- docs/CHAIN-FORMAT-v1.md.

These vectors are vendored byte-identically in Clear-Sights/Lever's own suite too. A pass here
and a pass there is what makes the format's "no shared runtime package" bet safe: drift between
the two hand-copied implementations is CAUGHT, not merely hoped against, because both suites
assert the exact same three facts about the exact same three frozen bytes-on-disk fixtures.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from makoto.state import ledger
_VECTORS_DIR = Path(__file__).resolve().parent / "vectors" / "chain_v1"


def _load_into(tmp_path: Path, fixture_name: str) -> Path:
    shutil.copy(_VECTORS_DIR / fixture_name, tmp_path / "chain.jsonl")
    return tmp_path


def test_intact_vector_verifies_fully(tmp_path):
    _load_into(tmp_path, "intact.jsonl")
    assert ledger.verify_chain(root=tmp_path) is None


def test_intact_vector_reads_exactly_three_rows_in_order(tmp_path):
    _load_into(tmp_path, "intact.jsonl")
    rows = ledger.read(root=tmp_path)
    assert len(rows) == 3
    assert [r["kind"] for r in rows] == ["testrun", "verdict", "touched"]
    assert [r["key"] for r in rows] == ["tests/x.py", "gate.green_claim", "src/app.py"]
    assert all(r["src"] == "makoto" for r in rows)


def test_tampered_vector_breaks_at_exactly_row_index_1(tmp_path):
    _load_into(tmp_path, "tampered.jsonl")
    assert ledger.verify_chain(root=tmp_path) == 1


def test_tampered_vector_rows_before_the_break_still_read_correctly(tmp_path):
    """verify_chain names the break; read() itself still returns the full on-disk content
    (parsing is not verification -- a caller who wants trust must call verify_chain too)."""
    _load_into(tmp_path, "tampered.jsonl")
    rows = ledger.read(root=tmp_path)
    assert rows[0]["key"] == "tests/x.py"
    assert rows[1]["value"] == "TAMPERED"


def test_legacy_u2028_vector_verifies_fully(tmp_path):
    """issue #70: row 1 of this vector is a genuine pre-2.4.0 row -- hashed with the OLD
    norm_sha256(prev_hash + canonical(row)) construction, and its `value` carries the one
    character (U+2028) that made that construction disagree with the current `_row_hash`. The
    chain must still verify clean; a row authentic under the construction it was actually
    written with is not tamper."""
    _load_into(tmp_path, "legacy_u2028.jsonl")
    assert ledger.verify_chain(root=tmp_path) is None


def test_legacy_u2028_vector_flags_exactly_row_index_1_as_legacy(tmp_path):
    """The legacy row is a distinct, non-clean state (`legacy_hits`), not merely invisible --
    dispatch's issue #70 fix reports it under its own classification rather than folding it
    into an ordinary silent-clean pass."""
    _load_into(tmp_path, "legacy_u2028.jsonl")
    hits: list = []
    assert ledger.verify_chain(root=tmp_path, legacy_hits=hits) is None
    assert hits == [1]
