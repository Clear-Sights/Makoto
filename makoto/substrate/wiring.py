"""makoto.substrate.wiring -- hook-wiring introspection, the shared L0 home.

ONE domain: does a settings.json hook entry functionally reach makoto's dispatch? Consumed by
BOTH sides of the wiring contract -- install.py (the writer/status reporter) and
checks/selfWiredCheck.py (the self-defense gate that detects partial stripping). Hoisted here
2026-07-09 from the byte-for-byte duplicate both files carried: selfWiredCheck's own module
note asked for exactly this ("a future refactor that hoists both to a shared L0 module would
let this duplication go away") -- the gate-side layering firewall
(tests/test_gate_shape.py, ALLOWED_IMPORT_ROOTS) forbids a gate importing install.py's
lifecycle machinery, but an L0 primitive module is precisely what the firewall allowlists.
Stdlib-only, no makoto-internal imports: safe for anything to depend on.
"""
from __future__ import annotations

# The managed-entry marker `makoto install` writes into settings.json hook entries.
MAKOTO_CLAUDE_FLAG = "_makoto_managed"


def entry_dispatches_to_makoto(entry) -> bool:
    """True iff ONE hook entry functionally reaches makoto's dispatch -- the managed-flag entry
    `makoto install` writes, OR a flag-less hand-wired/shim entry whose command names makoto
    (`.../makoto_state/dispatch.sh`, `python -m makoto._dispatch`). Keying on the flag alone
    lies on a shim-wired device (status: hooks_wired=false while firing, fixed v1.2.1;
    install: a duplicate entry double-dispatching every event, the same bug on the write side)."""
    if not isinstance(entry, dict):
        return False
    if entry.get(MAKOTO_CLAUDE_FLAG):
        return True
    return any(isinstance(inner, dict) and "makoto" in str(inner.get("command", "")).lower()
               for inner in entry.get("hooks", []))
