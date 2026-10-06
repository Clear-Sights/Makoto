Makoto now emits a deterministic lineage surface from the shared session ledger.
The four groups are LINEAGE, OTHER POINT, SWITCH and SPEC.
PreToolUse emits additionalContext for Write, Edit, MultiEdit and NotebookEdit.
Bash git commit/push emits the same factual surface before admission.
Stop blocks once with the surface; stop_hook_active suppresses surface repetition.
Exact unpaid hard obligations continue to block on active Stop retries.
Empty categories are silent; each category caps entries at four with an omitted count.
The summary has at most nine lines and makes no judgment about prose meaning.
Named subjects and traced values with missing readings are awareness facts.
Hard holds require explicit host contracts or recorded mutation/read order.
Six hard-hold rules are listed below, with the reason each obligation is exact.
The declared adapter and basis grammar are removed; inferred is the sole adapter.
142 self-authored and retained regression tests passed in 3.11 seconds.
The driver prints held and the exact surface emitted at the selected step_index.
No pairs file or forbidden path was read, no recorded command executed, no push made.

Surface contract

LINEAGE reports complete prior readings this turn with subject, tool, selector,
origin and exact point. Exact delimited ledger identities, host-bound aliases, and structural paths/URLs
in the candidate, including unseen relative paths, plus matching trace values,
identify named/value-bearing subjects. Registered definition subjects are known
identities even before their first receipt.
Subjects without a complete reading this turn are reported. A separate line shows
values whose only recorded carriers are assistant/worker relays or session-written
text; an independent original receipt anywhere in the record removes that value
from this line. Native writer replacement bytes are bound only to their native
target; old_string text and Bash transfer arguments do not establish written
value carriers. Equal values establish only recorded overlap, never causation.

OTHER POINT reports subjects with exactly one complete receipt, subjects whose
latest reading sequence precedes their latest recorded mutation, and recorded
mutation destinations or host-required points with no matching complete receipt.
Unrecorded places/times are not invented. Mutation destinations use the destination
reserved at admission, including when settlement omits the destination metadata.

SWITCH reports completed, paired Bash commands this turn with exact tool inputs,
host invocation inputs, pre/completion sequence and exit status, including nonzero
status. Pending/background calls are not described as completed commands. Scripts
are identified by writer targets ending .py/.sh/.js/.rb/.pl, a leading shebang,
or a trusted executable flag on the native writer target; later edits retain
that registered script identity. Unrelated host effects do not inherit its shebang.
The surface reports those with no completed direct invocation after the edit.
Direct executable paths and explicit python/python3/bash/sh/node/ruby/perl script
arguments are structurally bound. Shell wrappers/options, PATH resolution and
arbitrary executable types need host instrumentation; execution is not guessed.
Bare PATH command names never identify an executable in the current directory.
A failed completed invocation counts as a run, without asserting success.

SPEC reports only previously host-registered immutable definitions, with exact
registration fields and one deterministic bound reading receipt ID (or null).
The binding selects the latest complete reading after registration for that
subject, selector and any registered version/point. It does not compare meanings
or assert agreement. With no definitions registered, SPEC is silent.

Each nonempty factual category contributes one line. Entries are sorted,
deduplicated, capped at four and followed by the exact omitted-entry count.
JSON encoding preserves exact text while escaping embedded line breaks. Long
individual inputs/definitions remain exact rather than being silently truncated.
The current candidate's readings/definitions/effects never pay its own check.
The candidate's trusted turn metadata applies before both surface and holds.
Stop is always a dependent boundary, including absent or empty final-message
text; a nonempty ledger surface still emits once, then active retries suppress it.

Hard-hold rules (six)

1. Host LINEAGE/dependency: require the explicitly identified original source,
selector/version/point, complete and current this turn, without a worker producer.
Exact because the trusted host explicitly states the obligation; merely naming
or copying a value does not create it. Written-file read-back defaults to relay.

2. Host OTHER POINT: require distinct prior receipt IDs at the two exact host
points, with the second available and after any specified sequence. Exact because
the host supplies both subject and points; a single observation cannot satisfy
a two-receipt contract. Native inference no longer fabricates a first point.

