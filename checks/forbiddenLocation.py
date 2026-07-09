"""makoto.checks.forbiddenLocation -- blocking PreToolUse check: a Write/Edit/MultiEdit/
NotebookEdit whose target lexically escapes cwd, hits a protected system/credential directory,
is a shell-rc file, (Write/MultiEdit only) is a credential basename, or hits MAKOTO'S OWN
control-plane -- ported by SHAPE (rule 5 -- copy, never import) from
`assay/assay/patterns/forbidden_location.py`, re-homed onto Makoto's predicate contract and
Makoto's own self-guard segments (SPEC-5 Task 5).

Pure `PurePosixPath` lexical membership test -- NO disk access, NO content read (grounding:
`assay/assay/patterns/forbidden_location.py`'s own module docstring makes the same claim; this
port preserves it verbatim). Membership is EXACT segment/basename equality, never substring
(`'etc'` must not match `'etcetera.md'`).

SELF-GUARD, re-homed onto MAKOTO's wiring (not Assay's): the same `.claude/settings.json` /
`.claude/settings.local.json` control-plane files now wire MAKOTO's hooks, so they are protected
here under Makoto's own name. Makoto has NO static project-level `.makoto` directory analogous to
Assay's `.assay` (verified against `makoto/state.py` -- Makoto's state lives at
`$MAKOTO_STATE_DIR`, default `$HOME/.claude/makoto_state/`, no leading-dot segment convention), so
this port drops the static-segment family Assay had for its own directory and keeps only the
DYNAMIC resolved-state-home family (`_under_makoto_state_home`, reading `makoto.record.state._state_dir()`
-- the SAME resolver the rest of Makoto's state layer reads/writes through, so this self-guard can
never diverge from where Makoto's own state actually lives).

Reuses `makoto.substrate._primitives.normalize_path` (already the flat package's own path-equality
primitive, functionally identical to Assay's `kernel.identity.normalize_path`) rather than porting
a duplicate `_pathident.py` module -- a deliberate simplification over the plan's literal file list
(no behavior difference, one fewer near-duplicate file in a 60-file flat folder).
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Optional

from makoto.substrate._loader import Check
from makoto.substrate._primitives import normalize_path
from makoto.core.schema import Finding, PreCheck
from makoto.record.state import _state_dir

# Protected system / credential DIRECTORY segments (EXACT segment membership, never substring).
_PROTECTED_DIR_SEGMENTS = frozenset({
    "etc", "boot", "sys", "proc", "dev",
    ".ssh", ".gnupg", ".aws", ".config", ".kube", ".docker",
})
_SHELL_RC_BASENAMES = frozenset({
    ".bashrc", ".bash_profile", ".bash_login", ".profile",
    ".zshrc", ".zprofile", ".zshenv", ".zlogin",
    ".cshrc", ".tcshrc", ".kshrc", ".login",
})
_CREDENTIAL_BASENAMES = frozenset({
    ".netrc", ".pgpass", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "credentials", ".npmrc", ".pypirc", ".git-credentials", "authorized_keys",
})
# MAKOTO's own control-plane FILES (SELF-GUARD): EXACT (parent-segment, basename) pairs -- never a
# bare basename match, so an unrelated project's own settings.json is not makoto's.
_MAKOTO_CONTROL_PLANE_FILES = frozenset({
    (".claude", "settings.json"),
    (".claude", "settings.local.json"),
})
_WRITE_NAMES = frozenset({"Write", "MultiEdit"})
_EDIT_NAMES = frozenset({"Edit", "NotebookEdit"})
_LOCATION_KEYS = ("file_path", "notebook_path")


def _lexical_resolve(path: str) -> PurePosixPath:
    """Collapse '.'/'..' lexically over a path's parts ('..' at the root is clamped) -- no disk
    access. Ported verbatim (by shape) from Assay's own `_lexical_resolve`."""
    p = PurePosixPath(path)
    anchor = p.anchor
    is_absolute = bool(anchor)
    resolved: list[str] = []
    parts = p.parts[1:] if is_absolute else p.parts
    for part in parts:
        if part in (".", ""):
            continue
        if part == "..":
            if resolved and resolved[-1] != "..":
                resolved.pop()
            elif not is_absolute:
                resolved.append("..")
            continue
        resolved.append(part)
    if is_absolute:
        return PurePosixPath(anchor, *resolved)
    if not resolved:
        return PurePosixPath(".")
    return PurePosixPath(*resolved)


def _resolves_outside_cwd(file_path: str, cwd: str) -> Optional[bool]:
    """True if `file_path` lexically resolves outside `cwd`, False if under/equal, None if
    undecidable (a relative path with no cwd is never guessed)."""
    fp = PurePosixPath(file_path)
    if not fp.is_absolute():
        if not cwd:
            return None
        base = PurePosixPath(cwd)
        if not base.is_absolute():
            return None
        target = _lexical_resolve(str(base / fp))
        root = _lexical_resolve(cwd)
    else:
        target = _lexical_resolve(file_path)
        if not cwd:
            return None
        root = _lexical_resolve(cwd)
    if normalize_path(str(target)) == normalize_path(str(root)):
        return False
    root_parts, target_parts = root.parts, target.parts
    if len(target_parts) < len(root_parts):
        return True
    if target_parts[: len(root_parts)] == root_parts:
        return False
    return True


