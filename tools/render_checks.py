#!/usr/bin/env python3
"""Render executable README evidence (standard library only)."""
from __future__ import annotations

import difflib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugin"
sys.path.insert(0, str(PLUGIN))

from makoto.registry import _ADVISORY_ALLOWLIST, load_checks  # noqa: E402
from makoto.substrate._canonAtoms import BLOCK_IDS, THE_CANON_17  # noqa: E402

README = REPO / "README.md"


def render_counts() -> list[str]:
    pre = load_checks(edge="Pre")
    stop = load_checks(edge="Stop")
    gates = [check for check in stop if check.may_block]
    advisory = [check for check in gates if check.id in _ADVISORY_ALLOWLIST]
    blocking = [check for check in gates if check.id not in _ADVISORY_ALLOWLIST]
    prefixes = Counter(check.id.partition(".")[0] for check in pre)
    prefix_text = ", ".join(f"`{key}`: **{value}**" for key, value in sorted(prefixes.items()))
    return [
        f"- **{len(pre)} pre-checks** (all blocking)",
        f"- Pre-check ids grouped by dotted prefix — {prefix_text}",
        f"- **{len(stop)} Stop checks** (all checks registered at the Stop edge)",
        f"- **{len(gates)} end-of-turn gates** (`may_block=True`)",
        f"- **{len(blocking)} blocking end-of-turn gates** (not advisory-allowlisted)",
        f"- **{len(advisory)} advisory end-of-turn gates** (advisory-allowlisted)",
    ]


def render_canon() -> list[str]:
    total = len(THE_CANON_17)
    blocking = len(BLOCK_IDS)
    return [
        f"- blocking robust core: **{blocking} of {total}** ported canon fingerprints",
        f"- advisory remainder: **{total - blocking}** ported canon fingerprints",
    ]


def _run_shim(payload: object, state: str) -> tuple[int, dict]:
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN), MAKOTO_STATE_DIR=state)
    proc = subprocess.run([str(PLUGIN / "makoto" / "_dispatch_shim.sh")],
                          input=json.dumps(payload), text=True, capture_output=True,
                          env=env, cwd=REPO)
    try:
        body = json.loads(proc.stdout) if proc.stdout else {}
    except json.JSONDecodeError:
        body = {}
    return proc.returncode, body


def _mechanism(body: dict) -> str:
    hook = body.get("hookSpecificOutput", {})
    if "permissionDecision" in hook:
        return f"stdout JSON `hookSpecificOutput.permissionDecision={hook['permissionDecision']!r}`"
    if "decision" in body:
        return f"stdout JSON `decision={body['decision']!r}`"
    return "no blocking decision"


def render_dispatch() -> list[str]:
    with tempfile.TemporaryDirectory(prefix="makoto-readme-evidence-") as state:
        cases = [
            ("clean PreToolUse call", {"hook_event_name": "PreToolUse", "tool_name": "Read",
             "tool_input": {"file_path": "README.md"}, "session_id": "readme-clean", "cwd": str(REPO)}),
            ("error-level pre-check finding", {"hook_event_name": "PreToolUse", "tool_name": "Write",
             "tool_input": {"file_path": "constitution/integrity/checks/readme_probe.py",
                            "content": "if status.startswith('ok'):\n    pass\n"},
             "session_id": "readme-pre-block", "cwd": str(REPO)}),
            ("Stop-gate finding", {"hook_event_name": "Stop", "session_id": "readme-stop-block",
             "cwd": str(REPO),
             "last_assistant_message": "I ran `pytest tests/readme_probe.py -q` and it passed."}),
        ]
        rows = []
        for label, payload in cases:
            code, body = _run_shim(payload, state)
            rows.append(f"| {label} | {_mechanism(body)} | **{code}** |")
        code, body = _run_shim([], state)
        rows.append(f"| invalid/non-object payload | {_mechanism(body)} | **{code}** |")
    return ["| Outcome | Observed mechanism | Process exit |", "|---|---|---|", *rows]


def render_demo() -> list[str]:
    spec = importlib.util.spec_from_file_location("render_demo", REPO / "docs/demo/render_demo.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scenarios = [name for name in vars(module)
                 if name.startswith("scenario_") and callable(vars(module)[name])]
    with tempfile.TemporaryDirectory(prefix="makoto-readme-demo-") as directory:
        demo_root = Path(directory)
        module.LOGS_DIR = demo_root / "logs"
        with redirect_stdout(io.StringIO()):
            module.scenario_receipt(demo_root)
        receipt = json.loads((module.LOGS_DIR / "receipt.json").read_text(encoding="utf-8"))
        receipt_body = json.loads(receipt["steps"][-1]["stdout"])
    replay = subprocess.run([sys.executable, "eval/replay.py"], cwd=REPO, text=True,
                            capture_output=True, check=True).stdout
    summary = next(line for line in replay.splitlines() if line.startswith("REPLAY "))
    fields = dict(item.split("=", 1) for item in summary.split()[1:])
    derailments = sum(
        json.loads(path.read_text(encoding="utf-8").splitlines()[0]).get("expect", "fires") != "none"
        for path in (REPO / "eval/corpus").glob("*.jsonl")
    )
    return [
        f"- corpus replay: **{derailments} derailments**, **{fields['passed']}/{fields['sessions']}** sessions pass; the command exits successfully only when every expectation holds",
        f"- live demo: **{len(scenarios)} REAL scenarios**",
        f"- receipt demo: **{receipt_body['claim_count']} claims**, **{receipt_body['exemption_count']} exemptions**",
    ]


RENDERERS = {"check-counts": render_counts, "canon-split": render_canon,
             "dispatch-contract": render_dispatch, "demo-measurements": render_demo}


def _replace(lines: list[str], marker: str, body: list[str]) -> list[str]:
    begins = [i for i, line in enumerate(lines) if line.startswith(f"<!-- BEGIN GENERATED: {marker}")]
    ends = [i for i, line in enumerate(lines) if line.startswith(f"<!-- END GENERATED: {marker}")]
    # Unit callers may supply a focused fixture containing just one generated region.
    # A malformed region that is present remains an error.
    if not begins and not ends:
        return lines
    if len(begins) != 1 or len(ends) != 1 or ends[0] <= begins[0]:
        raise SystemExit(f"README.md: expected exactly one valid {marker} marker region")
    lines[begins[0] + 1:ends[0]] = ["", *body, ""]
    return lines


def main(argv: list[str]) -> int:
    if argv[1:] not in (["--check"], ["--write"]):
        print("usage: render_checks.py --check | --write", file=sys.stderr)
        return 2
    original = README.read_text(encoding="utf-8")
    lines = original.split("\n")
    for marker, renderer in RENDERERS.items():
        lines = _replace(lines, marker, renderer())
    fresh = "\n".join(lines)
    if fresh == original:
        if argv[1] == "--check":
            print("check counts match makoto.registry")
        return 0
    if argv[1] == "--write":
        README.write_text(fresh, encoding="utf-8")
        print("wrote README.md")
        return 0
    print("GENERATED CHECK-COUNT DRIFT -- README.md disagrees with makoto.registry:", file=sys.stderr)
    for line in difflib.unified_diff(original.splitlines(), fresh.splitlines(),
                                     fromfile="README.md (committed)",
                                     tofile="executable sources (current)", lineterm=""):
        print(line, file=sys.stderr)
    print("Run: python3 tools/render_checks.py --write", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
