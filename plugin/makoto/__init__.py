"""makoto package root.

Entry points here (`__init__.py`, `__main__.py`, `dispatch.py`,
`install.py`, `_dispatch_shim.sh`) are referenced directly by every installed
`settings.json` hook, so they cannot move into a domain subpackage without a fresh
`makoto install`. Domain-owned logic lives under `core/`, `substrate/`, `state/`, or
`checks/`.
"""
