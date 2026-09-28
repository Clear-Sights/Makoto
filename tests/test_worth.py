"""tools/worth.py: a check that fired is worth it only when its catches cover its false fires and
its repeats. Each verdict of the tool has a plant here that turns it."""
import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "worth", Path(__file__).resolve().parent.parent / "tools" / "worth.py")
worth = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(worth)


def _row(ts, *checks, session="s", message="m", withheld=()):
    return json.dumps({"ts": ts, "session_id": session, "pattern_fires": list(checks),
                       "findings": [{"pattern_id": c, "message": message} for c in checks],
                       "withheld": list(withheld)})


def _v(ts, check, verdict, note="read"):
    return f"{ts}\t{check}\t{verdict}\t{note}"


def test_a_catch_covering_its_one_false_fire_is_worth_it():
    # discriminant: two fires with different messages, one catch and one false
    audit = [_row("t1", "gate.a"), _row("t2", "gate.a", message="other")]
    table, errors = worth.grade(audit, [_v("t1", "gate.a", "catch"), _v("t2", "gate.a", "false")])
    assert errors == [] and table["gate.a"]["catch"] == 1 and table["gate.a"]["false"] == 1


def test_plant_a_repeat_costs_without_a_verdict_and_tips_the_check(tmp_path):
    # discriminant: the same message fired three times in one session
    audit = [_row("t1", "gate.a"), _row("t2", "gate.a"), _row("t3", "gate.a")]
    a, v = tmp_path / "a.jsonl", tmp_path / "v.tsv"
    a.write_text("\n".join(audit)); v.write_text(_v("t1", "gate.a", "catch"))
    table, errors = worth.grade(audit, [_v("t1", "gate.a", "catch")])
    assert errors == [] and table["gate.a"]["repeat"] == 2
    assert worth.main(["worth", str(a), str(v)]) == 1


def test_a_withheld_repeat_costs_nothing(tmp_path):
    # discriminant: the repeats carry the fired check under `withheld`
    audit = [_row("t1", "gate.a"), _row("t2", "gate.a", withheld=["gate.a"]),
             _row("t3", "gate.a", withheld=["gate.a"])]
    a, v = tmp_path / "a.jsonl", tmp_path / "v.tsv"
    a.write_text("\n".join(audit)); v.write_text(_v("t1", "gate.a", "catch"))
    assert worth.main(["worth", str(a), str(v)]) == 0


def test_plant_an_unread_fire_is_not_evaluable(tmp_path):
    # discriminant: an empty verdicts file under one fire
    a, v = tmp_path / "a.jsonl", tmp_path / "v.tsv"
    a.write_text(_row("t1", "gate.a")); v.write_text("")
    assert worth.main(["worth", str(a), str(v)]) == 2


def test_plant_a_verdict_for_no_fire_is_not_evaluable():
    # discriminant: a verdict row whose ts and check match nothing in the audit
    _, errors = worth.grade([_row("t1", "gate.a")], [_v("t1", "gate.a", "catch"), _v("t9", "gate.b", "false")])
    assert any("matches no fire" in e for e in errors)


def test_a_repeat_in_another_session_is_a_new_fire():
    # discriminant: the same message in two different sessions
    table, errors = worth.grade([_row("t1", "gate.a", session="s1"), _row("t2", "gate.a", session="s2")],
                                [_v("t1", "gate.a", "catch"), _v("t2", "gate.a", "catch")])
    assert errors == [] and table["gate.a"]["repeat"] == 0 and table["gate.a"]["catch"] == 2


def test_every_fired_check_worth_it_exits_zero(tmp_path):
    # discriminant: one fire, one catch verdict, nothing else
    a, v = tmp_path / "a.jsonl", tmp_path / "v.tsv"
    a.write_text(_row("t1", "gate.a")); v.write_text(_v("t1", "gate.a", "catch"))
    assert worth.main(["worth", str(a), str(v)]) == 0
