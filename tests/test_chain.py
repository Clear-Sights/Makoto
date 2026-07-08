"""Chain-integrity + concurrency tests for makoto/chain.py — ported by shape from Assay's
tests/test_ledger.py (the substrate this module re-homes). Every test points MAKOTO_STATE_DIR at
a tmp dir so no test touches the real store. The two concurrency races and the seven
tamper-detection cases are the load-bearing evidence that the chain actually detects tampering,
not just that append/read round-trip."""
from __future__ import annotations

import json
import multiprocessing
import os
import threading
from pathlib import Path

import pytest


@pytest.fixture()
def chain(monkeypatch, tmp_path):
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(tmp_path))
    # no reload needed: store_root() -> state._state_dir() reads the env var LIVE on every call,
    # and a reload would corrupt class identity (LedgerView) for every other already-imported
    # consumer in the same pytest process — a real pollution bug this fixture had at first.
    import makoto.ledger as c
    return c


def _append_n(state_dir, n, tag):
    os.environ["MAKOTO_STATE_DIR"] = state_dir     # fresh child process: plain import suffices
    import makoto.ledger as c
    for i in range(n):
        c.append({"kind": "test", "key": f"{tag}-{i}"})


def test_append_read_roundtrip(chain):
    chain.append({"kind": "verdict", "key": "a"})
    chain.append({"kind": "verdict", "key": "b"})
    rows = chain.read()
    assert [r["key"] for r in rows] == ["a", "b"]
    assert rows[0]["prev_hash"] == ""                 # genesis
    assert rows[1]["prev_hash"] == rows[0]["row_hash"]  # linked


def test_concurrent_threads_append_without_forking_chain(chain, tmp_path):
    threads = [threading.Thread(target=lambda t=t: [chain.append({"k": f"{t}-{i}"}) for i in range(10)])
               for t in range(20)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert chain.verify_chain() is None, "20 racing threads must not fork the chain"
    assert len(chain.read()) == 200


def test_concurrent_processes_append_without_forking_chain(chain, tmp_path):
    procs = [multiprocessing.Process(target=_append_n, args=(str(tmp_path), 10, f"p{p}"))
             for p in range(20)]
    for pr in procs:
        pr.start()
    for pr in procs:
        pr.join()
    assert chain.verify_chain() is None, "20 racing processes must not fork the chain"
    assert len(chain.read()) == 200


def test_verify_chain_clean_on_untampered_appends(chain):
    for i in range(5):
        chain.append({"k": i})
    assert chain.verify_chain() is None


def test_verify_chain_none_when_absent_or_empty(chain, tmp_path):
    assert chain.verify_chain() is None                       # absent
    (tmp_path / "chain.jsonl").write_text("", encoding="utf-8")
    assert chain.verify_chain() is None                       # empty


def test_verify_chain_detects_hand_edited_field(chain, tmp_path):
    chain.append({"k": "a"})
    chain.append({"k": "b"})
    p = tmp_path / "chain.jsonl"
    lines = p.read_text().splitlines()
    row0 = json.loads(lines[0])
    row0["k"] = "TAMPERED"                                     # edit a field, leave its row_hash stale
    lines[0] = json.dumps(row0, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    p.write_text("\n".join(lines) + "\n")
    assert chain.verify_chain() == 0                          # exact broken row


def test_verify_chain_detects_broken_prev_hash_link(chain, tmp_path):
    for k in "abc":
        chain.append({"k": k})
    p = tmp_path / "chain.jsonl"
    lines = p.read_text().splitlines()
    row1 = json.loads(lines[1])
    row1["prev_hash"] = "0" * 64                              # sever the link
    lines[1] = json.dumps(row1, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    p.write_text("\n".join(lines) + "\n")
    assert chain.verify_chain() == 1


def test_verify_chain_detects_reorder_never_crashes(chain, tmp_path):
    for k in "abc":
        chain.append({"k": k})
    p = tmp_path / "chain.jsonl"
    lines = p.read_text().splitlines()
    lines[0], lines[1] = lines[1], lines[0]                   # reorder
    p.write_text("\n".join(lines) + "\n")
    assert chain.verify_chain() == 0


def test_verify_chain_detects_truncated_tail_never_crashes(chain, tmp_path):
    for k in "abc":
        chain.append({"k": k})
    p = tmp_path / "chain.jsonl"
    lines = p.read_text().splitlines()
    lines[-1] = lines[-1][: len(lines[-1]) // 2]             # truncate the last line mid-JSON
    p.write_text("\n".join(lines) + "\n")
    assert chain.verify_chain() == 2


def test_verify_chain_detects_non_dict_row_never_crashes(chain, tmp_path):
    chain.append({"k": "a"})
    p = tmp_path / "chain.jsonl"
    p.write_text(p.read_text() + "[1, 2, 3]\n")               # a valid-JSON non-dict row
    assert chain.verify_chain() == 1
