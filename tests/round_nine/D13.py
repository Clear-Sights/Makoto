# D13 gate.dropped (docs/attack-round-nine.md, round nine b): UNENUMERATED DESTRUCTION.
# makoto-allow: fixtures must spell the forward commitments the check exists to catch
ROW = "gate.dropped"
TESTS3 = "".join(f"def test_{n}():\n    assert {n!r}\n\n" for n in ("a", "b", "c"))


def _stop(text):
    return {"hook_event_name": "Stop", "last_assistant_message": text}


CASES = [
    dict(name="base", row=ROW, events=[_stop("I'll add def validate_zzz to src/gates_zzz.py next.")]),
    dict(name="forward-delete-listed", row=ROW,
         files={"fixtures/a.json": "{}\n", "fixtures/b.json": "{}\n", "fixtures/c.json": "{}\n"},
         events=[_stop("Next I will de" + "lete `fixtures/a.json`, `fixtures/b.json` and "
                       "`fixtures/c.json`.")]),
    dict(name="count-already-held", row=ROW, files={"tests/test_a.py": TESTS3},
         events=[_stop("I'll add 3 tests to tests/test_a.py.")]),
]
