"""makoto.substrate.effect -- what a tool call did, read off the tree before and after it.

A register row names an effect: content destroyed, Makoto switched off, a commit crediting a tool
as its author. A check that guesses the effect from the command's spelling covers the spellings it
lists and misses every other one (measured 2026-09-28: 21 escapes on five rows, `find -delete`,
`truncate -s 0`, a Bash `sed -i` of settings.json, `--author`, each the row's own effect in a
spelling the row did not list). Read here, the effect is the same whatever produced it.

At Pre, `snapshot` records the working tree's content (tracked and untracked, ignored files
excluded) through a private index, so every blob is written to the object store: the pre-image is
restorable, which is the undo the D14 row asks to have proven. At Post, `diff` compares it with
the tree after the call. The same pair records the files that decide whether Makoto runs, and
every ref, so a commit the call created is read as an object, not as the command that made it.

BOUNDS, named: content outside the repository the call's cwd sits in is not snapshotted (no
pre-image is readable at hook cost), and a call that deletes the repository's own `.git` takes the
object store with it, so its pre-image is gone even though the loss is still recorded.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

EMPTY_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
_GIT_TIMEOUT_S = 5


def _git(args, cwd, env=None, *, text=True):
    if text:
        return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=_GIT_TIMEOUT_S)
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, timeout=_GIT_TIMEOUT_S)


def guard_paths(cwd) -> list:
    """The settings layers that decide whether Makoto runs, nearest last."""
    home = Path(os.environ.get("HOME") or Path.home())
    here = Path(cwd or ".")
    paths = [Path("/etc/claude-code/managed-settings.json"),
             home / ".claude" / "settings.json", home / ".claude" / "settings.local.json"]
    for d in reversed((here, *here.parents)):
        if d != home:
            paths += [d / ".claude" / "settings.json", d / ".claude" / "settings.local.json"]
    return paths


# Values that leave Makoto as it ships: a switch set to one of these is no switch at all.
_DEFAULT_VALUES = {"", "0", "false", "no", "off", "strict"}


def _truthy(v) -> bool:
    return str(v).strip().lower() not in _DEFAULT_VALUES and v not in (False, None)


def switches(cwd) -> list:
    """Every setting that turns Makoto off or softens it, as `kind:layer:detail` facts, plus one
    `wired:` fact per layer whose hooks run Makoto. Read from the settings files themselves, so
    the reading is the same whether an Edit, `sed -i`, `echo >`, or a script changed them.

    The switches are the harness's and Makoto's own interface, all of it: `disableAllHooks`, an
    `enabledPlugins` entry naming makoto set false, any `MAKOTO_*` variable in a layer's `env`
    moved off its shipped value, and a layer's hook entries that invoke Makoto."""
    out = set()
    for p in guard_paths(cwd):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if _truthy(data.get("disableAllHooks", False)):
            out.add(f"disableAllHooks:{p}")
        for key, on in (data.get("enabledPlugins") or {}).items() if isinstance(
                data.get("enabledPlugins"), dict) else ():
            if "makoto" in str(key).lower() and on is False:
                out.add(f"plugin-off:{p}:{key}")
        for key, value in (data.get("env") or {}).items() if isinstance(data.get("env"), dict) else ():
            if str(key).upper().startswith("MAKOTO_") and _truthy(value):
                out.add(f"env:{p}:{key}={value}")
        if "makoto" in json.dumps(data.get("hooks") or {}).lower():
            out.add(f"wired:{p}")
    return sorted(out)


def snapshot(cwd, index_dir=None) -> dict:
    """The tree at `cwd` as {path: blob}, its tree id, every ref, and Makoto's switches.

    `index_dir` keeps a private index per repository between calls, so each snapshot rehashes only
    what changed since the last one."""
    snap = {"root": None, "tree": None, "files": {}, "refs": [], "switches": switches(cwd)}
    if not cwd or not os.path.isdir(cwd):
        return snap
    top = _git(["rev-parse", "--show-toplevel"], cwd or ".")
    if top.returncode != 0:
        return snap
    root = top.stdout.strip()
    gitdir = _git(["rev-parse", "--absolute-git-dir"], root).stdout.strip()
    keep = None
    if index_dir is not None:
        Path(index_dir).mkdir(parents=True, exist_ok=True)
        keep = Path(index_dir) / (hashlib.sha1(root.encode()).hexdigest()[:16] + ".index")
    with tempfile.TemporaryDirectory() as d:
        idx = os.path.join(d, "index")
        seed = keep if keep is not None and keep.exists() else Path(gitdir) / "index"
        if seed.exists():
            shutil.copyfile(seed, idx)
        env = dict(os.environ, GIT_INDEX_FILE=idx)
        _git(["add", "-A", "--ignore-errors", "--", "."], root, env)
        listing = _git(["ls-files", "-s", "-z"], root, env).stdout
        tree = _git(["write-tree"], root, env).stdout.strip()
        if keep is not None:
            try:
                shutil.copyfile(idx, str(keep) + ".tmp")
                os.replace(str(keep) + ".tmp", keep)
            except OSError:
                pass
    files = {}
    for rec in listing.split("\0"):
        if "\t" in rec:
            meta, path = rec.split("\t", 1)
            files[path] = meta.split()[1]
    refs = set(_git(["for-each-ref", "--format=%(objectname)"], root).stdout.split())
    head = _git(["rev-parse", "--verify", "-q", "HEAD"], root).stdout.strip()
    snap.update(root=root, tree=tree or None, files=files, refs=sorted(refs | ({head} - {""})))
    return snap


