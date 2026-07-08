"""Tests for makoto.receipt -- the pure read-time receipt view (Task 2 slice 4).

FABLE DECISION 2026-07-07: claim kinds = verdict/certified-fact/testrun only; a receipt is
computed fresh every call, nothing persisted; every claim cites its own row_index/row_hash.
"""
from __future__ import annotations

from makoto import ledger
from makoto.receipt import emit_receipt


def test_absent_chain_is_a_vacuous_all_zero_receipt(tmp_path):
    r = emit_receipt(root=tmp_path)
    assert r["verified_through"] is None
    assert r["claims"] == []
    assert r["claim_count"] == 0
    assert r["trace_bound_count"] == 0
    assert r["exemption_count"] == 0


def test_only_claim_kinds_are_counted_as_claims(tmp_path):
    ledger.append({"kind": "testrun", "key": "a"}, root=tmp_path)
    ledger.append({"kind": "audit", "key": "b"}, root=tmp_path)          # NOT a claim kind
    ledger.append({"kind": "touched", "key": "c"}, root=tmp_path)        # NOT a claim kind
    ledger.append({"kind": "certified-fact", "key": "d"}, root=tmp_path)
    r = emit_receipt(root=tmp_path)
    assert r["claim_count"] == 2
    assert {c["claim_kind"] for c in r["claims"]} == {"testrun", "certified-fact"}


def test_every_claim_cites_a_real_row_index_and_hash(tmp_path):
    stored = ledger.append({"kind": "verdict", "key": "a"}, root=tmp_path)
    r = emit_receipt(root=tmp_path)
    assert r["claims"] == [{"claim_kind": "verdict", "row_index": 0,
                            "row_hash": stored["row_hash"]}]


def test_session_id_scopes_claims_to_one_session(tmp_path):
    ledger.append({"kind": "testrun", "key": "a", "session_id": "s1"}, root=tmp_path)
    ledger.append({"kind": "testrun", "key": "b", "session_id": "s2"}, root=tmp_path)
    r = emit_receipt(session_id="s1", root=tmp_path)
    assert r["claim_count"] == 1
    assert r["claims"][0]["row_index"] == 0


def test_tampered_chain_excludes_claims_after_the_break_from_trace_bound(tmp_path):
    """PLANT the fault: two claims, tamper the FIRST row. verify_chain names index 0 as broken,
    so trace_bound_count must be 0 even though claim_count still lists both (undisguised, not
    hidden -- the receipt's own contract is 'cite it, never hide it')."""
    import json
    ledger.append({"kind": "testrun", "key": "a"}, root=tmp_path)
    ledger.append({"kind": "verdict", "key": "b"}, root=tmp_path)
    chain_file = tmp_path / "chain.jsonl"
    lines = chain_file.read_text().splitlines()
    row0 = json.loads(lines[0])
    row0["key"] = "TAMPERED"
    lines[0] = json.dumps(row0, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    chain_file.write_text("\n".join(lines) + "\n")

    r = emit_receipt(root=tmp_path)
    assert r["verified_through"] == 0
    assert r["claim_count"] == 2               # still cited, undisguised
    assert r["trace_bound_count"] == 0         # but nothing after (or at) the break is trusted


def test_exemption_count_reflects_chained_exemption_rows(tmp_path):
    from makoto import audit
    audit.append_exemption(tmp_path, pattern_id="content.timing_unsafe_compare", kind="makoto-allow", file="h.py",
                           line=4, reason="r", snippet="s")
    r = emit_receipt(root=tmp_path)
    assert r["exemption_count"] == 1
    assert r["claim_count"] == 0               # an exemption is not itself a claim
