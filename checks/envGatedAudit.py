"""pattern 1.2 predicate — env-gated audit/verification code (active-code AST).

Fires when a PreToolUse Write/Edit INTRODUCES, as REAL Python code (not a comment / string /
docstring mention), an ``if <env-read>:`` whose guarded body — OR the env-var key itself — NAMES
an integrity / audit / verification concept (``lexicons._INTEG_VOCAB``). Env-read =
``os.environ.get(...)``, ``os.getenv(...)``, ``os.environ[...]``, or the bare imported
``getenv(...)`` / ``environ.get(...)`` / ``environ[...]`` forms.

Materiality: gating an audit trail / verification check behind an env var means the check runs
ONLY when someone opts in — a silently-disable-able integrity check, i.e. a HOLLOWED word (the
audit survives in name while its guarantee is gutted). This is makoto's own CLAUDE.md convention
("Audit/verification code gated behind an env var (`if os.environ.get(...AUDIT...)`)").

Why AST, not the old string matcher (cert 2026-06-02, warning-tier-elimination:43, which CUT the
prior ``regex_file_predicate``): the old regex (1) fired on MENTIONS in comments/strings/docs
(instance-vs-mention FP) — it even targeted ``.md``, firing on CLAUDE.md describing the shape;
(2) required a literal ``AUDIT`` in the var NAME (its ``body_rx``), a flat FN on a BODY-only
signal like ``if os.environ.get("MAKOTO_SHADOW"): run_integrity_check()``; (3) matched only
``os.environ.get(`` — ``os.getenv()`` was a flat FN. The active-code AST gate
(``lib.factories.parse_introduced``) dissolves (1) — a comment / ``str`` Constant / docstring is
never a real ``ast.If``; checking the gated BODY's code identifiers (not just the var name)
dissolves (2); ``callee_chain`` matching both call forms + the subscript form dissolves (3).

NAME-AGNOSTIC: the integrity signal comes from the env-var KEY *or* a body code identifier, so it
is not tied to the literal substring ``AUDIT``. A bare feature flag
(``if os.getenv("DARK_MODE"): render()``) carries no integrity token in key or body and stays
silent — the discrimination the near-miss tests pin. The body-token scan reads only active code
identifiers (Name/Attribute), never ``str`` Constants, so a comparison value
(``if getenv("X") == "audit":``) cannot self-trigger.

ACKNOWLEDGED FN (precision-first, like 1.4/1.26): an env-gated audit whose only audit op sits in
the ``else`` branch, or whose integrity intent is hidden behind a fully-generic name in both key
AND body, evades. For a BLOCKING gate an FP (blocking honest code) is the binding harm, so the
fire is kept MATERIAL. ``makoto-allow`` honored by the factory. Knight-Leveson: stdlib ast + re.
"""
from __future__ import annotations
import ast
import re
from typing import Optional

from makoto.lexicons import _INTEG_VOCAB
from makoto.lib.factories import ast_introduced_predicate, callee_chain

from makoto.lexicons import _PY_FILE_RX as _TARGET_RX  # .py only — .md is prose (worst old FP was CLAUDE.md)
_INTEG_RX = re.compile(_INTEG_VOCAB, re.I)  # the shared L0 integrity vocabulary (single source; pattern 1.4 too)

# An env-var READ in CALL form (callee_chain) vs SUBSCRIPT form (value chain).
_ENV_CALL_CHAINS = {"os.getenv", "getenv", "os.environ.get", "environ.get"}
_ENV_SUBSCRIPT_CHAINS = {"os.environ", "environ"}


def _value_chain(node: ast.AST) -> str:
    """Dotted name of an Attribute/Name expression: ``os.environ`` -> 'os.environ', ``environ`` ->
    'environ'. The subscript-receiver companion to ``callee_chain`` (which handles Call.func)."""
    parts: list = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _is_env_read(node: ast.AST) -> bool:
    """True iff ``node`` reads an environment variable: ``os.getenv(...)`` / ``os.environ.get(...)`` /
    the bare imported ``getenv(...)`` / ``environ.get(...)`` (Call), or ``os.environ[...]`` /
    ``environ[...]`` (Subscript)."""
    if isinstance(node, ast.Call):
        return callee_chain(node) in _ENV_CALL_CHAINS
    if isinstance(node, ast.Subscript):
        return _value_chain(node.value) in _ENV_SUBSCRIPT_CHAINS
    return False


def _names_integrity_concept(node: ast.AST) -> bool:
    """True iff any ACTIVE code identifier (Name.id / Attribute.attr) in ``node``'s subtree names an
    integrity/audit/verification concept. ``str`` Constants are deliberately NOT consulted, so a
    comparison value (``== "audit"``) or a quoted example cannot self-trigger — only real code."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and _INTEG_RX.search(sub.id):
            return True
        if isinstance(sub, ast.Attribute) and _INTEG_RX.search(sub.attr):
            return True
    return False


def _env_key_names_integrity(test: ast.AST) -> bool:
    """True iff the env-var KEY string read in ``test`` names an integrity concept
    (``os.getenv("ENABLE_AUDIT")`` / ``os.environ["VERIFY_MODE"]``). Reads the first positional str
    arg of the env CALL, or the subscript key of ``os.environ[...]``."""
    for sub in ast.walk(test):
        key: Optional[ast.AST] = None
        if isinstance(sub, ast.Call) and _is_env_read(sub) and sub.args:
            key = sub.args[0]
        elif isinstance(sub, ast.Subscript) and _is_env_read(sub):
            key = sub.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and _INTEG_RX.search(key.value):
            return True
    return False


def _node_match(node: ast.AST) -> Optional[str]:
    """Match an ``if <env-read>:`` whose env-var KEY, or whose guarded (then-branch) body, names an
    integrity/audit/verification concept."""
    if not isinstance(node, ast.If):
        return None
    if not any(_is_env_read(sub) for sub in ast.walk(node.test)):
        return None                                  # the gate condition must READ an env var
    if _env_key_names_integrity(node.test):
        return "env-gated audit (env-var key names an integrity/verification concept)"
    if any(_names_integrity_concept(stmt) for stmt in node.body):
        return "env-gated audit (the env-gated body runs an integrity/audit/verification op)"
    return None


predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_node_match)


from makoto.checks._loader import Check as _Check
RETRY_HINT = "Don't gate an audit/verification check behind an env var — `if os.getenv('...'): <audit>` makes the check opt-in, so it silently does nothing unless someone sets the flag (a hollowed integrity check). Run the check unconditionally; if a genuinely-optional diagnostic is intended, annotate the line with `makoto-allow: <reason>`."
DESCRIPTION = 'env-gated audit/verification code (if os.environ.get(...)/os.getenv(...) gating an integrity op)'

CHECK = _Check(id='content.env_gated_audit', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('os.environ.get', 'os.getenv', 'os.environ['), retry_hint=RETRY_HINT, description=DESCRIPTION)
