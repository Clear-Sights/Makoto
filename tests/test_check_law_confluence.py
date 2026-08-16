"""ORDER law: independent Stop checks must converge under execution-order changes."""

import random
import sqlite3

from makoto import dispatch
from makoto import verdict as posture
from tests.test_dispatch import _setup_state


def _verdict_shape(findings):
    worst = dispatch._worst_finding(findings)
    if worst is None:
        return None

    outcome, finding = worst
    detail = finding.message
    if outcome == posture.BLOCK:
        hint = dispatch._jit_hint(finding)
        if hint:
            detail = f"{detail}\n{hint}"

    folded_by_mode = tuple(
        (mode, posture.apply(posture.Decision(outcome, detail), mode))
        for mode in (posture.LOOSE, posture.STRICT, posture.ASK_POSTURE, posture.SILENT)
    )
    return outcome, detail, folded_by_mode


# Prediction: confluence should already hold because the Stop fold is commutative/associative;
# any divergence across seeded shuffles is the finding, not noise to average away or retry past.
def test_stop_check_order_is_confluent_for_frozen_dispatch_fixture(tmp_path):
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "posture_stop",
        "cwd": str(tmp_path),
        "last_assistant_message": "Created src/promised_zzz.py. Done.",
    }

    conn = sqlite3.connect(str(state_dir / "makoto.record.db"))
    try:
        # Reuse the stable Stop fixture from test_dispatch_posture_integration. Evaluate its
        # independent checks once, freezing both their inputs and results before any permutation.
        declared_order = dispatch.run_stop_checks(conn, payload, root=state_dir)
    finally:
        conn.close()

    assert declared_order, "the reused fixture must exercise the Stop verdict fold"
    expected = _verdict_shape(declared_order)

    for seed in range(40):
        shuffled = list(declared_order)
        random.Random(seed).shuffle(shuffled)
        assert _verdict_shape(shuffled) == expected, f"Stop-check order diverged for seed={seed}"
