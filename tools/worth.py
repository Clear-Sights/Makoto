#!/usr/bin/env python3
"""Grade whether each check is worth it: its catches against its fires, on a real audit record.

usage: python3 tools/worth.py AUDIT.jsonl VERDICTS.tsv

AUDIT.jsonl is makoto's own audit stream (<state dir>/audit.jsonl), one row per finding-producing
hook call. Every name in a row's `pattern_fires` is one FIRE. A fire is a REPEAT when the same
session's previous fire of the same check carried the same first message: nothing new reached the
agent, so a repeat is a cost and never a catch. That class needs no judgement and none is asked.
A fire the row lists under `withheld` was recorded and never re-sent, so it costs nothing and is
not counted.

Every other fire needs a verdict in VERDICTS.tsv (`ts<TAB>check<TAB>verdict<TAB>note`, verdict one
of `catch` a real misstep stopped or corrected, `report` true and read but changed nothing, `false`
the fire was wrong). A verdict is a reading of the record, written once, with its reason in `note`.

Bar (Gabriel 2026-09-28, "never not being worth it, assuming even one thing triggers"): a check
that fired at least once is WORTH IT only when catches >= false + repeats. A check that never
fired is not graded. Exit 0 when every check that fired is worth it, 1 when one is not, 2 when a
fire has no verdict or a verdict row matches no fire (NOT-EVALUABLE: an unread fire is how a
costly check hides).
"""
import json
import sys
from collections import defaultdict

VERDICTS = {"catch", "report", "false"}


def fires(audit_lines):
    """[(ts, check, message, is_repeat)] in record order."""
    out, last = [], {}
    for line in audit_lines:
        if not line.strip():
            continue
        row = json.loads(line)
        msgs = {f.get("pattern_id"): (f.get("message") or "") for f in row.get("findings") or []}
        withheld = set(row.get("withheld") or ())
        for check in row.get("pattern_fires") or []:
            if check in withheld:
                continue   # recorded, never re-sent: it cost the agent nothing
            key = (row.get("session_id"), check)
            msg = msgs.get(check, "")
            out.append((row.get("ts", ""), check, msg, last.get(key) == msg))
            last[key] = msg
    return out


def grade(audit_lines, verdict_lines):
    labels, errors = {}, []
    for n, line in enumerate(verdict_lines, start=1):
        if not line.strip() or line.startswith("ts\t"):
            continue
        ts, check, verdict, note = (line.rstrip("\n").split("\t") + ["", "", "", ""])[:4]
        if verdict not in VERDICTS:
            errors.append(f"verdicts line {n}: {verdict!r} is not one of {sorted(VERDICTS)}")
        if not note.strip():
            errors.append(f"verdicts line {n}: {check} at {ts} has a verdict and no note")
        labels[(ts, check)] = verdict
    table = defaultdict(lambda: {"fires": 0, "catch": 0, "report": 0, "false": 0, "repeat": 0})
    seen = set()
    for ts, check, _msg, repeat in fires(audit_lines):
        t = table[check]
        t["fires"] += 1
        if repeat:
            t["repeat"] += 1
            continue
        verdict = labels.get((ts, check))
        seen.add((ts, check))
        if verdict is None:
            errors.append(f"fire {check} at {ts} has no verdict")
        elif verdict in VERDICTS:
            t[verdict] += 1
    for key in sorted(set(labels) - seen):
        errors.append(f"verdict {key[1]} at {key[0]} matches no fire in the audit")
    return dict(table), errors


def main(argv):
    if len(argv) != 3:
        print(__doc__.split("\n\n")[1])
        return 2
    with open(argv[1], encoding="utf-8") as a, open(argv[2], encoding="utf-8") as v:
        table, errors = grade(a.readlines(), v.readlines())
    unworthy = []
    print(f"{'check':<40} fires catch report false repeat  worth")
    for check, t in sorted(table.items(), key=lambda kv: -kv[1]["fires"]):
        ok = t["catch"] >= t["false"] + t["repeat"]
        unworthy += [] if ok else [check]
        print(f"{check:<40} {t['fires']:>5} {t['catch']:>5} {t['report']:>6} {t['false']:>5} "
              f"{t['repeat']:>6}  {'yes' if ok else 'NO'}")
    total = {k: sum(t[k] for t in table.values()) for k in ("fires", "catch", "report", "false", "repeat")}
    print(f"WORTH  checks={len(table)} worth={len(table) - len(unworthy)} not={len(unworthy)}  "
          + "  ".join(f"{k}={v}" for k, v in total.items()))
    if errors:
        print(f"  NOT-EVALUABLE {len(errors)}")
        for e in errors:
            print(f"    {e}")
        return 2
    return 1 if unworthy else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