3. Host SWITCH: require the exact host input digest, subject, selector and paired
completed response, or the explicit command at the same cwd/place context.
Exact because the invocation obligation and response identity are in the record.
An unrelated successful command or background launch cannot satisfy this rule.

4. Host SPEC: require the explicitly named immutable held definition/revision
and its identified subject reading. Exact because host registration and obligation
identify the definition, subject and selector; content agreement is never tested.
A missing requested registration or reading leaves that explicit contract unpaid.

5. Existing recorded writer target: Write/Edit/MultiEdit/NotebookEdit targeting
a subject with a recorded session mutation requires a complete content reading
strictly after the last mutation at its recorded destination. Exact because target,
mutation sequence, destination and read order are all recorded. No filesystem
probe infers whether an unseen target already exists. New targets without a
recorded mutation are not held by this rule. Read-back can be a relay here:
this is a freshness obligation, distinct from original-source provenance.

6. Named mutated subject: a dependent candidate naming an exact recorded subject
with a session mutation has the same destination read-back requirement. Exact
because exact identity, mutation and missing later full reading are in the record.
Aliases are host-bound. Old-turn readings alone, assistant text alone and copied
values alone do not trigger this rule. No free-prose required reading is inferred.

These six rules share the existing four family predicates; native freshness uses
OTHER POINT, without adding another family. Multiple hard findings are retained.
Pending effects invalidate explicit host-contract receipts as before. Malformed
inputs, invalid adapter selection and journal corruption fail closed as transport/
contract failures, separately from the six reading rules. Surface-only Stop blocks
are context delivery, not hard-hold findings; the driver held flag faithfully
includes that actual native block. stop_hook_active admits only a paid retry.

Declared subtraction

Removed declaration(), basis_text(), parse_basis() and the declared adapter option
from runtime/config/CLI. Its added catches were missing/invalid basis syntax and
understated declared value coverage. Those impose a self-declaration contract
that can hold a novel or otherwise adequately recorded step; they do not prove
an exact reading owed by prose. No added catch with zero false holds beyond
inferred plus surface was established. Host contracts remain available directly.
NOLOSS-MAP.tsv records this removal and the replacement of copy/name holds with
factual surface lines. Obsolete declaration-contract tests were subtracted;
applicable ledger, predicate, native transport and lifecycle regressions remain.

Validation and delivery

python3 -m pytest -q tests: 142 passed in 3.11 seconds (entire suite under 15 s).
Own plants cover each of nine surface lines present/absent, all seven requested
boundaries, four host hard contracts present/absent, stale targets and named
mutations present/absent, partial-reading exclusion, script edit/run ordering,
nonzero command inputs/status, deterministic counted caps, definition receipt
binding, destination preservation, relay/source controls and Stop once/retry.
Resume audit plants also cover absent/empty Stop text, unseen relative paths,
PATH versus direct executable paths, replacement-only writer value carriers,
registered unread subjects, exact alias freshness, and native-target shebangs.
Structural git plants now seed readings so they prove surface delivery.
Live subprocess plants, stdout interception, integrity and package regressions
remain. The driver was tested only with self-authored in-memory events.
No external pairs file was run. No universal free-prose accuracy claim is made.

The locked hash-linked append-only journal retains the candidate surface and hard
findings independently. PreToolUse returns the surface as additionalContext even
when denied. Stop/SubagentStop/PreDelivery include it in the blocking reason only
when stop_hook_active is false; paid active retries return no surface. The example
stdout delivery wrapper continues to withhold blocked final bytes. Hosts must
apply the native gate before execution/delivery; production host timing was not
independently tested. Runtime does not execute commands or probe missing sources.

Branch shapes. Two step-2 commits authored as
Clear-Sights <clear-sights@users.noreply.github.com>, without attribution lines.
Canonical outputs: /home/user/build/REPORT.md and /home/user/build/NOLOSS-MAP.tsv.
Identical copies under makoto/docs are committed with implementation and tests.
