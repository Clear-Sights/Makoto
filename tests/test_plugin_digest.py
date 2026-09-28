"""The installed plugin updates only when its version moves, so plugin/ content may not change
under an unchanged version. Measured 2026-09-28: the version read 3.2.0 from #93 to #101, and the
synced copy a session ran stayed on #100-era hooks while main held #101.

docs/PLUGIN-DIGEST.tsv is append-only, one `version<TAB>digest` row per release. The last row must
name the current version and the current content; every version appears once. Change plugin/ and
the digest stops matching; re-pin under the same version and the duplicate reads red."""
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugin"
PIN = REPO / "docs" / "PLUGIN-DIGEST.tsv"


def digest(root=PLUGIN):
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()[:16]


def _rows():
    return [l.split("\t") for l in PIN.read_text().splitlines() if l.strip() and not l.startswith("#")]


def test_the_pinned_digest_is_this_content_under_this_version():
    # discriminant: the last pin row against the live plugin/ bytes and plugin.json version
    version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]
    last_version, last_digest = _rows()[-1]
    assert (last_version, last_digest) == (version, digest()), (
        f"plugin/ is {digest()} at version {version}; the pin's last row is {last_version} {last_digest}. "
        f"Bump the version in plugin.json and pyproject.toml, then append `<new version>\\t{digest()}`")


def test_every_version_is_pinned_once():
    # discriminant: a re-pin under an existing version, the sync would not move
    versions = [v for v, _ in _rows()]
    assert len(versions) == len(set(versions)), f"a version is pinned twice: {versions}"


def test_plant_a_content_change_reads_red(tmp_path):
    # discriminant: one byte appended to a copy of plugin/
    import shutil
    copy = tmp_path / "plugin"
    shutil.copytree(PLUGIN, copy, ignore=shutil.ignore_patterns("__pycache__"))
    before = digest(copy)
    (copy / ".claude-plugin" / "plugin.json").write_text(
        (copy / ".claude-plugin" / "plugin.json").read_text() + " ")
    assert digest(copy) != before
