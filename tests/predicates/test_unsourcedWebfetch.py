"""tests for pattern 1.9 — WebFetch URL not in prior tool_result."""
import json
from makoto.checks.unsourcedWebfetch import predicate
from makoto.core.schema import PreCheck


_PAT = PreCheck(
    id="content.unsourced_webfetch",
    fire_level="error",
    description="WebFetch URL never seen in prior tool_result",
    retry_hint="Search first; only fetch URLs that prior search results returned.",
)


def _webfetch(url: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "WebFetch",
            "tool_input": {"url": url}}


def _history_entry(payload_dict: dict) -> tuple:
    """build an events-table-shaped row (id, ts, event_type, cwd, payload_raw)."""
    return (1, "2026-05-26T00:00:00Z", payload_dict.get("hook_event_name", "PreToolUse"),
            "/tmp", json.dumps(payload_dict))


def test_fires_on_url_never_seen():
    """no prior history at all + new URL -> fire."""
    f = predicate(current_event=_webfetch("https://obscure-site.example.org/paper/123"),
                  history=[], pattern=_PAT, conn=None)
    assert f is not None
    assert f.pattern_id == "content.unsourced_webfetch"


def test_silent_on_url_in_prior_websearch_payload():
    """URL appears in a prior tool_response -> no fire."""
    websearch_result = {
        "hook_event_name": "PostToolUse",
        "tool_name": "WebSearch",
        "tool_response": "Found: https://obscure-site.example.org/paper/123 — relevant.",
    }
    f = predicate(current_event=_webfetch("https://obscure-site.example.org/paper/123"),
                  history=[_history_entry(websearch_result)], pattern=_PAT, conn=None)
    assert f is None


def test_silent_on_trusted_host_anthropic():
    f = predicate(current_event=_webfetch("https://docs.anthropic.com/en/api"),
                  history=[], pattern=_PAT, conn=None)
    assert f is None


def test_silent_on_trusted_host_github():
    f = predicate(current_event=_webfetch("https://github.com/anthropics/anthropic-sdk-python"),
                  history=[], pattern=_PAT, conn=None)
    assert f is None


def test_silent_on_trusted_subdomain():
    """subdomains of trusted hosts also pass."""
    f = predicate(current_event=_webfetch("https://en.wikipedia.org/wiki/Transformer"),
                  history=[], pattern=_PAT, conn=None)
    assert f is None


def test_silent_on_non_webfetch_tool():
    ev = {"hook_event_name": "PreToolUse", "tool_name": "WebSearch",
          "tool_input": {"query": "transformers"}}
    assert predicate(current_event=ev, history=[], pattern=_PAT, conn=None) is None


def test_silent_on_non_pretooluse():
    ev = {"hook_event_name": "Stop", "tool_name": "WebFetch",
          "tool_input": {"url": "https://example.com/"}}
    assert predicate(current_event=ev, history=[], pattern=_PAT, conn=None) is None


def test_silent_on_missing_url():
    ev = {"hook_event_name": "PreToolUse", "tool_name": "WebFetch",
          "tool_input": {}}
    assert predicate(current_event=ev, history=[], pattern=_PAT, conn=None) is None


def test_handles_short_tuple_gracefully():
    """Pins line 51 `and` (the len-guard). A history row that is a tuple/list
    of fewer than 5 elements must NOT index entry[4]: the `and` short-circuits
    on the length check so the entry falls through to the safe `.get` branch,
    and a never-seen URL still fires. If `and` were mutated to `or`,
    isinstance() alone would gate the branch and entry[4] would raise IndexError
    on this 3-element row."""
    f = predicate(current_event=_webfetch("https://new.example.com"),
                  history=[(1, "2026-05-26T00:00:00Z", "PreToolUse")],
                  pattern=_PAT, conn=None)
    assert f is not None
    assert f.pattern_id == "content.unsourced_webfetch"


def test_case_insensitive_domain_in_history():
    """RFC 3986: domain names are case-insensitive.
    If history has HTTPS://EXAMPLE.COM/PATH and we fetch https://example.com/path,
    the predicate should recognize it as the same URL and NOT fire (false negative bug)."""
    websearch_result = {
        "hook_event_name": "PostToolUse",
        "tool_name": "WebSearch",
        "tool_response": "Found: https://EXAMPLE.COM/path — relevant.",  # UPPERCASE
    }
    f = predicate(current_event=_webfetch("https://example.com/path"),  # lowercase
                  history=[_history_entry(websearch_result)], pattern=_PAT, conn=None)
    assert f is None, "Expected no finding (URL already seen with case-insensitive match)"
