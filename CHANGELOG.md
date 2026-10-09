# Changelog

## Unreleased

- New `block_in` scope (`MAKOTO_BLOCK_IN`, path-separator list of directories). When set, a hold whose cwd is outside every listed directory is reported in `systemMessage` and does not block; the step is admitted and the finding stays in the journal. Unset: hold everywhere, as before.

## Unreleased

- Rule b: `file.py:12` (a line citation) is evidenced by a read of `file.py`, or by the exact citation in output; an unread file still holds.

## 5.0.4 — 2026-10-09

Fixes for false holds seen live in the Countdown project (2026-10-09). Each has an honest twin that now passes and a fake twin that is still held, in `tests/fixtures/false_holds.json`; `tools/measure_rates.py` prints catch and false-hold rates.

- Rule d: `.tsv`, `.jsonl` and `.ndjson` are data records, so a table such as `method/models.tsv` is never an unrun change.
- Rule d: `rm` and `rmdir` clear recorded edits of the removed file or tree, including staged ones, so a deleted throwaway no longer holds a later commit.
- Rule d: a write to one config-form file (for example `out8.json`) no longer names a sibling data file (`out7.json`) just because both use the same JSON keys. Paths still name it.
- Rule d: Stop and SubagentStop answer only for edits made by the same `agent_id`; commit and push still ship every agent's edits.
- Rule c: text that rides on a tool result (harness reminders) is still given prose but no longer starts a new turn, so a fetch made earlier in the same turn stays current.
- Rule c: `at version 1.1.0` and similar grammar-word-plus-version prose is not a package name.
- Rule b: an id the write itself defines (first table cell, heading or list label) is authored, not a reference; a use of an undefined id still holds.
- Rule b: `codex 0.162.0` is evidenced by `codex-cli 0.162.0` (same version; the name is a whole hyphen part). A different version still holds.

## 5.0.3 — 2026-10-08

- Preserve existing edit and run obligations across renames without inventing edits for moved files or unresolved shell paths.
- Recognize `codex-job.sh start --` script payloads while retaining interpreter check/eval and background-output controls.
- Treat git identity/options and new writer identifiers as introductions; declared unread files still hold.
- Select external subjects from URLs, explicit package syntax and host records; local refs, versions and config keys do not require online reads. A fetched page mentioning another URL does not read that URL.
- Check recorded staged revisions and commit path/tracked-file selection; push checks recorded committed changes. Unrun changes still hold, including combined add/commit calls.
- Treat a missing transcript as empty additional history while preserving the verified journal and its holds. Invalid transcripts and corrupt journals still fail closed.