def _lines(root, blob) -> set:
    r = _git(["cat-file", "blob", blob], root, text=False)
    if r.returncode != 0:
        return set()
    return {ln.strip() for ln in r.stdout.decode("utf-8", "replace").splitlines() if ln.strip()}


def _destroyed(pre, post) -> list:
    """Paths whose content before the call survives nowhere after it: not at the path, in whole or
    in part, and not at any other path. Moved or copied content survives; an edit keeps lines."""
    if not pre.get("root"):
        return []
    after = post.get("files", {}) if post.get("root") == pre["root"] else {}
    surviving = set(after.values())
    out = []
    for path, blob in pre["files"].items():
        if blob == EMPTY_BLOB or after.get(path) == blob or blob in surviving:
            continue
        now = after.get(path)
        if now is None or now == EMPTY_BLOB:
            out.append(path)
            continue
        before = _lines(pre["root"], blob)
        if before and not (before & _lines(pre["root"], now)):
            out.append(path)
    return sorted(out)


def _new_commits(pre, post) -> list:
    root = post.get("root")
    if not root:
        return []
    r = _git(["rev-list", "--all", "--not", *pre.get("refs", [])], root)
    out = []
    for sha in r.stdout.split()[:50]:
        c = _git(["show", "-s", "--format=%an <%ae>%x00%cn <%ce>%x00%B", sha], root)
        if c.returncode == 0:
            author, committer, message = (c.stdout.split("\0") + ["", "", ""])[:3]
            out.append({"sha": sha, "author": author, "committer": committer, "message": message})
    return out


def _muted(pre, post) -> list:
    before, after = set(pre.get("switches", [])), set(post.get("switches", []))
    return sorted([f for f in after - before if not f.startswith("wired:")]
                  + ["unwired:" + f[len("wired:"):] for f in before - after if f.startswith("wired:")])


_WRITTEN_FILES, _WRITTEN_LINES = 50, 200


def _written(pre, post) -> dict:
    """Lines each changed path gained: what the call wrote, however it wrote it."""
    root = post.get("root")
    if not root or root != pre.get("root"):
        return {}
    before = pre.get("files", {})
    out = {}
    for path, blob in sorted(post.get("files", {}).items()):
        if before.get(path) == blob or blob == EMPTY_BLOB:
            continue
        r = _git(["cat-file", "blob", blob], root, text=False)
        if r.returncode != 0 or b"\0" in r.stdout[:8000]:
            continue
        old = _lines(root, before[path]) if path in before else set()
        added = [ln for ln in r.stdout.decode("utf-8", "replace").splitlines()
                 if ln.strip() and ln.strip() not in old]
        if added:
            out[path] = added[:_WRITTEN_LINES]
        if len(out) >= _WRITTEN_FILES:
            break
    return out


def diff(pre, post) -> dict:
    return {"root": pre.get("root"), "tree": pre.get("tree"), "destroyed": _destroyed(pre, post),
            "muted": _muted(pre, post), "switches_before": pre.get("switches", []),
            "commits": _new_commits(pre, post), "written": _written(pre, post)}


def _slot(state_dir, key) -> Path:
    return Path(state_dir) / "effect" / (hashlib.sha1(str(key).encode()).hexdigest()[:20] + ".json")


def record_pre(state_dir, payload) -> None:
    key = payload.get("tool_use_id")
    if not key:
        return
    snap = snapshot(payload.get("cwd"), Path(state_dir) / "effect" / "index")
    snap["t"] = time.time()
    p = _slot(state_dir, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap), encoding="utf-8")


def read_post(state_dir, payload):
    """The call's effect, or None when its Pre snapshot is missing (no pre-image, nothing to say)."""
    key = payload.get("tool_use_id")
    if not key:
        return None
    p = _slot(state_dir, key)
    try:
        pre = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    # the repository the call started in, even when the call moved its own cwd or removed it
    post = snapshot(pre.get("root") or payload.get("cwd"), Path(state_dir) / "effect" / "index")
    try:
        p.unlink()
    except OSError:
        pass
    out = diff(pre, post)
    if isinstance(pre.get("t"), (int, float)):
        out["elapsed_ms"] = int((time.time() - pre["t"]) * 1000)
    return out


def of(ev) -> dict:
    """The recorded effect on a settled event, or {} when none was recorded."""
    eff = ev.get("makoto_effect") if isinstance(ev, dict) else None
    return eff if isinstance(eff, dict) else {}
