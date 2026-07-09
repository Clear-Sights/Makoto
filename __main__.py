"""CLI entry — makoto status / install / uninstall / pattern.

Hook dispatch (PreToolUse, Stop) is handled by _dispatch.py via the plugin
shim or settings.json wiring. This module exposes the install lifecycle, a
status report, and catalog inspection.

Subcommands:
  status               summary of patterns_count, hooks_wired, state_dir,
                       patterns_disabled (from MAKOTO_DISABLE_PATTERNS env)
  install              state setup + settings.json hook wiring (idempotent)
  uninstall            remove Makoto-managed hook entries
  show <key>           read the results ledger by normalized location key
  pattern list         show every pattern in the catalog as a table
  pattern show <id>    show full detail for one pattern + first 30 lines of
                       its predicate module
"""
from __future__ import annotations
import argparse
import importlib
import inspect
import json
import sys
from pathlib import Path

from makoto.core.schema import load_prechecks


def _cmd_pattern_list() -> int:
    """print every loaded pattern as a tab-aligned table."""
    patterns = load_prechecks()
    if not patterns:
        print("makoto: no patterns loaded")
        return 0
    print(f"{'ID':<6} {'LEVEL':<10} {'KEYWORDS':<32} DESCRIPTION")
    print(f"{'-'*6} {'-'*10} {'-'*32} {'-'*40}")
    for p in patterns:
        kw = ",".join(p.keywords[:3])
        if len(p.keywords) > 3:
            kw += f",+{len(p.keywords)-3}"
        if len(kw) > 30:
            kw = kw[:29] + "…"
        desc = p.description if len(p.description) <= 60 else p.description[:59] + "…"
        print(f"{p.id:<6} {p.fire_level:<10} {kw:<32} {desc}")
    return 0


def _cmd_pattern_show(pid: str) -> int:
    """print full detail for one pattern + the first 30 lines of its predicate module.

    SPEC-C item 3: `pid` is resolved through the legacy-id alias table first, so an operator
    who types a check's OLD id (from memory, an old script, a bookmarked doc) still gets the
    same live check after a rename -- the CLI honors the same "an old id is never dead, it's
    an alias" guarantee MAKOTO_DISABLE_PATTERNS already gets.
    """
    from makoto.substrate._aliases import canonical
    pid = canonical(pid)
    patterns = {p.id: p for p in load_prechecks()}
    if pid not in patterns:
        print(f"makoto: no pattern with id {pid!r}; available: {', '.join(sorted(patterns))}",
              file=sys.stderr)
        return 2
    p = patterns[pid]
    print(f"id              {p.id}")
    print(f"fire_level      {p.fire_level}")
    print(f"description     {p.description}")
    print(f"retry_hint      {p.retry_hint}")
    print(f"predicate       {p.predicate_module}")
    print(f"keywords        {p.keywords}")
    print("---")
    if p.predicate_module:
        try:
            mod = importlib.import_module(p.predicate_module)
            src_file = inspect.getsourcefile(mod) or "<unknown>"
            print(f"source: {src_file}")
            src_lines = Path(src_file).read_text(encoding="utf-8").splitlines()[:30]
            for i, line in enumerate(src_lines, 1):
                print(f"{i:>3}  {line}")
        except Exception as exc:
            print(f"(could not load predicate source: {exc})", file=sys.stderr)
    return 0


def _cmd_receipt(session_id: str | None) -> int:
    """print the current receipt (Task 2 slice 4) as JSON -- a pure read-time view over the
    chain, never a persisted row. Fail-soft: no chain yet -> a vacuous all-zero receipt, exit 0
    (matching `_cmd_show`'s "no DB yet" discipline; this is inspection, never a gate)."""
    from makoto.record.receipt import emit_receipt
    print(json.dumps(emit_receipt(session_id=session_id), indent=2))
    return 0


def _cmd_show(key: str) -> int:
    """read the results ledger by normalized key; print the row or 'no record'.

    A read-only inspection command — it never evaluates predicates, never fires,
    never blocks. Fail-soft: no DB yet -> a friendly note, exit 0.
    """
    import sqlite3
    from makoto.record.state import _state_dir
    from makoto.record import ledger
    db_path = _state_dir() / "makoto.record.db"
    if not db_path.exists():
        print("makoto show: no makoto.record.db yet (run `makoto install`)", file=sys.stderr)
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        row = ledger.read_key(conn, key)
    finally:
        conn.close()
    if row is None:
        print(f"no record for {key!r}")
    else:
        print(json.dumps(row, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser. Extracted from main() so tests can introspect the
    live command set (tests/test_doc_materiality.py) without spawning a subprocess."""
    p = argparse.ArgumentParser(prog="makoto")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("install")
    sub.add_parser("uninstall")
    sp_show = sub.add_parser("show", help="read the results ledger by key")
    sp_show.add_argument("key", help="normalized location key, e.g. src/auth.py")
    sp_receipt = sub.add_parser("receipt", help="print the current chain receipt (JSON)")
    sp_receipt.add_argument("--session", dest="session_id", default=None,
                            help="scope the receipt to one session_id (default: whole chain)")
    pat = sub.add_parser("pattern", help="inspect the catalog")
    pat_sub = pat.add_subparsers(dest="pat_action", required=True)
    pat_sub.add_parser("list", help="show all patterns as a table")
    pat_show = pat_sub.add_parser("show", help="show full detail for one pattern")
    pat_show.add_argument("id", help="pattern id, e.g. 1.1")
    return p


def main() -> int:
    """argparse dispatch."""
    args = build_parser().parse_args()
    if args.cmd == "status":
        from makoto.install import cmd_status
        return cmd_status()
    if args.cmd == "install":
        from makoto.install import cmd_install
        return cmd_install()
    if args.cmd == "uninstall":
        from makoto.install import cmd_uninstall
        return cmd_uninstall()
    if args.cmd == "show":
        return _cmd_show(args.key)
    if args.cmd == "receipt":
        return _cmd_receipt(args.session_id)
    if args.cmd == "pattern":
        if args.pat_action == "list":
            return _cmd_pattern_list()
        if args.pat_action == "show":
            return _cmd_pattern_show(args.id)
    return 1


if __name__ == "__main__":
    sys.exit(main())
