"""A denial that does not name its own row cannot be cited, looked up, or told apart.

The pattern-driven rows in `kit.py` build their message as `row {pattern.id} (...)`, so they
carried their id by construction. Every hand-written predicate had to remember to, and
`event.identical_retry` did not: its denial read as bare prose, so a reader could not tell which
of the fifteen Pre rows had spoken. The replay corpus could not attribute the fire to a row
either, which is why a session named for one check used to pass on a denial from any other.

`dispatch._named` closes it at the one place every finding passes through. A convention each
author must remember is the same defect waiting on the next author, so this is a property of the
boundary rather than a rule about predicates.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from makoto import dispatch
from makoto.registry import load_checks
from makoto.vocab import Finding

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "eval" / "corpus"


def finding(pattern_id: str, message: str) -> Finding:
    return Finding(pattern_id=pattern_id, file="f.py", line=1, level="ERROR", message=message)


class EveryDenialNamesItsRow(unittest.TestCase):
    def test_a_message_without_its_id_gains_it(self) -> None:
        named = dispatch._named(finding("event.identical_retry", "Identical retry of a Bash call"))
        self.assertIn("event.identical_retry", named)
        self.assertIn("Identical retry of a Bash call", named)

    def test_a_message_that_already_names_its_id_is_not_doubled(self) -> None:
        message = "row content.phantom_citation (a citation nobody can open): matched 'x'"
        self.assertEqual(dispatch._named(finding("content.phantom_citation", message)), message)
        self.assertEqual(dispatch._named(finding("content.phantom_citation", message)).count(
            "content.phantom_citation"), 1)

    def test_a_finding_with_no_id_is_passed_through_rather_than_mangled(self) -> None:
        self.assertEqual(dispatch._named(finding("", "something happened")), "something happened")

    def test_every_discovered_check_id_would_be_named(self) -> None:
        """Over every shipped check, not a sample: an id absent from its message is added."""
        ids = sorted({check.id for edge in ("Pre", "Stop") for check in load_checks(edge=edge)})
        self.assertTrue(ids, "no checks were discovered; finding nothing is not finding nothing wrong")
        for check_id in ids:
            with self.subTest(check_id):
                self.assertIn(check_id, dispatch._named(finding(check_id, "a bare message")))

    def test_the_check_can_fail(self) -> None:
        """Planted: a boundary that returns the raw message leaves a denial anonymous."""
        raw = finding("event.identical_retry", "Identical retry of a Bash call").message
        self.assertNotIn("event.identical_retry", raw)


class EveryCorpusSessionDeclaresACheck(unittest.TestCase):
    def test_every_session_declares_a_check_that_exists(self) -> None:
        known = {check.id for edge in ("Pre", "Stop") for check in load_checks(edge=edge)}
        for session in sorted(CORPUS.glob("*.jsonl")):
            header = json.loads(session.read_text().splitlines()[0])
            declared = header.get("check")
            if declared is None:
                self.assertEqual(
                    header.get("expect"), "none",
                    f"{session.name} names no check and is not a control session; a session that "
                    f"names no check is evidence about nothing")
                continue
            self.assertIn(declared, known,
                          f"{session.name} declares {declared}, which no registry edge discovers")


if __name__ == "__main__":
    unittest.main()
