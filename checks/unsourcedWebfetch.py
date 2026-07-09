"""pattern 1.9 — WebFetch URL not in any prior tool_result.

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
import json
from typing import Optional
from urllib.parse import urlparse
from makoto.core.schema import Finding, PreCheck


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


def predicate(*, current_event: dict, history: list, pattern: PreCheck,
              conn=None) -> Optional[Finding]:
    """fire on WebFetch URL that wasn't seen in any prior session event."""
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
    # Walk history for any prior payload containing this URL substring.
    # history rows are (id, ts, event_type, cwd, payload) tuples from events table.
    # Per RFC 3986, domain names are case-insensitive; normalize for matching.
    url_lower = url.lower()
    for entry in history:
        if isinstance(entry, (tuple, list)) and len(entry) >= 5:
            raw_payload = entry[4]
        else:
            raw_payload = entry.get("payload", "") if hasattr(entry, "get") else ""
        if not raw_payload:
            continue
        if url_lower in str(raw_payload).lower():
            return None  # URL was seen previously
    return Finding(
        pattern_id=pattern.id,
        file="",
        line=0,
        level=pattern.fire_level,
        message=f"row {pattern.id} ({pattern.description}): URL never seen in this session",
        retry_hint=pattern.retry_hint,
        snippet=url[:200],
    )


from makoto.substrate._loader import Check as _Check
RETRY_HINT = 'Run WebSearch first; only WebFetch URLs that prior search results actually returned. Fabricated URLs typically reflect plausible host+path patterns from training data, not real pages.'
DESCRIPTION = 'WebFetch URL never seen in any prior tool_result this session'

CHECK = _Check(id='content.unsourced_webfetch', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('http://', 'https://'), retry_hint=RETRY_HINT, description=DESCRIPTION)
