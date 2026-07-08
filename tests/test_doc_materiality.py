"""Doc-materiality self-check — makoto's own living docs must be material, not illusory.

makoto holds the agent's words to 誠 (material, not illusory). This holds makoto's OWN living docs
to the same bar: every makoto CLI invocation must resolve, every relative link must exist, no denied
stale-substrate term may appear unannotated, and no dead pattern-ID may be cited as live. Ground
truth is derived at runtime (argparse + load_prechecks) so the check cannot itself go stale.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

import pytest

from makoto.__main__ import build_parser
from makoto.checks._aliases import canonical
from makoto.schema import load_prechecks

REPO = Path(__file__).resolve().parent.parent

# Living docs = those that make CURRENT claims about makoto's behavior or usage. Adding one is a
# deliberate, reviewed act. Provenance/forward-looking trees (docs/archive, docs/certs,
# docs/research) make no current claim and are NOT checked.
LIVING_DOCS = ["README.md", "docs/SPIRIT.md", "docs/MAKOTO-CONVENTIONS.md", "docs/CITATIONS.md"]

# A term that must not be presented as makoto's CURRENT substrate (it migrated to SQLite).
SUBSTRATE_DENYLIST = ["duckdb"]

_ALLOW_RX = re.compile(r"makoto-allow:", re.I)
_CLI_RX = re.compile(r"python -m makoto ([a-z][\w]*(?:\s+[a-z][\w]*)?)")
_LINK_RX = re.compile(r"\]\(([^)]+)\)")
# SPEC-C item 3: matches BOTH the legacy numeric shape (still cited in older doc prose, resolved
# via the alias table below -- an old id is never "dead", it is an alias) and the current
# family.name shape (content./event./gate./makoto.<word>) new docs should use going forward.
_PATID_RX = re.compile(r"(?:pattern|row|patterns)\s+(\d\.\d{1,2}|(?:content|event|gate|makoto)\.\w+)", re.I)


def _cli_command_paths():
    """({top-level names}, {parent: {subcommands}}) from the live argparse parser."""
    parser = build_parser()
    top, sub = set(), {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, subparser in action.choices.items():
                top.add(name)
                kids = set()
                for a2 in subparser._actions:
                    if isinstance(a2, argparse._SubParsersAction):
                        kids |= set(a2.choices)
                if kids:
                    sub[name] = kids
    return top, sub


def _cli_invocation_valid(tokens, top, sub):
    if not tokens or tokens[0] not in top:
        return False
    if tokens[0] in sub:
        return len(tokens) >= 2 and tokens[1] in sub[tokens[0]]
    return True


def _read(doc):
    return (REPO / doc).read_text(encoding="utf-8")


@pytest.mark.parametrize("doc", LIVING_DOCS)
def test_living_doc_cli_resolves(doc):
    top, sub = _cli_command_paths()
    for m in _CLI_RX.finditer(_read(doc)):
        tokens = m.group(1).split()
        assert _cli_invocation_valid(tokens, top, sub), (
            f"{doc}: `python -m makoto {m.group(1)}` is not a real command "
            f"(top={sorted(top)}, sub={sub})"
        )


@pytest.mark.parametrize("doc", LIVING_DOCS)
def test_living_doc_links_resolve(doc):
    base = (REPO / doc).parent
    for m in _LINK_RX.finditer(_read(doc)):
        target = m.group(1)
        if target.startswith(("http://", "https://", "#")):
            continue
        path = target.split("#")[0]
        if not path:
            continue
        assert (base / path).exists(), f"{doc}: relative link does not resolve: {target}"


@pytest.mark.parametrize("doc", LIVING_DOCS)
def test_living_doc_no_stale_substrate(doc):
    for i, line in enumerate(_read(doc).splitlines(), 1):
        low = line.lower()
        for term in SUBSTRATE_DENYLIST:
            if term in low and not _ALLOW_RX.search(line):
                pytest.fail(
                    f"{doc}:{i}: stale-substrate term {term!r} with no makoto-allow: {line.strip()!r}"
                )


@pytest.mark.parametrize("doc", LIVING_DOCS)
def test_living_doc_no_dead_pattern_id(doc):
    live = {p.id for p in load_prechecks()}
    for m in _PATID_RX.finditer(_read(doc)):
        assert canonical(m.group(1)) in live, (
            f"{doc}: cites pattern {m.group(1)} which is not in the live catalog "
            f"(nor a known legacy alias for one)"
        )


def test_assertions_have_teeth():
    """anti-Goodhart: each assertion must FIRE on a planted violation (with a passing control)."""
    top, sub = _cli_command_paths()
    # 1) CLI
    assert not _cli_invocation_valid(["audit"], top, sub)
    assert not _cli_invocation_valid(["pattern", "frobnicate"], top, sub)
    assert _cli_invocation_valid(["status"], top, sub)
    assert _cli_invocation_valid(["pattern", "list"], top, sub)
    # 2) links
    assert not (REPO / "docs" / "does-not-exist-xyz.md").exists()
    assert (REPO / "docs" / "SPIRIT.md").exists()
    # 3) substrate
    bad = "We use DuckDB as the substrate."
    assert any(t in bad.lower() for t in SUBSTRATE_DENYLIST) and not _ALLOW_RX.search(bad)
    ok = "Migrated off DuckDB.  # makoto-allow: historical"
    assert _ALLOW_RX.search(ok)
    # 4) dead pattern id -- "1.12" was never a real id (planted violation); "1.1" is a real,
    # renamed check's LEGACY id (alias-resolves to its current canonical form, proving a doc that
    # still cites the old name is never wrongly flagged as dead).
    live = {p.id for p in load_prechecks()}
    assert canonical(_PATID_RX.search("see pattern 1.12 for details").group(1)) not in live
    assert canonical(_PATID_RX.search("see pattern 1.1 for details").group(1)) in live
