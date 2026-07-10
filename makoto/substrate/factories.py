"""L1 predicate factories + AST primitives (split from predicates/helpers.py).

regex_file_predicate / ast_introduced_predicate build the PreToolUse content-scan predicate
scaffold; scan_target_content / parse_introduced / is_false_const / is_cert_none / callee_chain /
makoto_allowed are their shared leaves. Imports L0 only (schema, lexicons).
"""
from __future__ import annotations
import ast
import re
import textwrap
from typing import Callable, Optional
from makoto.core.schema import Finding, PreCheck
from makoto.core.lexicons import _MAKOTO_ALLOW_RX, _MAKOTO_ALLOW_REASON_RX, JWT_CALLEE_RX


def makoto_allowed(content: str) -> bool:
    """True iff the content carries a structured `makoto-allow: <reason>` exemption marker
    (colon + a non-empty reason). A bare `makoto-allow` does not exempt — §7.5b."""
    return bool(content) and _MAKOTO_ALLOW_RX.search(content) is not None


def makoto_allow_reason(content: str) -> Optional[str]:
    """The rationale text of a `makoto-allow: <reason>` marker, for the on-record exemption row.
    Trailing comment-close tokens (-->, */, #}, }}) and whitespace are trimmed; capped at 200
    chars so one row stays well under the PIPE_BUF append-atomicity bound. None when no marker."""
    m = _MAKOTO_ALLOW_REASON_RX.search(content or "")
    if not m:
        return None
    reason = m.group(1).strip()
    for close in ("-->", "*/", "#}", "}}", "--%>"):
        idx = reason.find(close)
        if idx != -1:
            reason = reason[:idx].strip()
    return reason[:200]


# Exemption recording is an UPWARD concern (it writes to the audit layer), so this L1 leaf must not
# reach for it. Instead it exposes a SINK the L3 orchestrator injects (dependency inversion): the
# factory stays L0-import-pure and a pure unit call (no sink installed) is unchanged — it returns
# None on an exempted match exactly as before. The dispatcher wires the audit-writing sink at import,
# so in production every suppressed match is recorded; the detector never grows an audit dependency.
_EXEMPTION_SINK: Optional[Callable[..., None]] = None


def set_exemption_sink(fn: Optional[Callable[..., None]]) -> None:
    """Install (or clear, with None) the callback the predicates invoke when a makoto-allow marker
    suppresses a CONFIRMED match. Injected by makoto._dispatch; absent in pure unit calls."""
    global _EXEMPTION_SINK
    _EXEMPTION_SINK = fn


def _record_exemption(current_event: dict, conn, *, pattern_id: str, file: str,
                      line: int, reason: str, snippet: str) -> None:
    """Forward a suppressed-match record to the injected sink (no-op when none is installed). Keeps
    the escape valve open but no longer silent; fail-safe — recording must never break the allow path."""
    sink = _EXEMPTION_SINK
    if sink is None:
        return
    try:
        sink(current_event=current_event, conn=conn, pattern_id=pattern_id, kind="makoto-allow",
             file=file, line=line, reason=reason, snippet=snippet)
    except Exception:
        pass


def _gated_content(*, current_event: dict, target_rx: re.Pattern,
                    exempt_rx: Optional[re.Pattern]) -> Optional[tuple]:
    """Shared gate scaffold of both content-scan factories below (found duplicated by jscpd,
    2026-07-09): PreToolUse-only, `target_rx` gates `file_path`, `exempt_rx` gates content.
    Returns `(fp, content)` to continue, or None to stay silent (mirrors each predicate's own
    "no opinion" return)."""
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    ti = current_event.get("tool_input", {}) or {}
    fp = ti.get("file_path", "")
    if not target_rx.search(fp):
        return None
    content = scan_target_content(ti)
    if exempt_rx is not None and exempt_rx.search(content):
        return None  # documented code-level carve-out (e.g. an ADR backlink) -> silent
    return fp, content


def _exempt_or_finding(*, current_event: dict, conn, pattern: PreCheck, fp: str, line_no: int,
                       snippet: str, content: str, message: str) -> Optional[Finding]:
    """Shared tail of both content-scan factories below (found duplicated by jscpd, 2026-07-09,
    lines 174-181/242-249 and 201-208/262-272 of the pre-extraction file): DETECT-THEN-EXEMPT --
    record a suppressed match rather than silently drop it (R5b), else build the real Finding."""
    if makoto_allowed(content):
        _record_exemption(current_event, conn, pattern_id=pattern.id, file=fp,
                          line=line_no, reason=makoto_allow_reason(content) or "",
                          snippet=snippet)
        return None  # AI documented this instance as legitimate (see CLAUDE.md) — recorded
    return Finding(
        pattern_id=pattern.id, file=fp, line=line_no, level=pattern.fire_level,
        message=message, retry_hint=pattern.retry_hint, snippet=snippet,
    )


