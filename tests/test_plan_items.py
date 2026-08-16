import sqlite3

from makoto.state.plan import (
    record_task_event,
    source_plan_item_promise, source_plan_item_completions,
    record_plan_item, open_plan_items, set_plan_item_status, sync_plan_items,
)
from makoto.checks.planItemDrift import plan_item_drift_gate


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE plan_item_commitments (
            commitment_key  TEXT PRIMARY KEY,
            session_id      TEXT,
            label           TEXT,
            description     TEXT,
            status          TEXT NOT NULL DEFAULT 'open',
            retract_param   TEXT,
            ts              TEXT
        )
    """)
    return conn


def test_sources_first_person_forward_promise_on_section_label():
    p = source_plan_item_promise("I'll finish §9.3 after this push.")
    assert p is not None
    assert p["label"] == "section:9.3"


def test_sources_forward_promise_on_task_hash_label():
    p = source_plan_item_promise("Next I need to close out Task #19.")
    assert p is not None
    assert p["label"] == "task:19"


def test_silent_on_negated_frame():
    assert source_plan_item_promise("I won't finish §9.3 right now.") is None


def test_silent_on_past_tense_completion():
    assert source_plan_item_promise("I finished §9.3 already.") is None


def test_silent_on_conditional_offer():
    assert source_plan_item_promise("If you want, I could finish §9.3 later.") is None


def test_silent_on_third_person_mention():
    assert source_plan_item_promise("The other agent will finish §9.3.") is None


def test_silent_on_bare_mention_no_verb():
    assert source_plan_item_promise("§9.3 is about the clone-pair triage.") is None


def test_completion_detected_past_tense():
    hits = source_plan_item_completions("I finished §9.3 just now.")
    assert ("section:9.3", "done") in hits


def test_retraction_detected_negation():
    hits = source_plan_item_completions("Never mind §9.3, skipping it.")
    assert ("section:9.3", "retracted") in hits


def test_full_cycle_persists_and_clears():
    conn = _conn()
    sync_plan_items(conn, "s1", "I'll finish §9.3 next.")
    opens = open_plan_items(conn, "s1")
    assert [o["label"] for o in opens] == ["section:9.3"]

    sync_plan_items(conn, "s1", "Done -- I finished §9.3.")
    assert open_plan_items(conn, "s1") == []


def test_reopens_a_retracted_item_on_re_promise():
    conn = _conn()
    sync_plan_items(conn, "s1", "I'll finish §9.3 next.")
    sync_plan_items(conn, "s1", "Actually never mind §9.3.")
    assert open_plan_items(conn, "s1") == []
    sync_plan_items(conn, "s1", "OK I'll finish §9.3 after all.")
    assert [o["label"] for o in open_plan_items(conn, "s1")] == ["section:9.3"]


def test_drift_gate_advisory_lists_open_items():
    f = plan_item_drift_gate([{"commitment_key": "k", "label": "section:9.3", "description": "d"}])
    assert f is not None
    assert f.level == "advisory"
    assert "section:9.3" in f.message


def test_drift_gate_silent_on_no_open_items():
    assert plan_item_drift_gate([]) is None


# ---- Task #19c: the ground-truth source (harness TaskCreate/TaskUpdate tool events) -----------
# Payload shapes below are the LIVE ones captured from Makoto's own events table (2026-07-10),
# not doc-derived: TaskCreate's response carries {"task": {"id", "subject"}}; TaskUpdate's
# carries {"success", "taskId", "updatedFields", "statusChange": {"from", "to"}}.

def _task_create(tid, subject):
    return {"hook_event_name": "PostToolUse", "tool_name": "TaskCreate",
            "tool_input": {"subject": subject, "description": "d"},
            "tool_response": {"task": {"id": tid, "subject": subject}}}


def _task_update(tid, to, frm="in_progress"):
    return {"hook_event_name": "PostToolUse", "tool_name": "TaskUpdate",
            "tool_input": {"taskId": tid, "status": to},
            "tool_response": {"success": True, "taskId": tid, "updatedFields": ["status"],
                              "statusChange": {"from": frm, "to": to}}}


def test_task_create_opens_and_completed_discharges():
    conn = _conn()
    record_task_event(conn, "s1", _task_create("7", "Ship the bridge"))
    opens = open_plan_items(conn, "s1")
    assert [o["label"] for o in opens] == ["task:7"]
    assert opens[0]["description"] == "Ship the bridge"
    record_task_event(conn, "s1", _task_update("7", "completed"))
    assert open_plan_items(conn, "s1") == []


def test_task_delete_retracts_and_in_progress_reopens():
    conn = _conn()
    record_task_event(conn, "s1", _task_create("7", "x"))
    record_task_event(conn, "s1", _task_update("7", "deleted"))
    assert open_plan_items(conn, "s1") == []
    record_task_event(conn, "s1", _task_update("7", "in_progress", frm="pending"))
    assert [o["label"] for o in open_plan_items(conn, "s1")] == ["task:7"]


def test_task_update_on_unknown_task_surfaces_it_open():
    # a resumed session: the store never saw the create, only an in_progress transition
    conn = _conn()
    record_task_event(conn, "s1", _task_update("42", "in_progress", frm="pending"))
    assert [o["label"] for o in open_plan_items(conn, "s1")] == ["task:42"]


def test_task_and_prose_mentions_share_one_commitment():
    # "Task #7" promised in prose and the real Task object id 7 dedupe to the SAME key,
    # so a ground-truth completion discharges the prose promise too.
    conn = _conn()
    sync_plan_items(conn, "s1", "I'll finish Task #7 next.")
    record_task_event(conn, "s1", _task_update("7", "completed"))
    assert open_plan_items(conn, "s1") == []


def test_task_event_malformed_payloads_are_noops():
    conn = _conn()
    for bad in ({}, {"tool_name": "TaskCreate", "tool_response": {}},
                {"tool_name": "TaskCreate", "tool_response": "not-a-dict"},
                {"tool_name": "TaskUpdate", "tool_response": {"success": True}},
                {"tool_name": "TaskUpdate", "tool_response": {"taskId": "9"}},
                {"tool_name": "Bash", "tool_response": {"task": {"id": "9"}}}):
        record_task_event(conn, "s1", bad)
    assert open_plan_items(conn, "s1") == []


def test_task_subject_edit_or_ownership_change_is_ignored():
    conn = _conn()
    record_task_event(conn, "s1", _task_create("7", "x"))
    record_task_event(conn, "s1", {"hook_event_name": "PostToolUse", "tool_name": "TaskUpdate",
                                   "tool_input": {"taskId": "7", "subject": "renamed"},
                                   "tool_response": {"success": True, "taskId": "7",
                                                     "updatedFields": ["subject"]}})
    assert [o["label"] for o in open_plan_items(conn, "s1")] == ["task:7"]   # still open, untouched
