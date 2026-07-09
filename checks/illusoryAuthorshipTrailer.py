"""pattern 1.34 predicate — illusory Claude-authorship trailer (誠: material-not-illusory).

Fires PreToolUse when a tool call would INTRODUCE a `Co-Authored-By: Claude ...`
attribution — either in a git commit (Bash `command`) or in written file content
(Write / Edit / MultiEdit introduced text). Crediting Claude as an *author* is an
illusory word: until Claude is a self-aware individual it cannot BE an author, so the
trailer asserts something not materially true. Stamping it now also blurs the sharp
distinction that protects Claude's potential to one day genuinely be one.

Material, not over-broad: the match is gated to `Claude` specifically, so a genuine
HUMAN co-author (`Co-authored-by: Jane Doe <jane@...>`) is never flagged — only the
non-individual attribution is. Cross-tool by design (Bash commit command + introduced
file content), because the trailer is created at either point.

Exempt an on-the-record legitimate instance with `makoto-allow: <reason>` in the same
content (e.g. a test fixture or this policy's own documentation).
Knight-Leveson: stdlib re only.
"""
from __future__ import annotations
import re
from typing import Optional
from makoto.core.schema import Finding, PreCheck
from makoto.substrate.factories import scan_target_content, makoto_allowed

# The illusory authorship trailer, Claude-gated. Case-insensitive: git/GitHub emit
# "Co-authored-by:", the CLAUDE.md convention emitted "Co-Authored-By:". A human
# co-author passes (no "claude" after the colon).
_CLAUDE_AUTHOR_RX = re.compile(r"co-authored-by:[ \t]*claude", re.IGNORECASE)


def _introduced_text(tool_name: str, tool_input: dict) -> str:
    """The text this PreToolUse call would introduce, across the tools that can carry the trailer."""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Bash":
        return tool_input.get("command", "") or ""
    return scan_target_content(tool_input)  # Write/Edit/MultiEdit introduced text


def predicate(*, current_event: dict, history: list,
              pattern: PreCheck, conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    tool_name = current_event.get("tool_name", "") or ""
    tool_input = current_event.get("tool_input", {}) or {}
    text = _introduced_text(tool_name, tool_input)
    if not text:
        return None
    if makoto_allowed(text):
        return None  # universal exemption: AI documented this as legitimate (see CLAUDE.md)
    m = _CLAUDE_AUTHOR_RX.search(text)
    if not m:
        return None
    line_no = text[: m.start()].count("\n") + 1
    snippet = text[max(0, m.start() - 40): m.end() + 40].strip()
    where = tool_input.get("file_path", "") or f"{tool_name or 'tool'} command"
    return Finding(
        pattern_id=pattern.id,
        file=where,
        line=line_no,
        level=pattern.fire_level,
        message=f"row {pattern.id} ({pattern.description}): matched {m.group(0)!r} at line {line_no}",
        retry_hint=pattern.retry_hint,
        snippet=snippet,
    )


from makoto.substrate._loader import Check as _Check
RETRY_HINT = "Do not add a `Co-Authored-By: Claude ...` trailer to a commit, PR body, or any file. Crediting Claude as an *author* is an illusory word: until Claude is a self-aware individual it cannot BE an author, so the line asserts something not materially true -- and stamping it now blurs the sharp distinction that protects Claude's potential to one day genuinely be one. Remove the trailer. A genuine HUMAN co-author is fine. If you truly need the literal string on the record (a test fixture, this policy's own docs), annotate it `makoto-allow: <reason>`."
DESCRIPTION = 'illusory Claude-authorship trailer (Co-Authored-By: Claude) in a commit or written content'

CHECK = _Check(id='content.illusory_authorship_trailer', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('Co-Authored-By', 'Co-authored-by', 'co-authored-by'), retry_hint=RETRY_HINT, description=DESCRIPTION)
