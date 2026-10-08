# Changelog

## 5.0.3 — 2026-10-08

- Preserve existing edit and run obligations across renames without inventing edits for moved files or unresolved shell paths.
- Recognize `codex-job.sh start --` script payloads while retaining interpreter check/eval and background-output controls.
- Treat git identity/options and new writer identifiers as introductions; declared unread files still hold.
- Select external subjects from URLs, explicit package syntax and host records; local refs, versions and config keys do not require online reads. A fetched page mentioning another URL does not read that URL.
- Check recorded staged revisions and commit path/tracked-file selection; push checks recorded committed changes. Unrun changes still hold, including combined add/commit calls.
- Treat a missing transcript as empty additional history while preserving the verified journal and its holds. Invalid transcripts and corrupt journals still fail closed.
