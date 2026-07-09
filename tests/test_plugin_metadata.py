"""validate .claude-plugin/plugin.json + hooks/hooks.json shape."""
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent

_SEMVER_RX = re.compile(r"^\d+\.\d+\.\d+(?:[-.][\w.]+)?$")


def _pyproject_version() -> str:
    """extract the project version from pyproject.toml without a TOML parser."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "could not find version line in pyproject.toml"
    return m.group(1)


def test_plugin_json_has_required_fields():
    """plugin.json declares name, semver-shaped version matching pyproject, description, license."""
    p = REPO_ROOT / ".claude-plugin" / "plugin.json"
    assert p.is_file(), "missing .claude-plugin/plugin.json"
    data = json.loads(p.read_text())
    assert data["name"] == "makoto"
    plugin_v = data.get("version", "")
    assert _SEMVER_RX.match(plugin_v), f"plugin.json version not semver-shaped: {plugin_v!r}"
    py_v = _pyproject_version()
    assert plugin_v == py_v, (
        f"plugin.json version {plugin_v!r} != pyproject.toml version {py_v!r} — bump both together"
    )
    assert "description" in data and data["description"]
    assert "license" in data


def test_hooks_json_declares_all_three_events():
    """hooks.json registers PreToolUse + PostToolUse + Stop pointing at _dispatch_shim.sh.

    PostToolUse added 1.0.5 to enable history-walking predicates (1.9, 2.5)
    and citation capture (capture.py).
    """
    p = REPO_ROOT / "hooks" / "hooks.json"
    assert p.is_file(), "missing hooks/hooks.json"
    data = json.loads(p.read_text())
    hooks = data["hooks"]
    for evt in ("PreToolUse", "PostToolUse", "Stop"):
        assert evt in hooks, f"missing {evt} in hooks.json"
        for entry in hooks[evt]:
            for h in entry["hooks"]:
                assert h["type"] == "command"
                assert "_dispatch_shim.sh" in h["command"]
                assert "CLAUDE_PLUGIN_ROOT" in h["command"]


def test_dispatch_shim_exists_and_executable():
    """_dispatch_shim.sh exists at repo root, is a POSIX sh script."""
    shim = REPO_ROOT / "_dispatch_shim.sh"
    assert shim.is_file(), "missing _dispatch_shim.sh"
    first_line = shim.read_text().splitlines()[0]
    assert first_line == "#!/bin/sh", f"shim must use #!/bin/sh; got: {first_line!r}"
    assert shim.stat().st_mode & 0o100, "shim must be executable"


def test_dispatch_shim_invokes_makoto_dispatch():
    """shim execs `python -m makoto._dispatch`."""
    shim_text = (REPO_ROOT / "_dispatch_shim.sh").read_text()
    assert "makoto._dispatch" in shim_text
    assert "MAKOTO_PYTHON" in shim_text or "python3" in shim_text


def _exec_commands(md_text: str) -> list[str]:
    """the shell commands a slash command actually RUNS — inline !`cmd` + fenced ```! blocks.

    Prose that merely MENTIONS a flag (e.g. 'set MAKOTO_DISABLE_PATTERNS in your shell')
    is NOT executable and must not trip the read-only guard — only these do.
    """
    cmds = re.findall(r"!`([^`]+)`", md_text)
    cmds += re.findall(r"```!\s*\n(.*?)```", md_text, re.DOTALL)
    return [c.strip() for c in cmds if c.strip()]


def test_slash_commands_are_read_only():
    """Every shipped slash command must be READ-ONLY.

    makoto's adversary is the same agent that can self-invoke a slash command (via the
    Skill tool), so a MUTATING command (install/uninstall, setting a MAKOTO_DISABLE*
    env var, touching settings.json / a _makoto_managed hook) would be a one-call
    self-bypass of the guard. This test fails the build if any command's executable
    body could weaken makoto — enforcing the 'read-only commands only' invariant so a
    future 'status' command can't silently grow a --mute flag.
    """
    cmd_dir = REPO_ROOT / "commands"
    if not cmd_dir.is_dir():
        return  # ships no slash commands -> trivially read-only
    md_files = sorted(cmd_dir.glob("*.md"))
    assert md_files, "commands/ exists but ships no .md commands"

    mutation_rx = re.compile(
        r"makoto\s+(?:install|uninstall)\b"          # lifecycle mutation
        r"|MAKOTO_(?:DISABLE\w*|PAUSE)\s*[:=]"         # set a self-mute env var
        r"|settings(?:\.local)?\.json"                 # touch the wiring file
        r"|_makoto_managed"                            # touch a managed hook entry
        r"|\brm\b|\bsed\b|\btee\b|>\s*\S",             # generic file mutation / redirect
        re.IGNORECASE)
    any_makoto_rx = re.compile(r"\bmakoto\b")
    readonly_makoto_rx = re.compile(r"\bmakoto\s+(?:status|pattern|show)\b")

    for f in md_files:
        text = f.read_text(encoding="utf-8")
        assert re.search(r"^description:\s*\S", text, re.MULTILINE), f"{f.name}: missing description"
        execs = _exec_commands(text)
        assert execs, f"{f.name}: a command should run at least one read-only inspection"
        for cmd in execs:
            m = mutation_rx.search(cmd)
            assert m is None, (
                f"{f.name}: MUTATING exec command {cmd!r} (matched {m.group(0)!r}). "
                f"makoto ships only read-only commands — disable is out-of-band, never in-band."
            )
            if any_makoto_rx.search(cmd):
                assert readonly_makoto_rx.search(cmd), (
                    f"{f.name}: non-read-only makoto call {cmd!r} — only status/pattern/show allowed."
                )


def test_plugin_description_predicate_count_matches_disk():
    """Every count the plugin.json description states must equal the live loader's count.

    makoto holds others' manifests to their word; its own must be true too. This count
    drifted silently once already (a branch wrote '22' before another added a 23rd
    pattern module), so each stated tier count is pinned to the live catalog here —
    bump the description when a check is added or removed.
    """
    from makoto.core.schema import load_prechecks
    from makoto.substrate._loader import load_stopchecks

    desc = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())["description"]
    for phrase_rx, loader, tier in (
        (r"(\d+)\s+pre-checks", load_prechecks, "pre-check"),
        (r"(\d+)\s+Stop gates", load_stopchecks, "Stop gate"),
    ):
        m = re.search(phrase_rx, desc)
        assert m, f"plugin.json description must state the {tier} count ({phrase_rx})"
        claimed, actual = int(m.group(1)), len(loader())
        assert claimed == actual, (
            f"plugin.json claims {claimed} {tier}s but the live loader has {actual} — "
            f"update the description (or the catalog)."
        )