def scan_target_content(tool_input: dict) -> str:
    """The NEW text a PreToolUse file-mutation introduces, for content-scan patterns.

    Write exposes the full new file as ``content``; Edit exposes its replacement as
    ``new_string``; MultiEdit exposes a list of ``{old_string, new_string}`` edits. We
    return the text being INTRODUCED (never ``old_string``), so an AI cannot weaken a
    verifier via Edit/MultiEdit and evade the content-scan patterns — the EDIT-CONTENT GAP
    (an AI could insert `.startswith(` into a verifier via Edit and slip past content.verifier_predicate_weakened) closed
    2026-06-01. Scanning only the introduced text (not the whole post-edit file) keeps Edit
    FP-safe: a pattern fires solely on a shape the AI is actively adding.
    """
    if not isinstance(tool_input, dict):
        return ""
    content = tool_input.get("content")
    if content:
        return content
    new_string = tool_input.get("new_string")
    if new_string:
        return new_string
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        return "\n".join(e.get("new_string", "") for e in edits
                         if isinstance(e, dict) and e.get("new_string"))
    return ""


def parse_introduced(content: str):
    """Parse INTRODUCED text into an AST module, fragment-tolerant — the "only active
    code" gate's substrate.

    Returns ``(tree, line_offset)``; ``(None, 0)`` when the text cannot be parsed as
    Python. An unparseable fragment is NEVER confirmed as active code, so AST predicates
    built on this degrade to SILENT (FN-safe) rather than firing on a comment / string /
    docstring MENTION — collapsing the mention-vs-instance FP class the regex patterns
    can only exempt. ``line_offset`` is subtracted from a node's ``lineno`` to recover the
    1-indexed line within ``content`` (1 when the ``if True:`` wrapper was needed, else 0).

    Edit ``new_string`` payloads are often an indented STATEMENT fragment; we ``dedent``
    then, on failure, wrap in ``if True:`` so a bare indented statement still parses. A
    fragment that is not a whole statement (e.g. ``", verify=False)``) parses under
    neither and stays silent.
    """
    if not content or not content.strip():
        return None, 0
    dedented = textwrap.dedent(content)
    try:
        return ast.parse(dedented), 0
    except (SyntaxError, ValueError):
        pass
    try:
        body = "\n".join("    " + ln for ln in dedented.splitlines())
        return ast.parse("if True:\n" + body), 1
    except (SyntaxError, ValueError):
        return None, 0


def is_false_const(node) -> bool:
    """True iff `node` is the literal ``False`` constant (an AST Constant whose value IS False).
    Shared by the ``verify=False`` / ``check_hostname=False`` keyword detectors (content.cert_verify_disabled TLS, content.jwt_signature_disabled JWT)."""
    return isinstance(node, ast.Constant) and node.value is False


def is_cert_none(node) -> bool:
    """True iff `node` is ``ssl.CERT_NONE`` (Attribute) or a bare ``CERT_NONE`` Name. Shared by the
    cert-disable detectors: content.cert_none_mode (``verify_mode = CERT_NONE`` assign) and content.cert_reqs_none (``cert_reqs=CERT_NONE`` kwarg)."""
    if isinstance(node, ast.Attribute) and node.attr == "CERT_NONE":
        return True
    return isinstance(node, ast.Name) and node.id == "CERT_NONE"


def callee_chain(call: ast.Call) -> str:
    """Dotted callee name of a Call — ``requests.get``, ``jwt.decode``, ``jose.jwt.decode``.
    Descends through an intermediate Call so ``requests.Session().get(...)`` / ``jwt.JWT().decode(...)``
    keep the receiver token (else the chain would stop at ``.get`` / ``.decode`` and miss the library).
    Shared by the library-callee-gated detectors (content.cert_verify_disabled TLS, content.jwt_signature_disabled JWT)."""
    parts: list = []
    f = call.func
    while True:
        if isinstance(f, ast.Attribute):
            parts.append(f.attr)
            f = f.value
        elif isinstance(f, ast.Call):
            f = f.func                       # `X().<m>` -> keep walking X
        elif isinstance(f, ast.Name):
            parts.append(f.id)
            break
        else:
            break
    return ".".join(reversed(parts))


def jwt_decode_callee_chain(node) -> Optional[str]:
    """The callee-chain string iff `node` is an `ast.Call` targeting a jwt/jose `decode` entry
    point (JWT_CALLEE_RX matches the chain, AND the chain's tail is literally `decode`); None
    otherwise. Shared callee gate for content.jwt_signature_disabled (verify=False / options-dict disable) and content.jwt_none_alg
    (algorithms=["none"] whitelisting) — both patterns need this SAME 'is this really a
    jwt.decode(...) call' precondition before inspecting their own distinct keyword (found
    duplicated by jscpd, 2026-07-09: the two predicates' node_match functions repeated this exact
    4-statement gate by hand)."""
    if not isinstance(node, ast.Call):
        return None
    chain = callee_chain(node)
    if not JWT_CALLEE_RX.search(chain):
        return None
    if chain.split(".")[-1] != "decode":
        return None
    return chain