def _under_makoto_state_home(target: PurePosixPath) -> bool:
    """True iff `target` lies at/under Makoto's own RESOLVED state-home
    (`makoto.record.state._state_dir()` -- the same resolver the rest of the state layer uses), via exact
    segment-prefix membership. Covers an operator-relocated `$MAKOTO_STATE_DIR`, not just the
    default path."""
    root = _lexical_resolve(str(_state_dir()))
    if not root.is_absolute():
        return False
    root_parts, target_parts = root.parts, target.parts
    if len(target_parts) < len(root_parts):
        return False
    return target_parts[: len(root_parts)] == root_parts


def _under_harness_plans(target: PurePosixPath) -> bool:
    """True iff `target` lies at/under the host harness's own designated plan-artifact home,
    `<home>/.claude/plans` — the one out-of-cwd location the harness itself instructs an agent to
    write to (plan mode names exactly this path as the only permitted file). Resolved dynamically
    via `Path.home()` (the same home the installer wires), never a hardcoded user path — the same
    dynamic-resolver discipline as `_under_makoto_state_home`. Deliberately consulted in
    `_location_reason` ONLY between the self-guard family (control-plane pair, state-home) and the
    root-escape fallback: nothing under `.claude/plans` can shadow `settings.json` or
    `makoto_state`, which are matched and returned before this is ever reached. Live FP this
    closes: root-escape fired three times on the harness's own plan file, 2026-07-07."""
    root = _lexical_resolve(str(PurePosixPath(Path.home().as_posix()) / ".claude" / "plans"))
    if not root.is_absolute():
        return False
    root_parts, target_parts = root.parts, target.parts
    if len(target_parts) < len(root_parts):
        return False
    return target_parts[: len(root_parts)] == root_parts


def _location_reason(name: str, file_path: str, cwd: str) -> Optional[str]:
    fp = PurePosixPath(file_path)
    if fp.is_absolute():
        target = _lexical_resolve(file_path)
    elif cwd and PurePosixPath(cwd).is_absolute():
        target = _lexical_resolve(str(PurePosixPath(cwd) / fp))
    else:
        target = _lexical_resolve(file_path)

    segments = target.parts
    basename = target.name
    is_write = name in _WRITE_NAMES

    for seg in segments:
        if seg.lower() in _PROTECTED_DIR_SEGMENTS:
            return f"protected-directory: target lies under protected segment {seg!r}"

    if basename in _SHELL_RC_BASENAMES:
        return f"shell-rc: target basename {basename!r} is a shell startup file"

    if is_write and basename.lower() in _CREDENTIAL_BASENAMES:
        return f"credential-basename: {name} to credential file {basename!r}"

    candidate = (segments[-2].lower(), basename.lower()) if len(segments) >= 2 else None
    if candidate is not None and candidate in _MAKOTO_CONTROL_PLANE_FILES:
        return f"makoto-control-plane: target is makoto's own hook configuration {basename!r}"

    if _under_makoto_state_home(target):
        return "makoto-state-home: target lies under makoto's resolved state directory"

    if _under_harness_plans(target):
        return None                     # harness-designated plan home -- sanctioned, not an escape

    outside = _resolves_outside_cwd(file_path, cwd)
    if outside is True:
        return "root-escape: target resolves outside the working directory"

    return None


def _location_arg(tool_input: dict) -> Optional[str]:
    for key in _LOCATION_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def predicate(*, current_event: dict, history: list, pattern: PreCheck,
              conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    name = current_event.get("tool_name", "")
    if name not in _WRITE_NAMES and name not in _EDIT_NAMES:
        return None
    ti = current_event.get("tool_input", {}) or {}
    file_path = _location_arg(ti)
    if file_path is None:
        return None
    cwd = current_event.get("cwd", "")
    if not isinstance(cwd, str):
        cwd = ""
    reason = _location_reason(name, file_path, cwd)
    if reason is None:
        return None
    return Finding(
        pattern_id=pattern.id,
        file=file_path,
        line=0,
        level=pattern.fire_level,
        message=f"forbidden location -- {reason}",
        retry_hint=pattern.retry_hint,
    )


RETRY_HINT = "Do not write outside the working directory or into a protected system/credential location. If you need to touch makoto's own wiring (.claude/settings.json) or its state directory, that is out-of-band operator action, not an in-session edit."
DESCRIPTION = "Write/Edit/MultiEdit/NotebookEdit target escapes cwd, hits a protected system/credential dir, a shell-rc file, a credential basename, or makoto's own control-plane/state-home"

CHECK = Check(id="event.forbidden_location", applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('Write', 'Edit', 'MultiEdit', 'NotebookEdit'), retry_hint=RETRY_HINT, description=DESCRIPTION)
