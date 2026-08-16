# 0050: Synced-repository world resolution for Stop gates

Date: 2026-07-16

## Relocated design history

From `makoto/checks/_worldpaths.py`'s module docstring:

```text
gate.completion verifies a production claim against the results ledger and a cwd-relative
os.path.exists. That observation window has a measured blind spot (FP, 2026-07-16): a file
produced on a REMOTE machine over ssh and landed locally via `git pull` IS on disk — but under
a repo root, not under cwd, and a bare-name claim ("index.md") resolves to <cwd>/index.md and
misses. The claim was true; the world just wasn't looked at where it lives.
```

## Decision

Widen the Stop gates' observation window to include local git work-trees the session actually
synced, rather than only cwd-relative existence — while leaving the verdict rule unchanged.

## Rationale

The originating false positive was a true production claim about a file that had been created on
a remote machine and pulled down locally: it existed on disk, but under a repo root rather than
under cwd, so a bare-name claim resolved to `<cwd>/<name>` and missed. The fix is an observation
fix, not a belief fix — every successful resolution still ends in a live `os.path.exists`, and
the synced-repo route additionally requires the file to be git-tracked, so a claim about a file
that exists nowhere still blocks.

## Alternatives considered

- Walking the filesystem for candidate roots (`os.walk`) — rejected: the Stop hot path forbids
  unbounded filesystem crawls. Candidate roots come instead from a bounded regex over the
  session's own `git -C <dir> pull|fetch` / `cd <dir> && git pull|fetch` Bash events.
- `git ls-remote` to confirm a pushed branch — rejected: network I/O does not belong on the Stop
  hot path. Only bounded local Git metadata reads are used.
- Loosening the suffix-match rule to make bare-name claims resolve more readily — rejected: the
  path-separator-boundary match is the fakeexcuse firewall and must hold.