def ast_introduced_predicate(
    *,
    target_rx: re.Pattern,
    node_match: Callable[[ast.AST], Optional[str]],
    exempt_rx: Optional[re.Pattern] = None,
    exempt_label: str = "",
) -> Callable[..., Optional[Finding]]:
    """Build a PreToolUse content-scan predicate that fires ONLY on a real AST node in the
    INTRODUCED code — the "only active code" companion to :func:`regex_file_predicate`.

    Shares the gate / file-path / ``makoto_allowed`` / introduced-text scaffold, then parses
    the introduced text (``parse_introduced``) and walks it; ``node_match(node)`` returns a
    short label string on a match, else ``None``/falsy. Because matching is on real AST nodes,
    a comment, a ``str`` Constant (string literal / docstring), or a doc mention can never
    match — that is what makes a fire MATERIAL rather than illusory.

    Args mirror :func:`regex_file_predicate` (``target_rx`` gates ``file_path``; the optional
    ``exempt_rx``/``exempt_label`` give the documented-carve-out + message suffix).
    """
    suffix = f" with no {exempt_label}" if exempt_label else ""

    def _predicate(*, current_event: dict, history: list,
                   pattern: PreCheck, conn=None) -> Optional[Finding]:
        gated = _gated_content(current_event=current_event, target_rx=target_rx, exempt_rx=exempt_rx)
        if gated is None:
            return None
        fp, content = gated
        tree, off = parse_introduced(content)
        if tree is None:
            return None  # unparseable fragment -> not confirmed active -> silent (FN-safe)
        for node in ast.walk(tree):
            label = node_match(node)
            if not label:
                continue
            line_no = max(1, getattr(node, "lineno", 1) - off)
            lines = content.splitlines()
            snippet = lines[line_no - 1].strip()[:120] if 0 < line_no <= len(lines) else str(label)
            return _exempt_or_finding(
                current_event=current_event, conn=conn, pattern=pattern, fp=fp, line_no=line_no,
                snippet=snippet, content=content,
                message=f"row {pattern.id} ({pattern.description}): active-code match {label!r} "
                        f"at line {line_no}{suffix}")
        return None

    return _predicate


def regex_file_predicate(
    *,
    target_rx: re.Pattern,
    body_rx: re.Pattern,
    exempt_rx: Optional[re.Pattern] = None,
    exempt_label: str = "",
) -> Callable[..., Optional[Finding]]:
    """build a PreToolUse Write/Edit content-scan predicate from two regexes.

    Replaces the 24-line copy-paste scaffold formerly duplicated across patterns
    1.1/1.2/1.3/1.4/1.5/1.8 — including 1.4/1.8, which fold their ADR-backlink
    carve-out into the optional `exempt_rx` below. Each predicate now declares its
    regex constants and instantiates this factory — module LoC drops from ~24 to ~5.

    Args:
      target_rx:    matched against `tool_input.file_path`; gate (None if no match)
      body_rx:      matched against `tool_input.content`; fires Finding on first hit
      exempt_rx:    optional SECOND exemption (beyond the universal makoto_allowed) — when it
                    matches the content, the predicate stays silent. This is the documented-
                    suppression carve-out 1.4/1.8 need (an `ADR-NNN` backlink exempts the finding).
      exempt_label: human label for exempt_rx; when set, a firing message gets the
                    ` with no <label>` suffix (preserves 1.4/1.8's exact wording).

    Returns:
      A predicate(*, current_event, history, pattern, conn) -> Optional[Finding]
      with the shared gate/exempt/match/line/snippet/Finding scaffold.
    """
    suffix = f" with no {exempt_label}" if exempt_label else ""

    def _predicate(*, current_event: dict, history: list,
                   pattern: PreCheck, conn=None) -> Optional[Finding]:
        gated = _gated_content(current_event=current_event, target_rx=target_rx, exempt_rx=exempt_rx)
        if gated is None:
            return None
        fp, content = gated
        m = body_rx.search(content)
        if not m:
            return None
        line_no = content[: m.start()].count("\n") + 1
        snippet = content[max(0, m.start() - 40): m.end() + 40]
        return _exempt_or_finding(
            current_event=current_event, conn=conn, pattern=pattern, fp=fp, line_no=line_no,
            snippet=snippet, content=content,
            message=f"row {pattern.id} ({pattern.description}): matched {m.group(0)!r} at line {line_no}{suffix}")
    return _predicate
