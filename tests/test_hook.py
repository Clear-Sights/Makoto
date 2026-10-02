import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugin"))
import json, tempfile, collections
from makoto2 import hook
Obs = collections.namedtuple("Obs", "seq tool objects written created")
class Rec:
    def __init__(self, evs): self.obs = [Obs(i, e.get("tool_name"), frozenset(e.get("objs", [])), frozenset(), frozenset()) for i, e in enumerate(evs)]
def ev_(**k): return json.dumps(dict(session_id="s", **k))
def always(rows, rec, ev): return {"row": "r1", "message": "m", "objects": ["x"]} if ev["hook_event_name"] in ("PreToolUse", "Stop") else None
def never(rows, rec, ev): return None
_state = tempfile.TemporaryDirectory()
cfg = {"state_dir": _state.name}
run = lambda raw, v=always: hook.main(raw, cfg, [], Rec, v)
# D_in fail open
assert run("not json") == {} and run("{}") == {}
# first finding blocks (plant), pre -> deny, stop -> block
a = run(ev_(hook_event_name="PreToolUse", tool_name="Bash"))
assert a["hookSpecificOutput"]["permissionDecision"] == "deny", a
# O: same object state -> silent (look-alike)
assert run(ev_(hook_event_name="PreToolUse", tool_name="Bash")) == {}
# O: object state changes -> blocks again (plant)
run(ev_(hook_event_name="PostToolUse", tool_name="Bash", objs=["x"]), never)
b = run(ev_(hook_event_name="Stop"))
assert b.get("decision") == "block", b
# D_out has two outputs only
assert set(map(lambda d: tuple(sorted(d)), [a, b, {}])) <= {("hookSpecificOutput",), ("decision", "reason"), ()}
print("test_hook OK 6 assertions")

# Portable, offline GitHub Actions receipt checker. The caller supplies retained
# API responses: {"run": workflow_run, "jobs": jobs_response["jobs"]}.
# These checks establish receipt consistency; their authenticity is external.
CI_JOBS = frozenset({"pytest (ubuntu, py3.11)", "pytest (ubuntu, py3.12)",
                     "pytest (ubuntu, py3.13)", "pytest (macos, py3.13)",
                     "pytest (windows, py3.13)"})
ci_receipt_ok = lambda receipt, head: (
    isinstance(head, str) and len(head) == 40
    and all(c in "0123456789abcdef" for c in head)
    and isinstance(receipt, dict) and isinstance(receipt.get("run"), dict)
    and receipt["run"].get("head_sha") == head
    and receipt["run"].get("status") == "completed"
    and receipt["run"].get("conclusion") == "success"
    and receipt["run"].get("path") == ".github/workflows/ci.yml"
    and isinstance(receipt["run"].get("repository"), dict)
    and receipt["run"].get("repository", {}).get("full_name") == "Clear-Sights/Makoto"
    and type(receipt["run"].get("id")) is int
    and receipt["run"]["id"] > 0
    and isinstance(receipt.get("jobs"), list) and len(receipt["jobs"]) == 5
    and all(isinstance(job, dict) and isinstance(job.get("name"), str)
            for job in receipt["jobs"])
    and {job.get("name") for job in receipt["jobs"]} == CI_JOBS
    and all(job.get("head_sha") == head and job.get("run_id") == receipt["run"]["id"]
            and job.get("status") == "completed" and job.get("conclusion") == "success"
            for job in receipt["jobs"])
)

# Synthetic controls and plants never serve as current CI evidence.
import copy
_head = "a" * 40
_receipt = {"run": {"id": 123, "head_sha": _head, "status": "completed",
                    "conclusion": "success", "path": ".github/workflows/ci.yml",
                    "repository": {"full_name": "Clear-Sights/Makoto"}},
            "jobs": [{"name": name, "head_sha": _head, "run_id": 123,
                      "status": "completed", "conclusion": "success"}
                     for name in sorted(CI_JOBS)]}
assert ci_receipt_ok(_receipt, _head)
assert not ci_receipt_ok(_receipt, "b" * 40)
assert not ci_receipt_ok(_receipt, None)
assert not ci_receipt_ok({}, _head)
for _field, _value in (("head_sha", "b" * 40), ("status", "in_progress"),
                        ("conclusion", "failure"), ("path", "other.yml"),
                        ("repository", None), ("id", None)):
    _plant = copy.deepcopy(_receipt)
    _plant["run"][_field] = _value
    assert not ci_receipt_ok(_plant, _head), _field
for _index in range(5):
    for _field, _value in (("head_sha", "b" * 40), ("status", "queued"),
                          ("conclusion", "skipped"), ("run_id", 456),
                          ("name", "unrelated job")):
        _plant = copy.deepcopy(_receipt)
        _plant["jobs"][_index][_field] = _value
        assert not ci_receipt_ok(_plant, _head), (_index, _field)
_plant = copy.deepcopy(_receipt)
_plant["jobs"].pop()
assert not ci_receipt_ok(_plant, _head)
_plant = copy.deepcopy(_receipt)
_plant["jobs"][0] = copy.deepcopy(_plant["jobs"][1])
assert not ci_receipt_ok(_plant, _head)
_plant = copy.deepcopy(_receipt)
_plant["jobs"].append(copy.deepcopy(_plant["jobs"][0]))
assert not ci_receipt_ok(_plant, _head)
print("CI receipt controls and revision/status/job plants OK (synthetic)")

