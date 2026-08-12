# Branch register

Snapshot: 2026-08-12. Default branch: `main`. The protected
`backup-20260812/*` namespace is an immutable recovery copy and is not working
branch inventory.

## Classification

| Branch | Tip | Class | Action |
|---|---|---|---|
| `main` | `22da88f` | FULLY-MERGED | Retain: default branch |
| `claude/cleanup-makoto` | `22da88f` | FULLY-MERGED | Delete after backup verification |
| `claude/finish` | `1af9e5d` | UNMERGED-VALUABLE | Retain for human review |
| `claude/handoff` | `b65e1c9` | UNMERGED-VALUABLE | Retain for human review |
| `backup-20260812/main` | `22da88f` | BACKUP | Never touch |
| `backup-20260812/claude/cleanup-makoto` | `22da88f` | BACKUP | Never touch |
| `backup-20260812/claude/finish` | `1af9e5d` | BACKUP | Never touch |
| `backup-20260812/claude/handoff` | `b65e1c9` | BACKUP | Never touch |

`main` necessarily passes its own ancestor check; it is retained because it is
the default branch. No branch is UNMERGED-STALE or PROPOSED-DELETE in this
snapshot.

## Unmerged commits a human would miss

`claude/finish` contains tested install-isolation and public-documentation
corrections not present on `main`:

- `15b663bbe80828bce1d3fdef1e6d169fd11c9e95` — Stop two installs from silently sharing one hook and state store
- `045e1cd72c2cada74866ba5ff393b35d935761d5` — Make README inventory claims material
- `1af9e5d8177b69a8b10dfc5592d31318c5491790` — Correct stale public documentation claims

`claude/handoff` contains a point-in-time audit with ranked, reproducible open
findings that are not recorded on `main`:

- `b65e1c9b3105ffa4df99d32c526b8cc6440e4f1d` — docs: add cold-session handoff

## Restore deleted branches

- `claude/cleanup-makoto`: `git fetch origin refs/heads/backup-20260812/claude/cleanup-makoto && git push origin FETCH_HEAD:refs/heads/claude/cleanup-makoto`

## Naming convention

Use `<kind>/<kebab-topic>` with one purpose per short-lived branch. Allowed
kinds are `feat`, `fix`, `docs`, `audit`, and `chore`; for example,
`fix/install-state-collision`. Do not use a tool or person's name as the kind.
Keep `main` deployable, delete merged branches after their backup is verified,
and reserve `backup-YYYYMMDD/*` for immutable recovery refs.
