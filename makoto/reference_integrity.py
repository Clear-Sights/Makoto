"""Verify that repository-local source citations name files that exist.

This deliberately validates *resolution*, not merely the shape of a citation.
It covers the places where a reader can follow a source claim in this repository:

* local Markdown links and current inline-code source citations;
* relative path values in JSON and TOML manifests; and
* plugin-root paths embedded in hook commands.

Historical filenames in CHANGELOG.md are not citations to a current source: they
describe removals, so they are intentionally outside this verifier's live-doc
scope.  A current document should use a Markdown link for a local source.
"""
from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_MARKDOWN_LINK = re.compile(r"(?<![!])\[[^\]]*\]\(([^)]+)\)")
_INLINE_RELATIVE = re.compile(r"`((?:\./|\.\./)[^`\s#]+)")
_INLINE_REPOSITORY_PATH = re.compile(
    r"`((?:(?:\./|\.\./)?(?:makoto|tests|docs|commands|hooks|\.claude-plugin)/)[^`\s#]+)"
)
_EXCLUDED_PARTS = frozenset({".git", ".venv", "__pycache__", ".pytest_cache"})


@dataclass(frozen=True)
class BrokenReference:
    """A source citation whose local target did not exist at validation time."""

    owner: Path
    reference: str

    def display(self, root: Path) -> str:
        return f"{self.owner.relative_to(root)}: unresolved local reference {self.reference!r}"


def _in_scope(path: Path) -> bool:
    return not any(part in _EXCLUDED_PARTS for part in path.parts)


def _documents(root: Path) -> Iterable[Path]:
    for suffix in ("*.md", "*.json", "*.toml", "*.yml", "*.yaml"):
        yield from (p for p in root.rglob(suffix) if _in_scope(p.relative_to(root)))


def _without_fragment(reference: str) -> str:
    return reference.split("#", 1)[0].split(":", 1)[0]


def _resolves(reference: str, owner: Path, root: Path) -> bool:
    """Resolve a local reference according to its owning document's location."""
    raw = reference.strip().strip("<>")
    if raw.startswith(("http://", "https://", "mailto:", "#")):
        return True
    target = _without_fragment(raw)
    if not target:
        return True
    if target.startswith("${CLAUDE_PLUGIN_ROOT}/"):
        return (root / target.removeprefix("${CLAUDE_PLUGIN_ROOT}/")).exists()
    candidates = [owner.parent / target]
    # Inline source citations conventionally name paths from the repository root (for example
    # ``makoto/_dispatch.py``) even when the prose lives under docs/. Markdown links remain
    # owner-relative first, so ``../README.md`` keeps normal link semantics.
    if target.startswith(("makoto/", "tests/", "docs/", "commands/", "hooks/", ".claude-plugin/")):
        candidates.append(root / target)
    return any(candidate.exists() for candidate in candidates)


def _markdown_references(text: str) -> Iterable[str]:
    for match in _MARKDOWN_LINK.finditer(text):
        yield match.group(1).strip()
    for match in _INLINE_RELATIVE.finditer(text):
        yield match.group(1).strip()
    for match in _INLINE_REPOSITORY_PATH.finditer(text):
        yield match.group(1).strip()


def _json_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _json_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _json_strings(item)


def _json_references(text: str) -> Iterable[str]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return
    for item in _json_strings(value):
        # A source-bearing manifest value is explicitly relative, or uses the
        # plugin root placeholder that the host resolves to this repository.
        if item.startswith(("./", "../", "${CLAUDE_PLUGIN_ROOT}/")):
            yield item


def _toml_references(text: str) -> Iterable[str]:
    """Read conventional path-bearing TOML manifest fields (for example project.readme)."""
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return

    def walk(node: object, key: str = "") -> Iterable[str]:
        if isinstance(node, dict):
            for child_key, child in node.items():
                yield from walk(child, child_key)
        elif isinstance(node, list):
            for child in node:
                yield from walk(child, key)
        elif isinstance(node, str) and key in {"readme", "path", "source", "license-file"}:
            if not node.startswith(("http://", "https://")):
                yield node

    yield from walk(value)


def find_broken_references(root: Path) -> list[BrokenReference]:
    """Return every unresolved current-document or manifest source reference."""
    root = root.resolve()
    broken: list[BrokenReference] = []
    for owner in sorted(_documents(root)):
        text = owner.read_text(encoding="utf-8")
        # Historical filenames in the changelog describe previous layouts, not files a current
        # reader should be able to open. Current Markdown documents use links or repo-rooted
        # inline paths and are resolved below.
        refs = (list(_markdown_references(text))
                if owner.suffix == ".md" and owner.name != "CHANGELOG.md" else [])
        if owner.suffix == ".json":
            refs.extend(_json_references(text))
        if owner.suffix == ".toml":
            refs.extend(_toml_references(text))
        for reference in refs:
            if not _resolves(reference, owner, root):
                broken.append(BrokenReference(owner=owner, reference=reference))
    return broken


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="verify repository-local citations resolve")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    broken = find_broken_references(args.root)
    for finding in broken:
        print(finding.display(args.root.resolve()))
    if broken:
        print(f"reference-integrity: FAIL ({len(broken)} unresolved reference(s))")
        return 1
    print("reference-integrity: PASS (all local references resolve)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
