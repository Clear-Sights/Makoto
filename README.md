# Makoto 5.0.0-dev

Makoto holds dependent steps before Write, Edit, MultiEdit, NotebookEdit, Bash
`git commit`/`git push`, and Stop. The live hook is `python3 -m makoto2` from
`plugin/`; `plugin/hooks/hooks.json` wires native events into it. No model or
network is used by the checker.

Rule a requires an original artifact reading. Assistant text, worker answers,
writer acknowledgments, and readings of files this session wrote cannot supply
one. A completed code/query/request response is an artifact reading, including
Bash echo/printf, inline programs, runs of session-written scripts and runs with
mutations. Executing a script reads its response; directly reading an own file
still reads own output. A repeated or derived answer needs an original reading;
its prose need not occur verbatim in that reading.
Rule b requires each NAME span's exact characters in prior tool input or
original response bytes. Names are paths, URLs, emails and identifiers, including
hashes, UUIDs and versions. Plain/hyphenated words, numbers, units and quoted prose
do not trigger b. Current writer targets and session-written/edited file names
are outputs and exempt from b; they never supply an original reading for a. A span copied from a user prompt is given. Paths are
matched in their recorded spelling; normalized paths are used only to track
writes and stale readings. Rule c requires an online fetch/search of a named URL,
versioned package, or host-classified public project in the current turn.
User-given external names still need that online call.

Rule d holds an UNRUN CHANGE when a dependent writer names an edited code/script/
config path, module or identifier, or a commit/push/final ships session edits.
After the last edit, a paired call must execute that subject and return its
output. A failed run counts; an earlier run, file readback, different execution
path, missing output or background launch acknowledgment does not. An actual
stdout/stderr response from a background run counts. Silent completed runs can
return an exit status. Selection is by input form, without behavior word lists.
The hold says: "run it and read the output before this step".

`makoto2.switch` recognizes code/config suffixes, notebooks, shebangs, declarations
and structured JSON payloads. Module stems, declared identifiers and config keys
join normalized file paths as edited subjects' name forms. Simple direct runs,
interpreter script/module operands, explicit pytest files, sourced scripts,
native Run/Execute/NotebookExecute/NotebookRun and `--config` consumers provide
execution subjects. Conditional/compound shell, indirect imports, generated
commands and opaque runners need host-owned `makoto.invocation.subject` or
`subjects` on the paired pre/post tool event, identifying what actually executed.
Interpreter eval/check/help flags do not establish execution of a file named as
an argument; arguments after a script/module operand do not select interpreter
mode. The checker never executes the recorded program itself.

Hold messages name the rule, tag its shape (a lineage, b spec, c other point,
d switch), quote the exact subject, and say which reading or run clears it.
PreToolUse returns a native deny, and Stop returns a native block. Every
unpaid retry remains held, including `stop_hook_active`. Admitted dependent
PreToolUse steps receive Gabriel's exact four questions as `additionalContext`.
An otherwise admitted Stop presents them once as its block reason; a paid
`stop_hook_active` retry produces `{}`. The old lineage surface and four-family
obligation layer have been removed. The questions are:

"Before this step: (1) If it relies on a definition, did you read the thing itself against that definition? (2) If it carries a result to another place or time, did you read the same thing again where and when it lands? (3) If it says how a branch behaves, did you feed that branch an input and read its response? (4) Is it based on the original source, read this turn, rather than on an earlier answer?"

`makoto2.precision.extract` is the single reusable form extractor. It preserves
quoted/backtick/fenced payloads, output/log lines, paths, URLs, emails, digit and
symbol tokens, camelCase, versions, timestamps, IDs, and numbers with units.
Its deterministic non-dictionary substitute is membership in the bundled,
sorted `common-english.txt`: ordinary alphabetic tokens outside that closed list
are exact spans. This is an explicit offline allowlist, not an exhaustive English
dictionary. The extractor returns original string offsets and never rewrites
characters. `extract(text, tool_output=True)` preserves every output line;
visible log/stack syntax is also recognized in proposed text.
`makoto2.precision.names(text)` supplies the narrower NAME view, preserving exact
source slices. Quoted/backticked names keep their payload bytes; quotation alone
does not make a value or phrase a name. Output paths are exempt from b; own file contents still need
an independent artifact reading for a. Quoted URLs use the same current-turn online check.

The locked, hash-linked session journal retains prior turns. An optional native
`transcript_path` adds earlier tool-use/result and user-prompt records. Assistant
prose from the transcript never becomes evidence. A recorded write invalidates
that subject's earlier inputs and readings; pending writes reserve it immediately.
Failed mutations remain reserved unless the host attests `makoto.no_effect`.
Native writer targets, shell redirections and common mutation commands are
tracked. `makoto.effects` supplies subjects changed by opaque commands or tools.
Original readbacks of independent subjects can clear holds; own file readbacks
remain own output. Failed tool errors can be read evidence but cannot pay an
online fetch. A host-reported mutation after a denied call taints subsequent
readbacks without supplying witnesses. Completed native fetch text needs no
explicit exit-status field; reported failures still do not pay c.

The outer `makoto` envelope is host-owned instrumentation, never assistant
content copied out of `tool_input`. `external_subjects` classifies bare public
project names without a subject-specific registry; `network_subjects` records
opaque network clients. `turn_id` provides a stable host turn identity.
`detio_store` or `DETIO_STORE_DIR` identifies a DetIO store. Only references
already witnessed in a successful source response are expanded, and their SHA
addresses are verified. Unreferenced stored objects never become evidence.
`BORROWED.tsv` pins the reused DetIO and Causality pieces. Packages carry their
licenses, notices and provenance table.

The host must enforce hook decisions before executing a tool or delivering a
final answer. `tools/deliver.py` demonstrates this by withholding stdout until a
Stop is admitted; host-specific final interception still depends on that host.
`tools/run_pairs.py INPUT.json --adapter inferred` replays supplied events without
executing recorded commands and prints each session's `held` and exact `response`.
Runtime dependencies are Python 3.11+ standard library only.

Run the whole offline suite with `python3 -m pytest -q`. All test plants are authored
in this repository. The spent development set is used only for diagnosis and
replay grading; its words, paths and names are not added to code or tests. See `REPORT.md` for measured
results and the precise boundary of the record contract. Form and record presence
cannot establish universal semantic dependency or distinguish every bare public
name from a local name without host classification. The requested universal
100% and zero false positives is not claimed.
