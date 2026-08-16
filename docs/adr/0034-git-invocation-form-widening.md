# 0034: `git commit`/`git tag` detection widened to all global-option forms

Date: 2026-05-29

## Relocated design history

From `makoto/checks/fabricatedCommitSha.py`'s `_GIT_COMMIT_OR_TAG_RX`:

```text
WIDENED (content.fabricated_commit_sha revision, 2026-05-29) to close the documented
AI-FP: a truthful commit made through a git worktree / `git -C <dir>` / a cd'd
directory, then a truthful Stop SHA claim, must NOT fire. The original
`\bgit\s+(?:commit|tag)\b` required the subcommand to be IMMEDIATELY after
`git`, so it MISSED `git -C <worktree> commit`, `git -c k=v commit`,
`git --git-dir=.. --work-tree=.. commit`, and `git -C <wt> tag` (verified:
those forms are exactly how a worktree/-C commit is invoked).
```
