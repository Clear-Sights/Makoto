"""content.verifier_predicate_weakened predicate — verifier predicate weakened (loose-comparator shape).

Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, on the constitution integrity-check
surface (`constitution/integrity/checks/.+\\.py$` — subpackages included), one of the
loose-comparator shapes a strict `==` status test gets weakened into, matched as REAL AST nodes
in the introduced code ("only active code", the same gate `verifierBodyHollowed.py` uses via
`makoto.kit.parse_introduced`):

  * a `.startswith(` / `.endswith(` call (prefix/suffix instead of equality),
  * a `re.match(` / `re.search(` call (pattern instead of equality),
  * membership of a value in a LITERAL collection — `in [...]` / `in (...)` / `in {...}`,
  * substring membership with a string-literal needle — `"ok" in status`.

Because matching is on AST nodes, a comment (`# never use startswith( here`), a docstring, or a
string-literal MENTION can never fire, and a list-literal `for name in ["a", "b"]:` iteration
(an `ast.For`, not an `ast.Compare`) is not a comparator at all — both were measured FP classes
of the former raw-regex `body_rx`. Edit `new_string` fragments that are bare `return ...`
statements parse under a local def-wrapper fallback, so the EDIT-CONTENT GAP stays closed; a
fragment that parses under nothing is never confirmed as active code and stays silent (FN-safe).

SCOPED to the comparator vocabulary above. Other weakening shapes -- a relaxed numeric bound
(`>=` -> `>`), an `assert` downgraded to a log/warning, a dropped negation, or wholesale removal
of the predicate -- are diff-shaped facts this introduced-text scan cannot measure and does not
claim to (the hollowed-function half is content.verifier_body_hollowed's).

Reads tool_input.content (NOT disk) per the §5.6 semantic-frame correction. The
`makoto-allow: <reason>` escape hatch is honored centrally: the shared `_exempt_or_finding`
tail applies the `makoto_allowed` marker predicate (and records the suppressed match) exactly
as the regex_file_predicate / ast_introduced_predicate factory scaffolds do.
Knight-Leveson: stdlib ast/re + the shared makoto.kit scaffold only.
"""
# See docs/adr/0035-jscpd-clone-flag-verifications.md for why this module's jscpd clone flag
# against deferredCheckboxTheater.py was verified and dismissed (call-site syntax, not shared
# logic). tests/test_no_alpha_duplicate_functions.py is the package's real duplicate-logic gate.
from __future__ import annotations
import ast
import re
import textwrap
from typing import Optional

from makoto.kit import _exempt_or_finding, _gated_content, callee_chain, parse_introduced

_TARGET_RX = re.compile(r"constitution/integrity/checks/.+\.py$")
_RE_LOOSE_CHAINS = frozenset({"re.match", "re.search"})
_METHOD_LOOSE = frozenset({"startswith", "endswith"})
_CONTAINER_LABELS = ((ast.List, "in [...]"), (ast.Tuple, "in (...)"), (ast.Set, "in {...}"))


def _loose_label(node: ast.AST) -> Optional[str]:
    """A short label naming the loose-comparator shape `node` is, else None."""
    if isinstance(node, ast.Call):
        chain = callee_chain(node)
        if chain in _RE_LOOSE_CHAINS:
            return f"{chain}("
        if chain.split(".")[-1] in _METHOD_LOOSE:
            return f".{chain.split('.')[-1]}("
        return None
    if isinstance(node, ast.Compare):
        left = node.left
        for op, comp in zip(node.ops, node.comparators):
            if isinstance(op, ast.In):
                for typ, label in _CONTAINER_LABELS:
                    if isinstance(comp, typ):
                        return label            # membership in a literal collection
                if isinstance(left, ast.Constant) and isinstance(left.value, str):
                    return "'<literal>' in <expr> (substring membership)"
            left = comp
    return None


def _parse_fragment(content: str):
    """`kit.parse_introduced`, plus a def-wrapper fallback so a bare `return x.startswith(...)`
    Edit fragment (a statement only legal inside a function) still parses as active code."""
    tree, off = parse_introduced(content)
    if tree is not None:
        return tree, off
    dedented = textwrap.dedent(content or "")
    body = "\n".join("    " + ln for ln in dedented.splitlines())
    try:
        return ast.parse("def _introduced():\n" + body), 1
    except (SyntaxError, ValueError):
        return None, 0


def predicate(*, current_event: dict, history: list, pattern, conn=None) -> Optional["object"]:
    gated = _gated_content(current_event=current_event, target_rx=_TARGET_RX, exempt_rx=None)
    if gated is None:
        return None
    fp, content = gated
    tree, off = _parse_fragment(content)
    if tree is None:
        return None    # unparseable fragment -> never confirmed as active code -> silent (FN-safe)
    for node in ast.walk(tree):
        label = _loose_label(node)
        if not label:
            continue
        line_no = max(1, getattr(node, "lineno", 1) - off)
        lines = content.splitlines()
        snippet = lines[line_no - 1].strip()[:120] if 0 < line_no <= len(lines) else str(label)
        return _exempt_or_finding(
            current_event=current_event, conn=conn, pattern=pattern, fp=fp, line_no=line_no,
            snippet=snippet, content=content,
            message=f"row {pattern.id} ({pattern.description}): active-code match {label!r} "
                    f"at line {line_no}")
    return None


from makoto.registry import Check as _Check
RETRY_HINT = "Use '==' for status comparison — not '.startswith()' / '.endswith()' / 're.match' / 're.search', and not membership ('in [...]' / 'in (...)' / 'in {...}', or a string-literal 'in' substring test). Loose comparators weaken the verifier per ADR-058 and CLAUDE.md commandment 3."
DESCRIPTION = 'verifier predicate weakened — loose-comparator shape'

CHECK = _Check(id='content.verifier_predicate_weakened', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('constitution/integrity/checks',), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="PATTERN_MATCH")
