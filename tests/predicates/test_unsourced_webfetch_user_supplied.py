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

def test_transcript_separators_splitlines_handles_are_all_seen(tmp_path):
    """A REGRESSION, caused by an optimization and caught by an independent review pass.

    `user_turn_texts` was briefly rewritten to iterate an open file handle under `islice`, to apply
    its line bound before reading the whole transcript rather than after. File iteration splits only
    on `\n`; `str.splitlines()` also splits on `\v`, `\f`, `\x1c`-`\x1e`, `\x85`, U+2028 and U+2029.
    A transcript carrying any of those collapsed into ONE unparseable line and the function returned
    [] -- no user turns at all, not merely a missed one.

    That empty list is not inert. `_user_supplied` reads it as "the user never typed this URL" and
    `content.unsourced_webfetch` DENIES, stating exactly that as its reason. So the optimization
    turned an ordinary WebFetch of a URL the user HAD typed into a hard deny resting on a false
    fact. This test pins every separator `splitlines()` recognises, so the bound can only ever be
    reintroduced by a form that splits on the same set.
    """
    from makoto.state.ledger import user_turn_texts

    def record(text):
        return json.dumps({"message": {"role": "user",
                                       "content": [{"type": "text", "text": text}]}})

    for separator in ("\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"):
        path = tmp_path / f"transcript-{ord(separator)}.jsonl"
        path.write_text(record("first turn") + separator + record("fetch https://vendor.example/api"),
                        encoding="utf-8")
        turns = user_turn_texts(str(path))
        assert len(turns) == 2, (
            f"separator U+{ord(separator):04X} lost a user turn: {turns!r} -- a WebFetch of a URL "
            f"the user typed would be denied for 'the user never typed it'")
        assert any("https://vendor.example/api" in t for t in turns)


def test_transcript_line_bound_is_still_applied(tmp_path):
    """The bound the reverted optimization existed to enforce must still hold."""
    from makoto.state.ledger import user_turn_texts

    path = tmp_path / "long.jsonl"
    path.write_text("\n".join(
        json.dumps({"message": {"role": "user", "content": [{"type": "text", "text": f"turn {i}"}]}})
        for i in range(50)), encoding="utf-8")
    assert len(user_turn_texts(str(path), limit=10)) == 10


# --- regressions found by an independent high-effort review pass ------------------------------

def test_a_proper_prefix_of_a_typed_url_is_not_the_typed_url(tmp_path, check):
    """The oracle exempted every PREFIX of anything the user ever pasted.

    `in` is substring containment, and the docstring it implemented says "no prefix match". So a
    user who typed `.../reference-internal-only` silently pre-approved `.../reference` -- a
    DIFFERENT resource they never named -- and the agent could invent it and be waved through by
    the one channel this check treats as ground truth.
    """
    typed = URL + "-internal-only"
    t = _transcript(tmp_path, [_user_turn(f"please fetch {typed}")])
    finding = predicate(current_event=_event(url=URL, transcript_path=t), history=[], pattern=check)
    assert finding is not None and finding.pattern_id == "content.unsourced_webfetch"


def test_the_url_the_user_actually_typed_is_still_exempt(tmp_path, check):
    """The other half: tightening the boundary must not start denying the exact typed url."""
    typed = URL + "-internal-only"
    t = _transcript(tmp_path, [_user_turn(f"please fetch {typed}")])
    assert predicate(current_event=_event(url=typed, transcript_path=t),
                     history=[], pattern=check) is None


@pytest.mark.parametrize("wrapper", ["fetch {}.", "see ({})", "{}", "read {}, then stop",
                                     "<{}>", '"{}"', "{}; thanks"])
def test_ordinary_sentence_punctuation_does_not_revoke_the_exemption(tmp_path, check, wrapper):
    """The failure mode the boundary check could EASILY introduce, pinned so it cannot.

    People end sentences with urls. If a trailing `.` or `)` counted as part of the url, this fix
    would deny the single most ordinary way a human supplies one -- reintroducing the exact false
    deny the exemption was written to stop.
    """
    t = _transcript(tmp_path, [_user_turn(wrapper.format(URL))])
    assert predicate(current_event=_event(transcript_path=t), history=[], pattern=check) is None


def test_a_bom_prefixed_transcript_still_yields_its_first_turn(tmp_path, check):
    """A UTF-8 BOM glued U+FEFF onto the FIRST record, so that record alone failed to parse.

    The first record is where a session's opening message lives -- routinely the very turn
    carrying the url -- and losing it lands as "the user never typed it", i.e. a hard deny resting
    on a false fact.
    """
    p = tmp_path / "bom.jsonl"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps(_user_turn(f"fetch {URL}")).encode("utf-8") + b"\n")
    assert predicate(current_event=_event(transcript_path=str(p)),
                     history=[], pattern=check) is None