if __name__ == "__main__" and "--validate" in sys.argv:
    import argparse, hashlib, subprocess
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Measure local validation and retained CI receipts")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--ci-receipt", type=Path)
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = sorted({str(p.relative_to(root)) for directory in ("plugin/makoto2", "tests")
                    for p in (root / directory).iterdir() if p.is_file()
                    and p.suffix in (".py", ".json", ".tsv", ".txt")}
                   | {".github/workflows/ci.yml", "mesh/check.py", "mesh/REQUIREMENTS.tsv",
                      "mesh/CONSTRAINTS.tsv", "mesh/SLOTS.tsv", "mesh/SOURCES.tsv",
                      "SPIRIT.md", "WORDS.tsv", "mesh/reference/docs-def-README.md",
                      "TASKS.tsv", "PLAN.md", "mesh/evidence/register.json"})
    pins = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths}
    digest = hashlib.sha256(json.dumps(pins, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    checks = []
    for command in ([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                    [sys.executable, "tests/test_hook.py"],
                    [sys.executable, "mesh/check.py", "--task", "validate"]):
        proc = subprocess.run(command, cwd=root, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                              text=True, capture_output=True)
        checks.append({"command": command, "exit_code": proc.returncode,
                       "stdout": proc.stdout, "stderr": proc.stderr})
    selected = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=root,
                              text=True, capture_output=True)
    head = selected.stdout.strip() if selected.returncode == 0 else None
    # A head receipt cannot certify modified or untracked selected source bytes.
    tree = subprocess.run(["git", "status", "--porcelain", "--", *paths], cwd=root,
                          text=True, capture_output=True)
    matches_head = head is not None and tree.returncode == 0 and not tree.stdout.strip()
    receipt = None
    receipt_error = None
    if options.ci_receipt:
        try:
            receipt_bytes = options.ci_receipt.read_bytes()
            receipt = json.loads(receipt_bytes)
            receipt_pin = hashlib.sha256(receipt_bytes).hexdigest()
            receipt_valid = bool(ci_receipt_ok(receipt, head))
        except (OSError, ValueError, TypeError, AttributeError):
            receipt_error = "Unreadable, malformed or inconsistent CI receipt"
            receipt_valid = False
    else:
        receipt_valid = False
        receipt_error = "No current retained CI API receipt supplied"
    unchanged = all(hashlib.sha256((root / name).read_bytes()).hexdigest() == pin
                    for name, pin in pins.items())
    local_pass = all(check["exit_code"] == 0 for check in checks) and unchanged
    ci_pass = receipt_valid and matches_head and unchanged
    evidence = {"task": "validate", "requirements": ["suite", "ci"],
                "candidate": "tests/test_evaluate.py:<module>;tests/test_observed.py:<module>;tests/test_hook.py:<module>",
                "port": "validate#evidence", "selected_head": head,
                "selected_input_digest": digest, "source_pins": pins,
                "digest_method": "SHA-256 of UTF-8 canonical source_pins JSON (sorted keys, compact separators); evidence is not self-pinned",
                "checks": checks,
                "observations": [
                    {"case": "local suite, source fixtures and six hook assertions",
                     "result": "pass" if local_pass else "fail", "inputs_unchanged": unchanged},
                    {"case": "CI receipt checker hostile plants", "result": "pass",
                     "synthetic": True, "detail": "Rejects another revision, missing jobs, wrong job/run, pending and unsuccessful outcomes"},
                    {"case": "five current CI jobs", "result": "pass" if ci_pass else "absent",
                     "receipt_consistent": receipt_valid, "selected_sources_match_head": matches_head,
                     "detail": receipt_error or "Retained receipt requires external authenticity verification"}],
                "ci_receipt": receipt,
                "ci_receipt_sha256": locals().get("receipt_pin"),
                "present": (["suite:each_rule:slip_and_control", "suite:observation:subject_bound",
                             "suite:source:pinned", "suite:hook_assertions:six_unit_cases", "ci:local:pass"]
                            if local_pass else []) + ["ci:other_head:rejected"],
                "absent": [] if ci_pass else ["ci:five_jobs:exact_head_pass"],
                "external": [] if ci_pass else ["Selected committed head and authentic five-job CI receipts"],
                "result": "pass" if local_pass and ci_pass else "fail" if not local_pass else "absent",
                "status": "PASS" if local_pass and ci_pass else "FAIL" if not local_pass else "EXTERNAL",
                "failure_edge": "Re-measure changed input and re-derive waves; unavailable operator or outside evidence = EXTERNAL.",
                "scope": "Local unit calls only; no hook installation or live hook invocation. Fixture quote agreement does not certify external provenance. Synthetic receipts do not prove remote CI or register approval."}
    (root / "mesh/evidence/validate.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("validate:", evidence["status"])
    sys.exit(0 if evidence["result"] == "pass" else 1 if evidence["result"] == "fail" else 2)
