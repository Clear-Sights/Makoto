"""makoto.substrate._planNode -- the declared-Plan / contract-dependency shape (SPEC-5 Makoto
absorbs Assay). Ported BY SHAPE (rule 5 -- copy, never import) from Assay's
`assay/assay/plan/node.py` (the ``PlanNode`` frozen dataclass) + `assay/assay/plan/gaps.py`
(the ``Plan`` container + the GAP rule), combined into ONE Makoto module per the merge plan.
Logic is unchanged from Assay's own; only the import path/home moved.

Underscore-prefixed (deviating from the merge plan's literal ``checks/planNode.py`` path --
see the SPEC-5 Task's own DEFERRED.md-adjacent note in the landing commit): this module is
package PLUMBING, not a detector -- it exports no ``CHECK``/``GATE`` and answers no hook event
directly. Every other non-detector file in this package (``_shared.py``, ``_primitives.py``,
``_loader.py``, ``_declared.py``) is underscore-prefixed so ``checks._loader``'s scan skips it;
a bare ``planNode.py`` would instead be treated as an ORPHAN detector module (no CHECK export)
by ``checks.undeclaredFalsifiable``'s completeness audit, a false completeness-drift signal
for a file that was never meant to be a detector. Consumers: ``makoto/plan.py`` (the sqlite
persistence layer) and ``makoto/checks/{contractOrder,staleEstablisher}.py`` (the two checks
built over this grammar).

  * ``PlanNode`` -- one declared step: operation ``what`` on operand-name ``passthrough`` at
    location ``where``, advancing ``status`` OPEN -> DONE. ``passthrough`` is the recurrence
    trigger the gap scan reads BY NAME (deps are gaps in the ledger, no explicit DAG); it is the
    declared IDENTIFIER, never a basename of the argument.
  * ``Plan`` -- an ORDERED list of ``PlanNode``. A dependency is NEVER a declared edge -- it
    surfaces as a GAP read off the ledger BY NAME: the earlier node(s) that established this
    node's passthrough-name, still open.

AGNOSTIC: a node holds only structural locators (an op token, an operand name, a location);
this module orders / validates / (de)serializes them, never their work-content meaning. PURE,
STORAGE-AGNOSTIC: ``rows``/``from_rows``/``from_jsonl`` are text<->object codecs only -- no
file or DB I/O anywhere in this module. IMPORTS ONLY stdlib.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, List, Optional

# node status (the append-only advance: OPEN -> DONE)
OPEN = "open"
DONE = "done"


@dataclass(frozen=True)
class PlanNode:
    """One declared step: operation ``what`` on operand-name ``passthrough`` at ``where``.

    ``id`` is the node's stable key; it defaults to the deterministic composite
    ``"<what>::<passthrough>::<where>"``. ``status`` is OPEN or DONE. ``passthrough`` is the
    declared identifier (the recurrence trigger the gap scan reads BY NAME), never a basename
    of the argument.
    """

    what: str
    passthrough: str
    where: str
    id: str = ""
    status: str = OPEN

    def __post_init__(self) -> None:
        """Default ``id`` to the ``"<what>::<passthrough>::<where>"`` composite when unset."""
        if not self.id:
            object.__setattr__(self, "id", f"{self.what}::{self.passthrough}::{self.where}")


class Plan:
    """A declared plan: an ORDERED list of ``PlanNode`` whose partial order is the GAP rule.

    Order is significant -- it IS the ledger order the gap scan reads. The plan never stores a
    declared edge; every dependency is derived on read from the passthrough-name recurrence.
    """

    def __init__(self) -> None:
        self._nodes: List[PlanNode] = []

    # --- construction -------------------------------------------------------
    def add_node(
        self, what: str, passthrough: str, where: str, *, id: str = "", status: str = OPEN
    ) -> PlanNode:
        """Declare a node at the END of the plan, immutably. Re-adding an IDENTICAL node
        (same id -> same what/passthrough/where) is a no-op that returns the existing node.
        Re-adding the same id with a DIFFERENT triple raises ``ValueError``. A newly declared
        node starts OPEN. Returns the stored node."""
        node = PlanNode(what=what, passthrough=passthrough, where=where, id=id, status=status)
        for existing in self._nodes:
            if existing.id == node.id:
                if (
                    existing.what == node.what
                    and existing.passthrough == node.passthrough
                    and existing.where == node.where
                ):
                    return existing
                raise ValueError(f"node {node.id!r} already declared with a different shape")
        self._nodes.append(node)
        return node

    # --- advance ------------------------------------------------------------
    def mark_done(self, id: str) -> None:
        """Advance the node ``id`` to DONE in place (``KeyError`` if never declared)."""
        for i, node in enumerate(self._nodes):
            if node.id == id:
                self._nodes[i] = PlanNode(
                    what=node.what,
                    passthrough=node.passthrough,
                    where=node.where,
                    id=node.id,
                    status=DONE,
                )
                return
        raise KeyError(id)

    # --- resolution (a live call -> the declared node it advances) ----------
    def resolve(self, where: str, what: Optional[str] = None) -> Optional[str]:
        """Return the id of the declared node a live call at ``where`` advances, else ``None``.
        Prefers an exact ``(where, what)`` match; falls back to the FIRST node at ``where``.
        Among equals prefers the first OPEN node, else the first match."""
        exact = [n for n in self._nodes if n.where == where and (what is None or n.what == what)]
        pool = exact if exact else [n for n in self._nodes if n.where == where]
        if not pool:
            return None
        for n in pool:
            if n.status == OPEN:
                return n.id
        return pool[0].id

    # --- the GAP rule (dependencies as gaps, read off the ledger by name) ---
    def _index(self, id: str) -> int:
        for i, n in enumerate(self._nodes):
            if n.id == id:
                return i
        raise KeyError(id)

    def unmet_deps(self, id: str) -> set:
        """Return the GAP -- earlier nodes sharing ``id``'s passthrough-name not yet DONE.
        ``KeyError`` if ``id`` is absent. The FIRST node to name a passthrough has no earlier
        same-name node, so its gap set is empty."""
        idx = self._index(id)
        node = self._nodes[idx]
        return {
            earlier.id
            for earlier in self._nodes[:idx]
            if earlier.passthrough == node.passthrough and earlier.status != DONE
        }

    def order_violation(self, id: str) -> bool:
        """``True`` iff an earlier node that established ``id``'s passthrough-name is not yet
        DONE (``KeyError`` if ``id`` is absent). Equivalent to ``bool(self.unmet_deps(id))``."""
        return bool(self.unmet_deps(id))

    # --- the forgetting / passthrough-recurrence home (name -> location) ----
    def passthrough_locations(self) -> dict:
        """Return ``{passthrough-name -> set-of-WHEREs}`` -- the no-forgetting multiset."""
        out: dict = {}
        for n in self._nodes:
            out.setdefault(n.passthrough, set()).add(n.where)
        return out

    # --- reads --------------------------------------------------------------
    def open_nodes(self) -> set:
        """Return the set of ids of nodes whose ``status`` is OPEN."""
        return {n.id for n in self._nodes if n.status == OPEN}

    def remainder(self) -> set:
        """Return the open nodes -- the Stop gate's hint (the unfinished remainder)."""
        return self.open_nodes()

    def nodes(self) -> List[PlanNode]:
        """Return the declared nodes in plan (ledger) order -- a shallow copy."""
        return list(self._nodes)

    # --- record (serialization; text<->object only, no I/O) -----------------
    def rows(self) -> list:
        """Return the node rows as plain dicts, in PLAN ORDER (order is load-bearing)."""
        return [
            {
                "id": n.id,
                "what": n.what,
                "passthrough": n.passthrough,
                "where": n.where,
                "status": n.status,
            }
            for n in self._nodes
        ]

    @classmethod
    def from_rows(cls, rows: Iterable[dict]) -> "Plan":
        """Rebuild a ``Plan`` from row dicts (inverse of ``rows``), preserving order."""
        plan = cls()
        for row in rows:
            plan._nodes.append(
                PlanNode(
                    what=row.get("what", ""),
                    passthrough=row.get("passthrough", ""),
                    where=row.get("where", ""),
                    id=row.get("id", ""),
                    status=row.get("status", OPEN),
                )
            )
        return plan

    @classmethod
    def from_jsonl(cls, text: str) -> "Plan":
        """Parse byte-stable JSONL text back into a ``Plan``."""
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        return cls.from_rows(rows)
