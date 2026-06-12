"""StopCheck + GateContext schemas for the gates package (separate module: no import cycle)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional, Sequence
from makoto.schema import Finding


@dataclass(frozen=True)
class GateContext:
    """The Stop-event substrate, assembled ONCE per event and shared by every gate."""
    text: str
    touched: frozenset
    empty: frozenset
    opens: Sequence
    testrun_output: str
    cwd: str
    fs_exists: Callable
    fs_size: Callable
    fs_read: Callable
    history: Sequence = ()     # the events-table rows _select_recent returns (faithful: full
    #                            command + full tool_response per prior tool event). Fabrication
    #                            gates walk this like predicate 1.9; default () keeps it optional.

    @property
    def roots(self):
        return [self.cwd]


@dataclass(frozen=True)
class StopCheck:
    """A live Stop gate. NO `blocking` field: discovered <=> live <=> blocking (no shadow tier)."""
    id: str
    fn: Callable
    run: Callable  # GateContext -> Optional[Finding] | list[Finding] (gate.liveness yields a list;
    #                run_stop_checks normalizes a list/tuple, a single Finding, and None alike)
