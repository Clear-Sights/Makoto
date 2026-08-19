"""content.unsourced_webfetch — WebFetch URL not in any prior tool_result.

Mining evidence (Miner-W, 2026-05-26): 571 of 1,858 WebFetches across 302
sessions (31%) hit a URL that never appeared in any prior WebSearch result.
The agent invented the URL — often based on a plausible-looking host+path
pattern from training data.

Predicate walks session history (events table, populated by 1.0.5 PostToolUse
infra) and checks whether the URL appears anywhere in prior tool_response
content. Two short-circuits come first: a trusted-host allowlist for well-known
docs domains, and -- the one that keeps the condition honest -- a URL the USER
typed verbatim in a genuine transcript turn. "Not in a prior tool_result" is a
proxy for "fabricated", and it is a proxy that misfires on the single most
clearly-grounded case there is; see `_user_supplied` for the measured misfire.

Knight-Leveson: stdlib re + json only; conn for events lookup is passed in.
"""
from __future__ import annotations
from typing import Optional
from urllib.parse import urlparse
from makoto.vocab import Finding
from makoto.registry import Check
from makoto.kit import claim_vs_history_predicate, raw_payload_str


# Allowlisted hosts the agent legitimately knows from training data.
_TRUSTED_HOSTS = frozenset({
    "docs.anthropic.com",
    "code.claude.com",
    "claude.com",
    "docs.claude.com",
    "github.com",          # GitHub is so well-known that fabricating a github URL is rare
    "stackoverflow.com",
    "wikipedia.org",
    "en.wikipedia.org",
})


# The characters that can CONTINUE a url. A match followed by one of these is a proper prefix of a
# longer url the user actually typed, not that url -- which is the whole substring hole.
#
# Sentence punctuation is deliberately NOT in this set, and that asymmetry is the point: people end
# sentences with urls, and `See https://vendor.example/a.` must keep exempting
# `https://vendor.example/a`. Treating the trailing period as part of the url would turn this fix
# into a false DENY on the single most ordinary way a human supplies a url -- the exact failure
# this check was rewritten to stop committing. Same linkifier convention every chat client uses.
_URL_CONTINUES = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_~/%&=+@#$*"
)


def _ends_url(turn: str, url: str) -> bool:
    """True iff `url` occurs in `turn` as a complete url rather than as a prefix of a longer one."""
    start = turn.find(url)
    while start != -1:
        end = start + len(url)
        if end >= len(turn) or turn[end] not in _URL_CONTINUES:
            return True
        start = turn.find(url, start + 1)
    return False


def _user_supplied(url: str, current_event: dict) -> bool:
    """True iff `url` appears VERBATIM in a genuine user turn of this session's transcript.

    THE TRIGGER-NARROWING THAT MAKES THIS CHECK MEAN WHAT IT SAYS. The mined defect is a
    FABRICATED url -- one the agent invented from a plausible host+path pattern in training data.
    The implemented condition was "never seen in a prior tool_result", and those are not the same
    set. A url the human typed into chat has never been in a tool_result either, so the check fired
    on it: measured live, on a url the user supplied directly, denied as never-seen. That is not a
    near-miss of the target, it is a different target -- and it fires precisely when the agent is
    doing the most obviously correct thing available to it, which is the worst possible time for a
    gate to be wrong, because the user watched them supply the url.

    A url the user typed is grounded BY DEFINITION: its provenance is the oracle, and no tool call
    can improve on that. So the exemption is not a softening of the check, it is the check finally
    matching its own stated subject.

    Verbatim, and only verbatim -- as a WHOLE URL, not as a substring. No normalization, no
    host-only match, no prefix match. A host-only match would exempt every path under any domain
    the user ever mentioned, which is the fabrication this check exists to catch, one directory
    deeper -- and plain `in` quietly granted exactly that, one character at a time. If the user
    typed `https://vendor.example/api/v3/reference-internal-only`, then
    `https://vendor.example/api/v3/reference` is a substring of it, so the agent could invent that
    shorter url -- a DIFFERENT resource, which the user never named -- and be waved through by the
    oracle. Every proper prefix of anything the user ever pasted was pre-approved. `_ends_url`
    closes it by requiring the match to END where the user's url ended.

    Spoof-resistant by construction, because the turns come from `ledger.user_turn_texts`, which
    admits only host-written, non-synthetic, non-tool-result user entries. The agent cannot write
    itself a permission slip: a tool result carrying the url is not a user turn, and that
    distinction is enforced where the transcript is read, not here.
    """
    try:
        from makoto.state.ledger import user_turn_texts
        turns = user_turn_texts(current_event.get("transcript_path"))
    except Exception:
        # Absence of evidence, never evidence of absence: an unreadable transcript leaves the
        # check exactly as strict as it was before this exemption existed.
        return False
    return any(_ends_url(turn, url) for turn in turns)


def _webfetch_url(current_event: dict) -> Optional[str]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    if current_event.get("tool_name") != "WebFetch":
        return None
    url = current_event.get("tool_input", {}).get("url", "")
    if not url:
        return None
    # Trusted-host short-circuit
    host = urlparse(url).netloc.lower()
    if host in _TRUSTED_HOSTS or any(host.endswith("." + th) for th in _TRUSTED_HOSTS):
        return None
    # Oracle short-circuit: the user typed this url themselves. See `_user_supplied`.
    if _user_supplied(url, current_event):
        return None
    return url


def _url_grounded_in_history(url: str, history: list) -> bool:
    for entry in history:
        payload = raw_payload_str(entry)
        if payload and url.lower() in payload.lower():
            return True
    return False


predicate = claim_vs_history_predicate(
    claim_rxs=(), neg_ref_rx=None, grounded_in_history=_url_grounded_in_history,
    tool_gate=_webfetch_url,
    message=("row {id} ({description}): this URL was never returned by a prior tool call in "
             "this session, and the user never typed it"),
)


from makoto.registry import Check as _Check
RETRY_HINT = 'Run WebSearch first; only WebFetch URLs that prior search results actually returned, or that the user gave you verbatim. Fabricated URLs typically reflect plausible host+path patterns from training data, not real pages.'
DESCRIPTION = 'WebFetch URL neither returned by a prior tool_result nor supplied verbatim by the user'

CHECK = _Check(id='content.unsourced_webfetch', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('http://', 'https://'), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "history", "pattern"}), tests="CLAIM_VS_HISTORY")
