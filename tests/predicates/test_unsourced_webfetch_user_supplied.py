"""content.unsourced_webfetch fires on FABRICATION, not on "the user typed it".

MEASURED MISFIRE. The check's stated subject is a hallucinated URL -- one the agent invented from a
plausible host+path pattern in training data. Its implemented condition was "never seen in a prior
tool_result". Those are different sets, and the gap has a resident: a URL the human typed into chat
has never been in a tool_result either. Live, the check denied exactly that.

The exemption is verbatim-only and reads the ORACLE channel (`ledger.user_turn_texts`), which
admits only host-written, non-synthetic, non-tool-result user turns. The agent cannot write itself
a permission slip.
"""
from __future__ import annotations
import json

import pytest

from makoto.checks.unsourcedWebfetch import predicate
from makoto.registry import load_precheck_catalog

URL = "https://obscure-vendor.example/api/v3/reference"


@pytest.fixture
def check():
    return next(c for c in load_precheck_catalog() if c.id == "content.unsourced_webfetch")


def _transcript(tmp_path, entries) -> str:
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in entries))
    return str(p)


def _event(url=URL, transcript_path=None):
    return {"hook_event_name": "PreToolUse", "tool_name": "WebFetch", "session_id": "s",
            "transcript_path": transcript_path, "tool_input": {"url": url}}


def _user_turn(text):
    return {"timestamp": "2026-08-19T10:00:00Z", "message": {"role": "user", "content": text}}


def test_user_typed_url_is_not_a_fabrication(tmp_path, check):
    """The regression. The human supplied the URL; its provenance is the oracle."""
    t = _transcript(tmp_path, [_user_turn(f"please fetch {URL} and summarise it")])
    assert predicate(current_event=_event(transcript_path=t), history=[], pattern=check) is None


def test_url_in_structured_user_content_blocks_too(tmp_path, check):
    """Real transcripts carry user content as a list of blocks, not only as a bare string."""
    entry = {"timestamp": "2026-08-19T10:00:00Z",
             "message": {"role": "user", "content": [{"type": "text", "text": f"see {URL}"}]}}
    assert predicate(current_event=_event(transcript_path=_transcript(tmp_path, [entry])),
                     history=[], pattern=check) is None


def test_unmentioned_url_still_fires(tmp_path, check):
    """The exemption must not blunt the check: a URL nobody supplied is still unsourced."""
    t = _transcript(tmp_path, [_user_turn("please look up the docs for me")])
    finding = predicate(current_event=_event(transcript_path=t), history=[], pattern=check)
    assert finding is not None and finding.pattern_id == "content.unsourced_webfetch"


def test_tool_result_turn_is_not_an_oracle(tmp_path, check):
    """A tool result is the ONE user-role entry an agent can produce.

    Accepting it would let the agent launder a fabricated URL into an exemption by first emitting
    it as tool output. The distinction is enforced in `_is_genuine_user_turn`, and this test is
    what keeps it enforced.
    """
    entry = {"timestamp": "2026-08-19T10:00:00Z", "toolUseResult": {"x": 1},
             "message": {"role": "user", "content": URL}}
    assert predicate(current_event=_event(transcript_path=_transcript(tmp_path, [entry])),
                     history=[], pattern=check) is not None


def test_system_reminder_turn_is_not_an_oracle(tmp_path, check):
    """Harness-injected user-role text is not the human speaking."""
    t = _transcript(tmp_path, [_user_turn(f"<system-reminder> context mentions {URL} </system-reminder>")])
    assert predicate(current_event=_event(transcript_path=t), history=[], pattern=check) is not None


def test_exemption_is_verbatim_not_host_wide(tmp_path, check):
    """A host-only match would exempt every path under any domain the user ever mentioned --
    the fabrication this check exists to catch, one directory deeper."""
    t = _transcript(tmp_path, [_user_turn(f"start from {URL}")])
    deeper = URL + "/internal/secrets"
    assert predicate(current_event=_event(url=deeper, transcript_path=t),
                     history=[], pattern=check) is not None


def test_missing_transcript_leaves_the_check_exactly_as_strict(tmp_path, check):
    """Absence of evidence is never evidence of absence: no transcript means no exemption."""
    assert predicate(current_event=_event(transcript_path=None), history=[], pattern=check) is not None
    missing = str(tmp_path / "nope.jsonl")
    assert predicate(current_event=_event(transcript_path=missing),
                     history=[], pattern=check) is not None


def test_prior_tool_result_grounding_still_works(check):
    """The original grounding path is untouched by the new short-circuit."""
    history = [(1, "2026-08-19T10:00:00Z", "PostToolUse", "/tmp",
                json.dumps({"tool_response": {"results": URL}}))]
    assert predicate(current_event=_event(), history=history, pattern=check) is None
