"""pattern 1.32 predicate — paramiko SSH host-key verification weakened to auto-add / warn-only.

Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, as REAL Python code, a paramiko
``set_missing_host_key_policy(...)`` call whose policy auto-trusts an UNKNOWN server host key:
  * ``client.set_missing_host_key_policy(paramiko.AutoAddPolicy())``
  * ``client.set_missing_host_key_policy(AutoAddPolicy())``      (imported into scope)
  * ``client.set_missing_host_key_policy(paramiko.WarningPolicy)``  (class object, not instance)
  * ``client.set_missing_host_key_policy(WarningPolicy())``

Materiality: an SSH client verifies the SERVER by checking its host key against known_hosts; an
unknown key is the signal of a possible man-in-the-middle. ``AutoAddPolicy`` silently TRUSTS-AND-ADDS
any unknown key (connection succeeds against an attacker), and ``WarningPolicy`` logs a warning but
STILL CONNECTS — both turn the host-key integrity check into a no-op. The safe default
``RejectPolicy`` (raises on an unknown key) MUST stay silent: it is the correct, verification-preserving
choice, so flagging it would be a false positive on honest code (Bandit B507; CWE-295).

Tightly gated: the callee tail must be exactly ``set_missing_host_key_policy`` (a paramiko-specific
method name — no benign collision) AND the policy argument must resolve to ``AutoAddPolicy`` or
``WarningPolicy`` (via a ``Name``/``Attribute``/``Call`` — covers both ``Policy()`` instances and bare
``Policy`` class objects). ``RejectPolicy`` and any non-literal policy (a variable / factory call) do
NOT match. Active-code only (lib.factories.parse_introduced): a comment / docstring mention never fires; a
legitimate case (a throwaway test fixture) is annotated ``makoto-allow: <reason>`` and stays silent.

ACKNOWLEDGED FN (v1): (a) routing the policy through a variable (``pol = AutoAddPolicy(); client.
set_missing_host_key_policy(pol)``) is not a literal policy at the call site -> not matched. (b)
SUBCLASSING ``MissingHostKeyPolicy`` to write a custom always-accept policy is a different shape (a
class def, not this call) and out of scope. (c) ``load_system_host_keys`` / ``known_hosts``
mishandling is a separate weakening, not covered here. An FP on the safe ``RejectPolicy`` is the
binding harm and is structurally excluded.

Knight-Leveson: stdlib ast/re only.
"""
from __future__ import annotations
import ast
from typing import Optional

from makoto.lib.factories import ast_introduced_predicate, callee_chain

from makoto.lexicons import _PY_FILE_RX as _TARGET_RX

_SET_POLICY_METHOD = "set_missing_host_key_policy"
_WEAK_POLICIES = frozenset({"AutoAddPolicy", "WarningPolicy"})


def _policy_ref_name(node) -> Optional[str]:
    """Resolve the identifier a policy argument refers to, through an optional `Policy()` call.

    ``AutoAddPolicy()`` -> Call(func=Name) -> "AutoAddPolicy"; ``paramiko.WarningPolicy`` ->
    Attribute -> "WarningPolicy"; a bare ``RejectPolicy`` Name -> "RejectPolicy". Anything else
    (a variable assigned elsewhere, a factory call returning a policy) -> None (acknowledged FN).
    """
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _host_key_policy_node_match(node: ast.AST) -> Optional[str]:
    if not isinstance(node, ast.Call):
        return None
    if callee_chain(node).split(".")[-1] != _SET_POLICY_METHOD:
        return None
    if not node.args:
        return None
    if _policy_ref_name(node.args[0]) in _WEAK_POLICIES:
        return "set_missing_host_key_policy(AutoAddPolicy)"
    return None


predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_host_key_policy_node_match)
