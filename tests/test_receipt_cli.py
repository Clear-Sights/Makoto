"""tests for `makoto receipt [--session <id>]` -- read-only chain-receipt inspection (never
fires). Uses MAKOTO_STATE_DIR (not monkeypatch.setattr on state._state_dir): ledger.py binds
`_chain_state_dir` at IMPORT time (`from makoto.record.state import _state_dir as _chain_state_dir`),
so only the env var is re-read live on every call -- a function-object monkeypatch (the pattern
test_show_cli.py uses for `_cmd_show`'s own fresh per-call import) would not be seen here."""
import json

from makoto.record import ledger
from makoto import __main__ as cli
def test_receipt_cli_absent_chain_is_vacuous(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(tmp_path))
    rc = cli._cmd_receipt(None)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["claim_count"] == 0
    assert out["verified_through"] is None


def test_receipt_cli_reports_real_claims_and_session_scope(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(tmp_path))
    ledger.append({"kind": "testrun", "key": "a", "session_id": "s1"})
    ledger.append({"kind": "testrun", "key": "b", "session_id": "s2"})
    rc = cli._cmd_receipt("s1")
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["session_id"] == "s1"
    assert out["claim_count"] == 1


def test_receipt_subcommand_is_wired_in_the_parser():
    """`python -m makoto receipt --session <id>` must parse -- pins the CLI wiring itself,
    independent of _cmd_receipt's own behavior."""
    args = cli.build_parser().parse_args(["receipt", "--session", "abc"])
    assert args.cmd == "receipt"
    assert args.session_id == "abc"
    args2 = cli.build_parser().parse_args(["receipt"])
    assert args2.session_id is None
