# 0009: Synced repository resolution

Date: 2026-08-16

## Relocated design history

From `run_stop_checks()`:

```text
# cwd-first, and on a miss resolve against git work-trees this session synced
# (checks/_worldpaths.py) — a file produced remotely over ssh and landed here via
# `git pull` is on disk under a repo root, not under cwd, and a bare-name claim
# ("index.md") false-blocked gate.completion (issue #2). Observation widens; the
# verdict doesn't: every alternate path still ends in a live os.path.exists.
```
