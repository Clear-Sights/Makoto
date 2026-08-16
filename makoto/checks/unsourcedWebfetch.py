"""content.unsourced_webfetch — WebFetch URL not in any prior tool_result.

Mining evidence (Miner-W, 2026-05-26): 571 of 1,858 WebFetches across 302
sessions (31%) hit a URL that never appeared in any prior WebSearch result.
The agent invented the URL — often based on a plausible-looking host+path
pattern from training data.

Predicate walks session history (events table, populated by 1.0.5 PostToolUse
infra) and checks whether the URL appears anywhere in prior tool_response
content. Trusted-host allowlist short-circuits well-known docs domains.

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
    message="row {id} ({description}): URL never seen in this session",
)


from makoto.registry import Check as _Check
RETRY_HINT = 'Run WebSearch first; only WebFetch URLs that prior search results actually returned. Fabricated URLs typically reflect plausible host+path patterns from training data, not real pages.'
DESCRIPTION = 'WebFetch URL never seen in any prior tool_result this session'

CHECK = _Check(id='content.unsourced_webfetch', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('http://', 'https://'), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "history", "pattern"}), tests="CLAIM_VS_HISTORY")
