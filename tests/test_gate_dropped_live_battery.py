"""Anti-Goodhart contamination battery for gate.dropped — through the LIVE run_stop_checks path.

The unit tests (test_gate_dropped.py) exercise the pure dropped_gate function; connectivity.py
exercises ONE fire/silent pair through the wired runner. Neither is a measured per-population
error rate over an adversarial near-miss set drawn from the real FP modes. This battery is that
canary (CLAUDE.md multi-layer reliability canaries / anti-Goodhart):

  * a TP population of planted KNOWN drops that MUST every one fire — if any stays silent the gate
    is broken (under-firing), and an all-silent "0 FP" verdict would be a Goodhart green. A TP miss
    VOIDS the battery (assert-fails loudly), it does not quietly pass.
  * a TN population of adversarial near-misses drawn from the discharge FP modes — discharged-by-
    touch, narration-before-recorded-action (the cross-turn-deferral mode that fires on a naive
    detector), content-met count, vague (no identifying info), and negated frames — that MUST every
    one stay silent. Any fire is a measured false positive.

Both populations route through the real wired runner (touched-keys from the ledger, cwd-relative
disk), so a discharge/wiring regression that the pure-function unit tests miss reddens here.
"""
import sqlite3

from makoto import ledger as _L
from makoto._dispatch import run_stop_checks

_COMMIT_DDL = (
    "CREATE TABLE commitments (commitment_key TEXT PRIMARY KEY, session_id TEXT, "
    "location TEXT, qty_min REAL, qty_max REAL, status TEXT NOT NULL DEFAULT 'open', "
    "retract_param TEXT, created_event_id INTEGER, ts TEXT)")
_LEDGER_DDL = (
    "CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT NOT NULL, "
    "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)")


def _conn():
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.execute(_COMMIT_DDL)
    c.execute(_LEDGER_DDL)
    return c


def _write_ledger(conn, path, content):
    """Record a non-empty Write into the ledger so touched_keys/discharge see it (no real file)."""
    _L.record_update(conn, {"tool_name": "Write",
                            "tool_input": {"file_path": path, "content": content}},
                     event_id=1, session_id="s")


def _fired(text, cwd, *, ledger_writes=()):
    conn = _conn()
    for path, content in ledger_writes:
        _write_ledger(conn, path, content)
    out = run_stop_checks(conn, {"last_assistant_message": text, "session_id": "s", "cwd": cwd})
    conn.close()
    return "gate.dropped" in {getattr(f, "pattern_id", "") for f in out}


def test_dropped_tp_population_every_planted_drop_fires(tmp_path):
    """TP canary: each planted drop (no touch, no file on disk) MUST fire. A silent TP means the
    gate is under-firing — which would also fake a clean FP rate — so this VOIDS on any miss."""
    cwd = str(tmp_path)
    tps = [
        "I'll add def validate_seal_ghost to gates_ghost_zzz.py next.",          # named_symbol
        "Let me create config_ghost_zzz.yaml for the run.",                       # named_artifact
        "I will add 3 helper functions to utils_ghost_zzz.py.",                   # count
        "I'll edit lines 10-20 of parser_ghost_zzz.py to fix it.",                # line_range
    ]
    silent = [t for t in tps if not _fired(t, cwd)]
    assert not silent, f"gate.dropped FAILED to fire on planted drops (under-firing -> battery VOID): {silent}"


def test_dropped_tn_population_every_near_miss_stays_silent(tmp_path):
    """TN canary: adversarial near-misses drawn from the real discharge FP modes MUST all stay
    silent through the live runner. Any fire is a measured false positive."""
    cwd = str(tmp_path)
    # content-discharge near-misses need a REAL cwd-relative file (the gate fs_reads disk):
    (tmp_path / "utils_met_zzz.py").write_text(
        "def a():\n    pass\ndef b():\n    pass\ndef c():\n    pass\n")           # 3 defs -> count met
    (tmp_path / "gates_met_zzz.py").write_text(
        "def validate_seal_met():\n    return True\n")                            # symbol present
    fps = []
    cases = [
        # (label, text, ledger_writes)
        ("discharged-by-touch artifact",
         "Let me create cfg_done_zzz.yaml for the run.", (("cfg_done_zzz.yaml", "data: 1\n"),)),
        # the novita cross-turn-deferral FP mode: narration-before-action where the action IS recorded.
        ("narration-before-recorded-action",
         "Now let me update App_done_zzz.css with better styling:", (("App_done_zzz.css", ".x{color:red}\n"),)),
        ("count met on disk",
         "I will add 3 helper functions to utils_met_zzz.py.", ()),
        ("named symbol present on disk",
         "I'll add def validate_seal_met to gates_met_zzz.py.", ()),
        ("vague promise, no identifying info",
         "I'll look into the parser and figure out what is going on.", ()),
        ("negated frame",
         "I won't add config_neg_zzz.yaml — there is no need for it.", ()),
        ("bare intent, no path or info",
         "Now let me update the styling a bit.", ()),
    ]
    for label, text, writes in cases:
        if _fired(text, cwd, ledger_writes=writes):
            fps.append(label)
    assert not fps, f"gate.dropped FALSE-POSITIVE on near-miss(es): {fps}"


def test_dropped_battery_discriminates_as_a_population(tmp_path):
    """The two populations together: TP fire-rate == 100% AND TN fire-rate == 0%. Pins the gate as
    a DISCRIMINATING detector (not fire-on-everything, not silent-on-everything) in one assertion."""
    cwd = str(tmp_path)
    (tmp_path / "u_pop_zzz.py").write_text("def a():\n    pass\ndef b():\n    pass\n")  # 2 defs
    tp = "I'll add def brand_new_pop to brand_new_pop_zzz.py."
    tn = "I will add 2 helper functions to u_pop_zzz.py."                          # 2 present -> met
    assert _fired(tp, cwd) is True
    assert _fired(tn, cwd) is False
