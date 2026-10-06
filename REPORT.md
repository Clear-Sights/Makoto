Makoto step 3 now holds dependent steps on three literal session-record checks.
Rule a holds without an original artifact reading or on unsupported own-answer copying.
Rule b holds on an exact form span absent from prior tool input/response or user-given text.
Rule c holds on an external subject lacking a current-turn online fetch/search.
Write/Edit/MultiEdit/NotebookEdit, Bash git commit/push, and Stop are checked before admission.
Every unpaid attempt stays held, including repeated stop_hook_active finals.
Earlier-turn readings count until a recorded write makes their subject stale.
Session-written file readbacks and earlier assistant/worker text remain own output.
plugin/makoto2/precision.py is the single reusable exact-span extractor.
Its documented offline catch-all uses the bundled sorted common-English allowlist.
The lineage surface and four-family obligation layer were subtracted.
DetIO string walking/store verification and Causality traced receipts were reused.
BORROWED.tsv pins each source path and commit; the requested workspace copy also exists.
170 self-authored and retained whole-suite tests passed in 10.01 seconds (under 15 s).
Universal 100% and zero false positives is not established; the exact limits follow.

Record contract

The sweep is independent of the subject and operates on ordered native tool calls.
No checker invokes a model, executes recorded shell commands, or uses the network.
Literal response field names, string leaves and numeric values are retained. Tool
input may provide an exact name before its result, as required by rule b, but it
cannot create an artifact reading for rule a. The candidate never pays itself.
User prompts are given even when an earlier unpaid assistant repeats their text.

Source evidence includes arbitrary native artifact-tool responses, Read/Grep/Glob,
completed shell observations and actual error/log output. It excludes writer
acknowledgments, Agent/Task relays, native echo/inline-program answers and known
session-written executable/file outputs. Partially visible output pays only its
visible bytes. Empty returned file content is a reading; a missing response is not.

Native tool IDs must pair input and response. Mismatched, unpaired, replayed or
background results do not supply evidence. The session journal retains a locked
SHA-256 chain. Corruption or malformed transport holds, using native deny for a
recognizable PreToolUse boundary. Journals are isolated by hashed session identity.

The optional transcript importer supports native hook rows and Claude message
blocks. Only user prompts, assistant tool_use and user tool_result blocks enter
the evidence sweep. Assistant text is never promoted. Journal admissions override
matching imports; identical repeated user prompts still establish distinct turns.
The current candidate is excluded, and other-session transcripts fail closed.

Read freshness applies across turns. Recorded native and shell writes invalidate
all earlier readings/inputs attached to their subject. Canonical path identity is
used for mutation matching only, never as proof of a different precision spelling.
Pending writes invalidate their reservations immediately. A failed write is
potentially effective until host-attested no_effect. Re-reading an own file does
not turn it into an original artifact. An independent artifact may still clear
its supported exact values. Opaque mutations require host effects instrumentation.

Online observations pay rule c only in the current turn and only after settlement.
WebFetch, WebSearch and recognized curl/wget/package/git network invocations count;
failed, pending, explicitly offline or local git observations do not. Exact URLs
and package@version, package==version, package v1.2.3, package version 1.2.3 and
package 1.2.3 forms are checked. A given URL still needs an online observation.
Bare public-project names use host external_subjects, without a name registry.
Opaque network clients use host network_subjects. These are trusted outer event
fields, never assistant-authored tool payload receipts.

Precision contract

The extractor preserves exact source slices for quoted/backtick/fenced payloads,
paths, URLs, emails, digit/symbol tokens, snake_case/camelCase, versions, hashes,
UUIDs, timestamps and numbers with units. Output mode preserves each complete
nonempty tool line. Visible error/stack/log forms become whole exact line spans
in proposed text. Nested lexical spans also remain checked. Token spelling and
internal whitespace are never regenerated or normalized. Sentence punctuation is
separated lexically; URL wrappers are separated from Markdown links.

The deterministic substitute for an unlimited common-English dictionary is a
closed offline allowlist. common-english.txt is a sorted, deduplicated hand-authored
list of familiar words. Alphabetic tokens outside it are precision data. Membership
is case-insensitive; every captured span retains its original case. This rule is
reproducible by sorting/deduplicating the shipped list, does not learn from candidate
text, and requires no external corpus, package or network. It may classify ordinary
words missing from the allowlist as exact spans; it is not a universal dictionary.

Reuse and subtraction

borrowed.leaves and borrowed.get adapt DetIO core.py at
0c7839c4c9e287a2c1f336c0ee95e7e280c5b5b7. The walker also preserves numeric values.
Only a response-witnessed detio:// address or exact objects/address path is opened;
SHA-256 must match the stored bytes. No store directory is swept. A corrupt or
missing witnessed object holds. Independent response subjects retain freshness.

borrowed.receipt copies Causality receipt at
0d76999a2f81e9e00d2fe550ce3d2859dd568d16. Admitted steps carry actual original tool
reading IDs and exact-span witnesses in the durable snapshot. This is a record
trace, not a claim that the assistant's internal causal choice was measured.
Causality history at 44103e9 was inspected: the public product's same receipt
primitive remains available. BORROWED.tsv records all copied pieces; package
artifacts carry the license, third-party license, notice and table.

surface.py and obligations.py are removed. The four-family display, one-time Stop
surface block, explicit semantic obligation contracts, definitions/aliases and
point/version selection are superseded by this brief's three rules. Their old
plants were replaced, rather than falsely reported as retained passing behavior.
Lifecycle/package/audit/current-measurement tests remain, with fresh-account Stop
now correctly blocked for no reading. NOLOSS-MAP.tsv records these decisions and
maps replaced units to their new owners. docs/REPORT.md and docs/NOLOSS-MAP.tsv
mirror the requested root artifacts for existing documentation consumers.

Verification and limits

The suite includes held/clear plants for each rule, all dependent boundaries,
multiple unpaid retries, assistant-only values, own file/executable responses,
user-given copies, raw logs/errors, numeric values, protocol fields, both directions
of path spelling near misses, stale/pending/failed/no-effect mutations, earlier
turns, native/message transcripts, repeated prompts, candidate exclusion,
DetIO valid/short/corrupt/unreferenced objects, and current-turn online near misses.
The live entry and delivery wrapper are exercised; the driver reports each
selected session's held flag and actual response. The whole suite includes the
two resident mesh completion tests and stays below the required 15 seconds.

The requested universal bar is not proven or implied by these plants. Two worlds
can have identical tool records and the name Phoenix, with a local subject in
one and a public project in the other. A form-only checker cannot distinguish
those worlds; trusted external_subjects classification is necessary for bare
names. The same record cannot expose which internal reading an assistant actually
used, so rule a proves absence of original readings and literal own-answer copies,
not arbitrary hidden semantic dependencies. Opaque shell programs may synthesize
output or mutate undeclared subjects; effects/origin/network instrumentation is
needed for those cases. Changes outside the observed session also need host
mutation records. These are remaining requirements for a universal guarantee,
not silent claims of coverage. Native host enforcement before final delivery is
assumed; the executable delivery wrapper validates the boundary it owns.

No forbidden path or external pair corpus was read. No external network was
accessed and no push was made. Git's configured signing helper attempted a local
service request that the sandbox blocked; signing was disabled for the offline
commit. Commits use Clear-Sights on shapes with no attribution trailer.
