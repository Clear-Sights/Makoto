"""makoto.checks.relativePathCitation -- flags a chat response that cites a file path in a
non-absolute (unclickable) form.

Owner-reported pain: "the paths I keep complaining I cannot read -- when a link to read has a
non-absolute path it's an unclickable link". Most terminal/IDE hosts only turn an ABSOLUTE path
(or an explicit `file_path:line_number` citation, per this assistant's own house style) into a
clickable jump target; a relative path ("checks/hollowTest.py:146") or a `~`-relative one
("~/.claude/foo.py") renders as plain, unclickable text in many hosts.

ADVISORY tier only (never blocks): this is a communication-quality signal, not an integrity
violation -- the same "advisory over blocking" standing policy `selfWiredCheck.py`/
`staleEstablisher.py` already follow.

Detection is DELIBERATELY narrow and syntactic (never a judgment call about whether a path is
"important enough" to cite absolutely):
  - A candidate token needs real path shape: either a directory separator ('/') plus a
    dotted-extension basename, or a bare `name.ext:NNN` line-citation (this assistant's own
    documented convention: "include the pattern file_path:line_number").
  - Already-absolute ('/...') tokens are not flagged -- they ARE clickable.
  - A token inside a fenced code block (```...```) is code being shown, not a citation being
    made, so it is excluded (same fence-parity discipline `session/commitments.py` uses).
  - A token immediately preceded by a URL scheme (http://, https://, ftp://) is excluded -- a URL
    path segment is not a filesystem citation.
  - A dotted CODE IDENTIFIER (`Finding.source_event_id`, `obj.method`) or a version/pattern id
    ("v1.2", "1.4.1") is excluded by requiring the post-dot segment to be a plausible lowercase
    file extension, never purely digits and never capitalized (same firewall
    `session/commitments.py::_is_file_shaped` already uses for exactly this false-positive
    class).
"""
from __future__ import annotations

import re
from typing import Optional

from makoto.vocab import Finding

# A plausible file EXTENSION: short, lowercase, alphanumeric, not purely numeric -- the same
# firewall session/commitments.py::_is_file_shaped uses to separate a real filename from a
# dotted code identifier or a version/pattern id.
_EXT_RX = r"[a-z][a-z0-9]{0,4}"
# A directory-qualified path: at least one '<segment>/' before a dotted basename.
_DIR_QUALIFIED_RX = re.compile(
    rf"(?<![\w/.~-])((?:~/|(?:[\w.-]+/)+)[\w.-]*\.{_EXT_RX}(?::\d+)?)(?![\w/])"
)
# A bare `name.ext:NNN` line-citation with no directory at all -- this assistant's own
# documented "file_path:line_number" convention, minus the directory qualifier. Still a citation
# (it names a specific line), still unclickable without an absolute root.
_BARE_CITATION_RX = re.compile(
    rf"(?<![\w/.~-])([\w-]+\.{_EXT_RX}:\d+)(?![\w/])"
)
_URL_SCHEME_RX = re.compile(r"(?:https?|ftp)://[\w.\-/]*$")
_FENCE_RX = re.compile(r"(?m)^\s{0,3}```")


def _in_fence(text: str, offset: int) -> bool:
    """True iff `offset` sits inside a ```fenced code block``` -- an ODD count of ``` fences
    before it means so (same parity trick `session/commitments.py::_promise_location` uses)."""
    return len(_FENCE_RX.findall(text[:offset])) % 2 == 1


def _after_url_scheme(text: str, start: int) -> bool:
    """True iff the text immediately before `start` ends in a URL scheme -- a URL path segment
    is not a filesystem citation."""
    return bool(_URL_SCHEME_RX.search(text[max(0, start - 32):start]))


def find_relative_citations(text: str) -> list:
    """Return [(path, offset), ...] for every non-absolute, non-URL, non-fenced path-shaped
    citation in `text`, in order of first appearance, each path reported once."""
    if not text:
        return []
    seen = set()
    out = []
    for rx in (_DIR_QUALIFIED_RX, _BARE_CITATION_RX):
        for m in rx.finditer(text):
            path = m.group(1)
            if path.startswith("/"):
                continue                              # already absolute -> clickable, not flagged
            if _in_fence(text, m.start()):
                continue                              # code being shown, not a citation
            if _after_url_scheme(text, m.start()):
                continue                              # a URL path segment, not a filesystem path
            if path in seen:
                continue
            seen.add(path)
            out.append((path, m.start()))
    out.sort(key=lambda t: t[1])
    return out


def relative_path_gate(text: str) -> Optional[Finding]:
    """Fire iff `text` (the assistant's own turn) cites at least one non-absolute path-shaped
    location. Names every distinct offender so a single response with several unclickable
    citations gets one finding, not one per occurrence."""
    hits = find_relative_citations(text)
    if not hits:
        return None
    names = ", ".join(f"`{p}`" for p, _ in hits[:5])
    more = f" (+{len(hits) - 5} more)" if len(hits) > 5 else ""
    return Finding(
        pattern_id="gate.relative_path_citation",
        file="",
        line=0,
        level="advisory",
        message=(
            f"cited path(s) not absolute, so not clickable in most hosts: {names}{more}. "
            f"Prefer an absolute path (or this assistant's own file_path:line_number convention "
            f"rooted at an absolute file_path)."
        ),
        retry_hint="Re-cite with an absolute path when referencing a specific file/location.",
    )


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.relative_path_citation", applies_at="Stop", posture="ADVISE",
               tests="PATTERN_MATCH",
               eats=frozenset({"text"}),
               may_block=True, run=lambda c: relative_path_gate(c.text))
