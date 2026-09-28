#!/usr/bin/env python3
"""Which installed Makoto copy's hooks run this session, and which copies are leftovers.

usage: python3 tools/makoto_copies.py [HOME]
prints one tab-separated line per installed copy:  live|unused <TAB> path <TAB> version <TAB> why

Two ways a copy loads (read from the files Claude Code itself reads, nothing guessed):
- account sync: ~/.claude/plugins/synced/<org>/manifest.json lists `makoto` with a generation N;
  the copy that loads is `makoto~gN` (plain `makoto` when no generation). Other generations are
  leftovers.
- marketplace install: ~/.claude/settings.json enabledPlugins["makoto@<marketplace>"] is true;
  the copy that loads is the installPath ~/.claude/plugins/installed_plugins.json records for that
  key (the newest version directory when there is no record). Other version directories, and every
  copy of a marketplace not enabled, are leftovers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _version(copy: Path) -> str:
    data = _json(copy / ".claude-plugin" / "plugin.json")
    return str(data.get("version", "?")) if isinstance(data, dict) else "?"


def _vkey(name: str):
    return tuple(int(p) if p.isdigit() else -1 for p in name.split("."))


def copies(home: Path) -> list[tuple[str, Path, str, str]]:
    out = []
    plugins = home / ".claude" / "plugins"
    for org in sorted(p for p in (plugins / "synced").glob("*") if p.is_dir()):
        found = sorted(p for p in org.glob("makoto*") if (p / ".claude-plugin" / "plugin.json").is_file())
        if not found:
            continue
        manifest = _json(org / "manifest.json") or {}
        entry = next((e for e in manifest.get("plugins", []) if isinstance(e, dict) and e.get("name") == "makoto"), None)
        gen = entry.get("generation") if entry else None
        loads = None if entry is None else org / (f"makoto~g{gen}" if gen else "makoto")
        for c in found:
            if c == loads:
                out.append(("live", c, _version(c), "account sync: the manifest lists this generation"))
            else:
                why = "account sync: an older generation" if entry else "account sync: the manifest does not list makoto"
                out.append(("unused", c, _version(c), why))
    settings = _json(home / ".claude" / "settings.json") or {}
    enabled = settings.get("enabledPlugins") or {}
    installed = (_json(plugins / "installed_plugins.json") or {}).get("plugins") or {}
    for mkt in sorted(p for p in (plugins / "cache").glob("*") if (p / "makoto").is_dir()):
        key = f"makoto@{mkt.name}"
        found = sorted((p for p in (mkt / "makoto").glob("*") if (p / ".claude-plugin" / "plugin.json").is_file()),
                       key=lambda p: _vkey(p.name))
        if not found:
            continue
        rec = installed.get(key)
        rec = rec[0] if isinstance(rec, list) and rec else rec
        loads = None
        if enabled.get(key) is True:
            path = rec.get("installPath") if isinstance(rec, dict) else None
            loads = Path(path) if path else found[-1]
        for c in found:
            if loads is not None and c.resolve() == loads.resolve():
                out.append(("live", c, _version(c), f"marketplace install: enabledPlugins {key} is on"))
            else:
                why = f"marketplace install: an older version of {key}" if loads is not None \
                    else f"marketplace install: enabledPlugins {key} is not on"
                out.append(("unused", c, _version(c), why))
    return out


if __name__ == "__main__":
    home = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home()
    for state, path, ver, why in copies(home):
        print(f"{state}\t{path}\t{ver}\t{why}")
