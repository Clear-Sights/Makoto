Makoto step 4 narrows rule b to project/subject NAME forms.
Rule b checks paths, URLs, emails and identifiers, including hashes/UUIDs/versions.
Plain or hyphenated words, numbers and unit values do not trigger rule b.
Quoted/backticked content is a name only when its payload has a NAME form.
precision.extract remains general; precision.names supplies the NAME-only view.
The name view does not depend on the bundled common-English word list.
A step's own output target and session-written/edited files are exempt from b.
Output exemptions identify paths; they never create an artifact reading.
Rule a still holds without an independent reading or on unsupported own content.
Earlier session readings count until a recorded write makes their subject stale.
Current-turn successful online fetch/search remains required by rule c.
Tests justified narrow a fixes for output references and independently read quoted names.
Tests justified a c fix for quoted URLs; curly quotes no longer enter URL bytes.
284 whole-suite tests passed in 10.39 seconds (under 15 s); ten NAME forms planted.
Universal 100% and zero false positives remains unestablished; exact limits follow.

Record contract

The sweep is independent of the subject and operates on ordered native tool calls.
No checker invokes a model, executes recorded shell commands, or uses the network.
Literal response field names, string leaves and numeric values are retained. Tool
input may provide an exact name before its result, as required by rule b, but it
cannot create an artifact reading for rule a. The candidate never supplies reading evidence; its writer target is an output exemption.
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
in proposed text. Nested lexical spans remain precision data; b checks only the names() view. Token spelling and
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

Step 3 recorded no forbidden path or external pair corpus reads. No external
network was accessed and no push was made. Git's configured signing helper attempted a local
service request that the sandbox blocked; signing was disabled for the offline
commit. Commits use Clear-Sights on shapes with no attribution trailer.
Step 4 changes and regression evidence

Rule b calls precision.names(text), a view over the general extractor. Its closed
lexical forms cover paths (including filenames, dotfiles and quoted space paths),
URLs, emails, snake_case, camelCase, dotted module names, mixed letter/digit IDs,
hex hashes, UUIDs, versions and versioned package names. Brackets and Markdown
link wrappers do not hide names. Delimited complete names suppress partial names
inside them; quoted prose and numbers are not promoted merely by quotation.
Original text slices and offsets are preserved. The precision extractor still
retains values, units, hyphenated number words, non-dictionary tokens and logs for
DetIO's literal ledger. No DetIO source or store was changed.

Decimals with two numeric components and bare integers remain values. Versions
have three numeric components or an explicit v prefix, with optional prerelease
and build suffixes. Short hashes require both hex letters and digits; all-letter
hex hashes use fixed 32/40/64 widths so ordinary words such as defaced/acceded do
not become names. All-digit strings remain numbers. These are deterministic form
boundaries, not a semantic guarantee for ambiguous short hashes/decimal versions.
Unit spans suppress their component tokens (including ms/kg); an explicit hash,
UUID or version form takes precedence. Plain and hyphenated alphabetic words do
not trigger b, regardless of common-word-list membership.

Native writer effects identify the candidate's output target. Ledger.written
identifies earlier session writes/edits, including imported native records and
observed shell mutations. Canonical identity is used only for output/staleness
tracking; unread names still require exact recorded spelling. Space paths exempt
only token slices contained in a complete known output path with boundaries.
Rejected or host-attested no-effect writes do not add a session-written subject.
Output exemptions are recorded in the snapshot and never pay rule a or rule c.
Other names inside the same write/final remain checked.

Rules a/c changes are limited to false holds demonstrated by the plants. Against
b5c1616, a final out.txt and its backticked form produced both a and b even with a
fresh independent reading, because the writer input itself was own text. Rule a
now exempts output-name references from its literal-copy checks while retaining
its no-original-reading hold and all checks on the contents of own outputs.
The own-file-content plant still holds a/b for an unsupported unread_subject.
A path-only final after its last source reading goes stale still holds a alone.

The quoted-name retry plants also exposed rule a holding `unread_subject` after
an original artifact supplied unread_subject, solely because the earlier denied
attempt had included backticks. A single quoted/backticked name with exact source
bytes now clears that whole-answer-copy check. The general precision-copy check
remains; a repeated own quoted prose phrase still needs independent exact bytes.

The original URL regex captured the closing curly quote in
‘https://example.test/a’, producing an unpayable c subject after fetching the real
URL. Curly delimiters are now excluded from URL spans. Rule c uses lexical NAME
URL/package spans as well as general spans, so quoted URLs consistently require
and clear on the same current-turn fetch. Network success, turn, freshness and
host-classified public-project rules are unchanged. No other a/c semantics changed.

The 121 new plants exercise ten name forms in bare/backtick/straight/curly-quote
spellings, each unread/read; all required exclusion categories; current targets
for all four native writers; session Write/Edit/MultiEdit/NotebookEdit/Bash outputs
in relative/absolute/quoted/prose finals; filenames with spaces; rejected/no-effect
writes; own-file content, stale sources and retries; Markdown paths; hash/version
variants; and the retained own-prose hold. Existing b plants now name subjects
instead of demanding readings for values/prose. Raw log plants check only embedded
names under b while extractor tests retain every complete output line.
The full offline command was python3 -m pytest -q --tb=short: 284 passed in 10.39s.
The live boundary/delivery/pair-driver and lifecycle/mesh tests all remain included.

BORROWED.tsv retains the three exact source pins and records their unchanged roles
in this narrower evaluator; no new borrowed code was introduced. All changes are
inside /home/user/build/makoto on shapes, committed as Clear-Sights, without push
or network. A preliminary filename discovery before reading BRIEF-3 returned
brief path names beneath excluded trees; no case contents from those paths were
opened. All subsequent inspection stayed within the authorized brief/repository.
