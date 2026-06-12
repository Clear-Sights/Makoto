"""re-export the public surface (PreCheck, Finding) for from-makoto import.

Hook dispatch is bash-driven (install-helpers/*.sh); Python provides only the
schema dataclasses, the citation check (makoto.checks), the audit log query
helpers (makoto.audit), and the install/uninstall/status CLI (makoto.__main__).
"""
from makoto.schema import PreCheck, Finding

__all__ = ["PreCheck", "Finding"]
