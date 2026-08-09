"""Regression probe for the former flat claim/evidence association defect.

Before the claim graph, every value printed by this module was ``true``: unrelated events
laundered all four claims.  Exit 0 now means every value is ``false`` and therefore every
planted mismatch was rejected.  Run it as
``python3 -m tests.repro_claim_graph_flatness`` from the repository root.
"""
from __future__ import annotations

import inspect
import json
import tempfile
from pathlib import Path

from makoto.checks.claimedShippedAbsent import claimed_shipped_gate
from makoto.checks.fabricatedToolAction import fabricated_action_gate
from makoto.checks.runIntentUnfulfilled import run_promised_gate
from makoto.record import ledger
from makoto.record.receipt import emit_receipt


def _event(event_type: str, tool_name: str, tool_input: dict, tool_response: dict) -> dict:
    return {"event_type": event_type, "payload": {
        "hook_event_name": event_type,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
    }}


def reproduce() -> dict:
    unrelated_read = _event(
        "PreToolUse", "Read", {"file_path": "README.md"}, {},
    )
    action_laundered = fabricated_action_gate(
        "I ran `scripts/deploy.sh`.", history=[unrelated_read],
    ) is None

    promised_stop = {"payload": {
        "hook_event_name": "Stop",
        "session_id": "repro",
        "last_assistant_message": "I'll deploy `release-2026-08` to production.",
    }}
    unrelated_bash = _event(
        "PostToolUse", "Bash", {"command": "printf unrelated"},
        {"stdout": "unrelated", "exitCode": 0},
    )
    promise_laundered = run_promised_gate(
        history=[promised_stop, unrelated_bash],
    ) is None

    unrelated_merge = _event(
        "PostToolUse", "merge_pull_request",
        {"owner": "other", "repo": "other", "pullNumber": 7},
        {"merged": True, "sha": "abc123"},
    )
    shipping_laundered = claimed_shipped_gate(
        "I merged Clear-Sights/makoto PR #999.", history=[unrelated_merge],
    ) is None

    with tempfile.TemporaryDirectory(prefix="makoto-claim-flatness-") as raw_root:
        root = Path(raw_root)
        ledger.append({
            "kind": "testrun",
            "key": "pytest -q",
            "session_id": "repro",
            "value": "1 passed",
        }, root=root)
        receipt = emit_receipt(session_id="repro", root=root)
        receipt_misnames_evidence_as_claim = (
            [c["claim_kind"] for c in receipt["claims"]] == ["testrun"]
            and "claim_text" not in inspect.signature(emit_receipt).parameters
        )

    return {
        "action_laundered_by_unrelated_read": action_laundered,
        "promise_laundered_by_unrelated_bash": promise_laundered,
        "shipping_laundered_by_unrelated_merge": shipping_laundered,
        "receipt_misnames_evidence_as_claim": receipt_misnames_evidence_as_claim,
    }


def main() -> int:
    result = reproduce()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result and not any(result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
