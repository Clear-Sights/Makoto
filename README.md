# Makoto 5.0.0

Makoto holds dependent steps before delivery. [DESIGN.md](DESIGN.md) owns the
terms, four checks, purpose hierarchy, ordered stages and exact hook/ledger
interfaces. Write/Edit claims use the same checks as final answers. Creations
and steps asserting nothing need no evidence receipt.

The live hook is `python3 -m makoto2` from `plugin/`;
`plugin/hooks/hooks.json` wires native events into it. Runtime dependencies are
Python 3.11+ standard library only. The checker uses no model or network.

Findings name a lineage, b spec, c other point, or d switch and identify the
missing evidence. The four decision functions are independent. The hook returns
a native PreToolUse denial or final block when findings remain, including on
active Stop retries. Successful finals return `{}`. Admitted dependent tool
calls receive the four questions from `makoto2.hook.FOUR_QUESTIONS` as context.

The locked, hash-linked session journal retains earlier turns. Optional native
`transcript_path` history contributes prior tool-use/result and user-prompt
records. Assistant transcript prose never becomes source evidence. Pending
mutations reserve subjects immediately. Failed mutations remain reserved unless
the host attests `makoto.no_effect`; a reported completion after denial taints
readbacks without supplying evidence.

The outer `makoto` envelope is host-owned instrumentation, never content copied
from `tool_input`. `effects` describes opaque mutations, `reads` describes
observed subjects, `place` supplies coordinates, `aliases` relates explicitly identified copies,
`definitions` records
`subject`/`definition` relationships, and `invocation.subject` or `subjects`
identifies actual execution for opaque runners. `turn_id` supplies host turn
identity. Candidate metadata cannot pay its own claim.

`makoto2.precision` preserves exact lexical slices. `makoto2.claims` owns the
projection of authored content and claim literals; command syntax, writer targets
and replaced text are excluded. Paths use normalized identity to track the
subject, while literal values preserve their spelling. The extractor's common
word list remains available to consumers but does not decide source existence.

`makoto2.switch` recognizes code/config suffixes, notebooks, shebangs and
syntactic declarations. It associates native runs, interpreter operands,
explicit pytest files and configuration consumers with execution subjects.
Indirect or conditional runners need host invocation observations. Configuration
readback is not execution. A failed completed run supplies a response; a
background launch acknowledgment does not. Recorded commands are never executed
by the checker.

`detio_store` or `DETIO_STORE_DIR` identifies a DetIO store. Only references
already witnessed in source bytes are expanded, and their SHA addresses are
verified. `BORROWED.tsv` pins reused DetIO and Causality pieces; packages retain
licenses, notices and provenance.

The host must enforce decisions before executing a tool or delivering a final
answer. `tools/deliver.py` demonstrates final interception by withholding stdout
until Stop is admitted. `tools/run_pairs.py INPUT.json --adapter inferred`
replays events and prints each session's `held` and exact `response`.

Run `bash check.sh` for `python3 -m pytest -q tests`. The built pairs use invented
subjects at Write, Edit, git commit and Stop; their fault twins assert exactly
one rule, and disabling one check must leave the other findings byte-identical.

Form and record presence cannot establish arbitrary semantic dependency.
The requested universal 100% and zero false positives is not claimed.
