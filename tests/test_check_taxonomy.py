"""The two firing categories load under their loaders: Pre-Checks (prechecks/, load_prechecks) and
Stop-Checks (stopchecks/, load_stopchecks). The former Close-Checks and Post-Checks PACKAGES were
collapsed away — the taxonomy is by TRIGGER EVENT, and liveness already fired on Stop, so it is now
the gate.liveness StopCheck; the empty post tier (PostToolUse, never populated) was deleted.

SPEC-C item 7 (dead weight sweep): the dead-package regression guard this file used to carry
(`test_collapsed_packages_are_gone`) is now `test_checks_taxonomy.py::
test_collapsed_packages_are_still_gone` -- ONE guard, not two copies of the same assertion drifting
independently. That file tests a genuinely different subject (the newer, not-yet-live
`checks._loader.load_checks` discovery mechanism) and is NOT a duplicate of this one otherwise --
both files stay, each testing its own real, still-live subsystem."""
from makoto.core.schema import load_prechecks            # schema.py exposes the Pre-Check loader
from makoto.stopchecks import load_stopchecks


def test_two_categories_load():
    assert load_prechecks(), "prechecks discovered"
    assert load_stopchecks(), "stopchecks discovered"


def test_liveness_run_adapter_emits_findings(tmp_path):
    # The Stop adapter reads each touched .py file and emits a real Finding per illusory statement.
    from makoto.checks.deadPureStatement import _run
    from makoto.core.schema import Finding
    f = tmp_path / "m.py"
    f.write_text("def fn():\n d = 1+1\n return 0\n")

    class Ctx:
        touched = frozenset({str(f)})

        def fs_read(self, p):
            return open(p).read()

    findings = _run(Ctx())
    assert findings and all(isinstance(x, Finding) for x in findings)
    fnd = findings[0]
    assert fnd.pattern_id == "gate.liveness"
    assert fnd.file == str(f) and fnd.line == 2 and fnd.level == "error"
    assert "illusory" in fnd.message


def test_liveness_run_adapter_skips_nonpy_and_missing(tmp_path):
    from makoto.checks.deadPureStatement import _run

    class Ctx:
        touched = frozenset({str(tmp_path / "notes.txt"), str(tmp_path / "gone.py")})

        def fs_read(self, p):
            return open(p).read()                      # raises OSError on the missing .py -> swallowed

    assert _run(Ctx()) == []


def test_liveness_gate_fires_on_touched_file(tmp_path):
    from makoto.checks.deadPureStatement import GATE
    f = tmp_path / "m.py"
    f.write_text("def fn():\n d = 1+1\n return 0\n")

    class Ctx:
        touched = frozenset({str(f)})

        def fs_read(self, p):
            return open(p).read()

    findings = GATE.run(Ctx())
    assert findings, "fires on the dead pure statement"
    assert all("illusory" in getattr(x, "message", "") for x in findings)


def test_liveness_gate_is_discovered_as_a_stopcheck():
    # gate.liveness is now discovered by load_stopchecks (no separate close-check loader).
    assert "gate.liveness" in {g.id for g in load_stopchecks()}


def test_run_stop_checks_includes_liveness_findings(tmp_path, monkeypatch):
    # The Stop dispatch (run_stop_checks) flows the liveness gate's list-findings into its output.
    import makoto._dispatch as D
    f = tmp_path / "m.py"
    f.write_text("def fn():\n d = 1+1\n return 0\n")
    monkeypatch.chdir(tmp_path)

    class FakeC:
        def cursor(self):
            return self

        def execute(self, *a, **k):
            return self

        def fetchall(self):
            return []

        def fetchone(self):
            return None

    # Stub the ledger/commitment reads so the only substrate is the touched file.
    monkeypatch.setattr(D, "GateContext", D.GateContext)
    import makoto.record.ledger as L
    import makoto.session.commitments as C
    monkeypatch.setattr(L, "touched_keys", lambda conn, sid: frozenset({"m.py"}))
    monkeypatch.setattr(L, "empty_write_keys", lambda conn, sid: frozenset())
    monkeypatch.setattr(L, "latest_testrun", lambda conn, sid: "")
    monkeypatch.setattr(C, "source_commitment", lambda text: None)
    monkeypatch.setattr(C, "open_commitments", lambda conn, sid: [])

    payload = {"last_assistant_message": "done", "session_id": "s", "cwd": str(tmp_path)}
    out = D.run_stop_checks(FakeC(), payload)
    assert any(getattr(x, "pattern_id", "") == "gate.liveness" for x in out), \
        "run_stop_checks surfaces the liveness gate finding"
