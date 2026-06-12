# 誠 — The Spirit and Wholeness of a Word

> 誠 (*makoto*) = 言 (word) + 成 (to complete, to fulfill, to make real). **The word made real.**
>
> This is makoto's constitution — the one principle every pattern is derived from. It also holds
> itself to that principle: where the code does not yet live up to the word, this document says so
> plainly. An empty claim of coverage would be the exact emptiness makoto exists to catch.

---

## 1. The One Principle

**Makoto ensures the agent's words are not empty.**

It does not *audit* a word for realness after the fact — that would make realness contingent, a
property a word might pass or fail on inspection. Makoto makes realness **constitutive**. Water does
not pass a wetness test; *wet is what water is.* In the same way, within makoto a word that is not
real is not a word — the way dry water is not water. Emptiness is refused at the boundary, so what
survives *is* real, by construction.

A word is empty when it is spoken but not **completed (成)**: when it carries no substance, is not
enacted, contradicts the speaker's own record, misstates evidence in plain view, survives in name
while its definition is gutted, or is silenced outright. Makoto's single job is to hold the agent's
own utterances to that standard — kept, whole, and honored in deed.

This is not honesty about the world. *"誠 makoto = 'the spoken word IS reality.' It holds no truth
and judges no external fact (France doesn't exist to it)"*
(`docs/archive/specs/2026-05-31-makoto-bidirectional-falsifiability-design.md:19`). It never
asks "is this claim true of the world?" It asks "is this word kept and whole?" The engine fires
only on *"a verifiable contradiction between the word and the world"* — where "the world" means the
durable, recorded state makoto itself captured — and is inert *"on absence… on a guess"*
(`stopchecks/` + `_dispatch.py:run_stop_checks`).

---

## 2. Why a Real Word Is Legal Tender

Constitutive realness has a consequence, and the consequence is the point: **a makoto-backed word
can be spent like currency.** If realness is a fundamental property of the word — not a hopeful
audit result — then a downstream party can *accept the word at face value without re-deriving it*,
the way you take a banknote without assaying the gold. That is what legal tender is: a medium of
exchange whose backing is guaranteed, so trust does not have to be re-established at every hand-off.
Makoto's economic function is to **mint trust** — to collapse a low-trust agent economy, where every
claim must be re-verified (slow, costly), into a high-trust one, where a kept word is simply spent.

Three properties make the word tender, and each is a design obligation:

- **Un-counterfeitable, or it is worthless.** Tender that can be forged is paper. If makoto can be
  muted, a word is only *contingently* real — real-while-watched — which is no realness at all. So
  non-bypassability is not a feature; it is the mint's seal. The self-mute guard (`pattern_1_23`)
  keeps makoto's own word un-forgeable — as of 2026-06-01 it no longer honors an in-band
  `makoto-allow` on the self-mute path, so the seal cannot be signed by the would-be forger
  (§7.5, closed).
- **Redeemable against a reserve of deeds.** A word is real because it is *cashable* against the
  ledger — the record of what was actually done — not because it sounds sincere. The ledger is the
  reserve that backs the currency.
- **Spendable without re-verification.** A reviewer, a CI gate, a human, or another agent can take a
  makoto-backed *"I ran X and it passed"* and build on it directly. That is the whole payoff.

And this is why **0 false-positives and 0 false-negatives is not pedantry — it is sound money.** A
mint debases its currency two ways: by stamping a real coin counterfeit (a false block — calling a
kept word empty), or by passing a forgery as real (missing an empty word). Makoto's charter forbids
both equally: *"FP and FN are equally forbidden; the resolution is being exceedingly clear, never
timid"* (`docs/archive/specs/2026-05-31-makoto-bidirectional-falsifiability-design.md:47-50`).
Fail-open guarantees it never debases by false rejection; catch-emptiness guarantees it never
inflates with hollow words. Soundness *is* the discipline.

---

## 3. What a Word Is Here

A "word" is **the agent's own utterance**, of two kinds:

- **A claim** — the assistant's end-of-turn text (`last_assistant_message`, read at the Stop hook).
- **A tool-call** — the call the assistant is about to emit (`tool_input`, read at PreToolUse).
  `scan_target_content` reads *"the NEW text a PreToolUse file-mutation introduces"* — the agent's
  own Write/Edit/MultiEdit (`scan_target_content`, `lib/factories.py`).

**Makoto watches its own words, never the user's.** This is the cardinal rule, enforced
structurally and not merely asserted: a user-directed action arrives as a PreToolUse/PostToolUse
event, never as a Stop, so it can never gate a *user* action — structurally: the Stop hook reads only
`last_assistant_message` (the AI's claim) and PreToolUse reads only `tool_input` (the AI's own pending
call), so a user utterance is never on a gated surface (`_dispatch.py:run_stop_checks`). Promise
detection requires a **first-person subject**, so a subagent's or
a user's action is never misread as the AI's promise (`commitments.py:62-67`).

**Keptness, not world-truth — except where the evidence is in front of makoto.** Makoto does not
fact-check the world. But a *surfaced result* is checkable: a number the agent recorded, a file on
disk, a URL a prior tool returned, a citation in the declared set. If you say *"I looked up the
capital of France and the result said X,"* makoto cannot know the capital — but it can read the
result you surfaced. Where the evidence is present, misstating it is an empty word, and makoto may
fire.

---

## 4. The Taxonomy of Emptiness

Six ways a word goes empty, plus one composite. Each has a concrete makoto instance. *(Each detector's
home and exact status is in §6; as of the 2026-06-02 warning-tier elimination every surviving detector
blocks live at error.)*

| Kind | A word goes empty when… | makoto instance |
|---|---|---|
| **INCOMPLETE** | it is spoken with no substance. | *No standalone detector — by design.* A transparently-labeled stub (`# placeholder`) or an empty call empties no word; it is honest about being incomplete. The only emptiness here is a stub **passed off as done** — which is UNFULFILLED (completion gate / §7.1), not a marker-scan. (Former `pattern_1_16`/`1_18` scanned honest labels — removed per §8; the `Bash("")` §7.3 aspiration is dropped for the same reason.) |
| **UNFULFILLED** | it is claimed but not enacted. | "I produced `foo.py`" with no `foo.py` in ledger or on disk (completion gate, `stopchecks/stopcheck_completion.py`); a presented commit-SHA with no `git commit` behind it (`pattern_1_22`). |
| **SELF-CONTRADICTING** | it contradicts your own prior word or record. | "everything is done" over an undischarged commitment you yourself made (advance gate, `stopchecks/stopcheck_advance.py`); a checkbox marked done that says DEFERRED (`pattern_1_5`). |
| **MISREPORTED** | it misstates evidence in front of makoto. | a claimed "tests pass" over a recorded test *failure* (green-claim gate, `stopchecks/stopcheck_green_claim.py`); a citation absent from `CITATIONS.md` (`pattern_1_6`); a WebFetch URL no prior tool returned (`pattern_1_9`). |
| **HOLLOWED** | it survives in name while its definition is gutted. | a loosened comparator (`startswith`/`in [...]`) in an integrity file (`pattern_1_1`); `*_skip`/`*_bypass` flags (`pattern_1_4`); env-gated audit (`pattern_1_2`); `\|\| true` / `2>/dev/null` masking a test runner (`pattern_1_21`). *Loosening a test empties the word "test."* |
| **BYPASSED** | it is silenced or routed around. | `MAKOTO_DISABLE*` or un-wiring the hook in `settings.json` (`pattern_1_23`); abusing `makoto-allow`. (`--no-verify` was removed per §8 — routing around a generic pre-commit hook bypasses a *process*, not a word.) |
| **PURPOSE-CONTRADICTION** | an exemption or self-edit is deployed *to empty another word* — a composite of BYPASSED + exemption-abuse. | a bare `makoto-allow` added in the same `settings.json` edit that sets `MAKOTO_DISABLE`, formerly laundering the bypass past the guard — **closed 2026-06-01** (§7.5): `pattern_1_23` no longer honors `makoto-allow`, and the marker now requires a structured `: <reason>`. |

---

## 5. The Monotonicity Invariant

**Once a word like "test X" has a definition, its meaning may only be PRESERVED or DEEPENED — never
made less meaningful, less complete, skipped, or bypassed.**

A test only has meaning if it has integrity. **A bypassable test was never a test.** A check wired
to always pass is not a relaxed check — it is the *absence* of a check wearing the check's name. You
may strengthen a check, add cases, tighten a comparator; you may not loosen it, env-gate it, mask
its exit code, or mute the watchdog that reads it. The direction of meaning is one-way. This is the
moral core of the HOLLOWED and BYPASSED classes — and the reason a mint never debases its own coin.

*(As of 2026-06-01 this invariant is also named in the shipped `MAKOTO-CONVENTIONS.md`, where
conventions are enforced by habit — §7.8, closed.)*

---

## 6. Every Detector, Derived From the Principle

Each detector keeps one word and prevents one emptiness. As of the **2026-06-02 warning-tier
elimination, every surviving detector blocks live at error.** A detector that could only ever *warn*
— never reach a material zero-FP block — is itself an illusory word, so makoto *cut* those rather
than list them as decoration (§8; the cuts are named at the end of this section). makoto blocks live
on three Stop **gates** — completion, advance, and green-claim — and on the **pattern** catalog:
`1_1`, `1_4`, `1_5`, `1_6`, `1_9`, `1_21`, `1_22`, `1_23`, and the eight-strong **verifier-neutered**
security family `1_26`-`1_33`. *(The live roster has since grown to **eight** Stop gates — the three
above plus `dropped`, `fabricated_action`, `named_test`, `stale_pass`, and `liveness` (function-
internal dead-code, an AST walk over the turn's touched `.py` files rather than a claim-vs-ledger
read); see README. The pattern catalog also now carries live `1_2` (rebuilt as an active-code
env-gated-audit AST detector) and `1_34` (illusory Claude-authorship trailer).)*

| Detector | Word it keeps | Emptiness | Status |
|---|---|---|---|
| `pattern_1_1` | "verifier" / "check" | HOLLOWED (loose comparator) | **COVERED** (error) — but its target is `constitution/integrity/checks/*.py`, a path absent from makoto, so it does **not** guard makoto's own comparators (§7.4). |
| completion gate (`stopchecks/stopcheck_completion.py`) | "I produced X" | UNFULFILLED | **COVERED** (flipped 2026-06-01) — discharge is content-deep: a zero-byte Write of a non-conventional file does NOT discharge the claim (§7.1). |
| `pattern_1_5` | a "done" checkbox | SELF-CONTRADICTING | **COVERED** (error). Scoped to one file. |
| `pattern_1_6` | "citation" | MISREPORTED (phantom authority) | **COVERED** (error). Checks presence-in-declared-set, not correctness. |
| `pattern_1_9` | a "fetch" URL | MISREPORTED (hallucinated URL) | **COVERED** (error). Grounded in session history. |
| `pattern_1_23` | makoto itself | BYPASSED (in-band self-mute) | **COVERED** (error) — un-forgeable: no longer honors `makoto-allow` on the self-mute path (§7.5, closed 2026-06-01). |
| green-claim gate (`stopchecks/stopcheck_green_claim.py`; reads the test-run ledger, `ledger.py`) | "the tests pass" | MISREPORTED (claim vs a recorded test *failure*) | **COVERED** — claim-vs-ledger: blocks "suite green" when the ledger recorded a failing run. |
| advance gate (`stopchecks/stopcheck_advance.py`) | "all done" | SELF-CONTRADICTING (over an open promise) | **COVERED** (flipped live 2026-06-01; 0-FP across all 1335 corpus sessions after the proposal-menu / code-fence sourcing guards, `commitments.py`; unified under `_gates_enabled()`, `_dispatch.py`) — every residual FP traced to a never-built PROPOSAL, not a genuine commitment (§7.6, closed). |
| `pattern_1_4` | a suppression flag (`*_skip`/`*_bypass`) | HOLLOWED | **COVERED** (error; graduated warning→error 2026-06-02, warning-tier-elimination cert). |
| `pattern_1_21` | "test" / "build" / "lint" | HOLLOWED (exit/stderr masking) | **COVERED** (error; graduated 2026-06-02 once the `2>/dev/null` FP source was removed — redirect does not alter exit code). |
| `pattern_1_22` | "committed" / "tagged" | UNFULFILLED (fabricated SHA) | **COVERED** (error; graduated 2026-06-02, corpus-FP=0). |
| `pattern_1_26`-`1_33` (the **verifier-neutered** family) | "verified" / "authenticated" / "secure" | HOLLOWED (a security verifier neutered into an illusory pass) | **COVERED** (error; active-code AST-gated, each controller-verified 0-FP over the 1335-session corpus): TLS `verify=False` (1.26), a hollowed verifier body `return True`/broad-except (1.27), JWT `verify=False` (1.28), `verify_mode=CERT_NONE` (1.29), timing-unsafe `==` of a secret (1.30), JWT `'none'`-alg allow-list (1.31), paramiko `AutoAddPolicy` (1.32), `cert_reqs=CERT_NONE` (1.33). |
| `reconcile` + `subject_binds` (`retraction.py`, `checks.py:42-47`) | a promise's *release* | (keptness firewall) | **COVERED in mechanism** — a commitment clears only by a reason-bound retraction whose result-key *equals* (normalized) the commitment location; a fakeexcuse file cannot stand in. The one genuinely keptness-deep core — and it feeds the advance gate, now live, so a reason-bound retraction is what lets honest re-prioritization clear a promise without a false block. |

**Cut, not held (2026-06-02 warning-tier elimination).** A detector that can only ever *warn* — never
reach a material zero-FP block — is an illusory word, so these were removed rather than kept as
decoration: `claim_check`/`check.quantity` (number-vs-recorded; could not block FP-safely), `pattern_2_6`
(fabricated benchmark), `2_7` (unenumerated completeness), `2_8` (honest-admission — punishing honesty is
perverse), `2_2` (done-over-todos; this env emits no TodoWrite), `2_5` (subagent laundering; structurally
unreachable), and `1_3`/`1_8` (ambiguous-signature audit/status flags; `1_2` was later rebuilt as an
active-code env-gated-audit AST detector and is live again — see the 2026-06-09 addendum at the head
of this section). The over-completion signal
survives **offline only** (formerly the `scope_miner`, since cut with the mining tier — io-purge B4):
it is verifiable against the actual trace, not the text, so
a live text-gate would false-block ~1-in-10 honest turns. **Staged** (built + measured, not wired): the
hidden-retraction gate (corpus-FP measured ≫ 0 — §4 measure-then-wire) and `retire_unsourceable_commitments`.

---

## 7. Where Words Can Still Go Empty — The Honest Gap Ledger

This is makoto's roadmap, stated as **aspiration, not current capability.** Most are places a word
can still go empty today — a denomination not yet fully backed. Settled gaps are marked **✓ CLOSED**
with their commit and reflected in §6's coverage; their numbers are retained as stable identifiers
(referenced by the hardening spec and plans).

1. **✓ CLOSED (2026-06-01) — discharge is now content-deep.** Was: `_discharged` returned true on a
   ledger key OR `os.path.exists`, and the "touched" row stored `value=None`, so *"I implemented
   rate-limiting in auth.py"* was discharged by a **zero-byte Write** of `auth.py` — existence
   verified, not substance. Now: a Write records its stripped length in the ledger (`ledger.py`),
   and `_discharged` (`stopchecks/_common.py`) downgrades a hit when the only thing backing a production claim is
   a zero-byte Write of a non-conventional file (`__init__.py`/`.gitkeep`/etc. still discharge —
   emptiness is their deliverable); unknown/edited/disk-absent fail open. Certed **0 new fires across
   all 1335 corpus sessions** (completion 33→33, advance 0→0); teeth proven by the empty-production
   unit TP + the `run_stop_gates` (now `run_stop_checks`) integration test (`docs/certs/2026-06-01-gap-7.1-content-depth-cert.md`).
   Semantic content-**match** (does `auth.py` carry the claimed *meaning*?) stays out of stdlib reach
   — a named residual (§7 intro), not this gap.
2. **✗ CUT (2026-06-02) — MISREPORTED-by-number could not block FP-safely.** `claim_check` /
   `check.quantity` compared a claimed number to a recorded one, but on the honest corpus it could not
   reach a material zero-FP block (a claimed count rarely contradicts a *recorded* one in a checkable
   way). Under 誠 (material, not illusory) a detector that can only ever warn is an illusory word, so it
   was removed, not held: `stopchecks` exposes no `claim_check` and `run_stop_checks` never calls it
   (warning-tier-elimination cert). The trace-verifiable cousin — claimed-vs-ledger — lives on as the
   **green-claim gate** (§6); a number-vs-ledger gate is a future feature, not a shipped aspiration.
3. **✗ OUT OF SCOPE (§8) — "empty-call" is not a makoto gap.** An empty `Bash("")` or a zero-byte
   Write with *no claim behind it* empties no word — it is an incomplete *action*, not an illusory
   *word*. `bash_nonempty_violation` (`checks.py:110`) stays uncalled by design. The only in-principle
   half — a zero-byte file *discharging a production claim* — is §7.1 (content-depth). (Reclassified
   from aspiration to out-of-scope 2026-06-01 under the single-principle scoping; `pattern_1_16`/`1_18`
   removed with it.)
4. **Makoto does not guard its own comparators.** `pattern_1_1`'s target is
   `constitution/integrity/checks/*.py` (`pattern_1_1.py:13`) — absent from this repo. If the agent
   loosened a comparator inside makoto's own `stopchecks/`/`retraction.py`/`checks.py`, 1.1 would not fire. The
   monotonicity invariant is enforced for a borrowed project's checks, not for makoto's own.
   *Slated for a follow-up plan (against tag `gap-7.6-advance-live`): a **diff-aware** weakening detector —
   old_string carried a strict comparator on a status/verdict, new_string swapped in a loose one. A
   blanket target extension is rejected: the relocated clause-parsing in `stopchecks/`/`retraction.py` and `commitments.py` use
   `re.search`/`re.match`/`in [...]` for legitimate clause parsing, so it would FP on 4 real lines.
   Graduation law: it must reach 0-FP on makoto's own code or ship as a warning.*
5. **✓ CLOSED (2026-06-01) — the anti-bypass word is now un-forgeable.** Was: `makoto_allowed`
   matched a bare `makoto-allow` substring anywhere (then `helpers.py`; the marker regex is now `lexicons.py`) — no reason, no word boundary —
   and `pattern_1_23` honored it *before* checking `MAKOTO_DISABLE`, so a bare marker in the same
   `settings.json` edit laundered a self-mute past the guard. Now: the marker requires a structured
   `makoto-allow: <reason>` (commit 2f1c58d), and `pattern_1_23` no longer honors it at all on the
   self-mute path (commit ffa70ec). Certed **0 corpus FP** on genuine user work. See §6
   (`pattern_1_23`).
6. **✓ CLOSED (2026-06-01) — SELF-CONTRADICTING is now enforced.** Was: the advance gate ran in
   shadow (audit-only), so "done over an open promise" recorded but never blocked. Now: it blocks
   live, unified with the completion gate under one `_gates_enabled()` switch (commit e091398).
   Graduated on the absolute bar — **0-FP across all 1335 corpus sessions** (the lone firing session,
   a 4708-turn plan-audit, went 7→0) with **0-FN** intact (gate-level TP, sourcing recall incl. an
   adversarial near-miss, reason-bound retraction). The decisive finding: every residual FP was a
   **never-built PROPOSAL** the AI recommended ("## What's worth building / Add X", "Option A: …
   produce X", "New Task N.M", a code-fence demo) — never a genuine commitment (each of which
   discharged when its file was touched). So the fix is pure sourcing-precision in `commitments.py`,
   needing **no staleness window** and therefore carrying **no FN risk**. (2.1 remains disabled, 2.2
   dead — those are separate detectors, not this gate.)
7. **Stale-ledger / temporal gap.** `_discharged` checks the ledger before the filesystem, and the
   fs leg can only *add* a discharge, never revoke one — a path touched then deleted still
   discharges. A reverted deed keeps backing its word. *Aspiration: let fs-absence override a stale
   touched row.*
8. **✓ CLOSED — the outward face is whole.** `README.md` opens with the one principle and links this
   constitution, and as of 2026-06-01 the monotonicity invariant (§5) is named in the shipped
   `MAKOTO-CONVENTIONS.md` (commit 4f10450), where conventions are enforced by habit. The 誠 thesis
   now reaches every surface the AI reads.

A word kept here matters more than elsewhere: this ledger is itself a makoto-word. The moment any
line above is fixed, it is marked **✓ CLOSED** with its commit and its coverage reflected in §6 —
leaving a closed gap listed as *open* would make the constitution lie.

---

## 8. The Design Rule for Future Patterns

**For any proposed shape, ask: *what word is being emptied here, and how?***

Name the word. Name the emptiness-kind from §4. If you cannot name the emptied word — if the shape
is a style preference, an efficiency nudge, or a guess about the world — **it is not a makoto
pattern.** (This is why shell/git-hygiene nudges are not integrity patterns: they keep a convention,
not a word.)

**Two independent admission filters — two kinds of cut.** A candidate must pass *both*: it must be
**about the weight of a word** (this section's test — *constitutional*) **and** be **detectable at
zero false-positives** (the corpus-FP ratchet — *tractable*). The filters are orthogonal, and so are
the reasons a pattern is scrapped. A shape cut for **tractability** — no FP-safe signal on the corpus —
is *a word-weight pattern makoto cannot yet catch*; it may **return** the day a cleaner corpus or a
sharper discriminator gives it teeth. A shape cut as **preference** — a convention, a nudge, a taste —
is *not a word at all*; no corpus and no discriminator can ever resurrect it, because there was never
an emptied word to keep. Never conflate the two: *"we couldn't measure it"* and *"it was never ours to
measure"* are different verdicts, and only the first is revisable.

Every pattern must obey makoto's own constants:

- **Fail-open, never timid.** A check is never made inert to dodge work — that would trade away the
  functionality makoto exists for. Block only on what makoto positively knows
  (`stopchecks/`, `_dispatch.py`).
- **The AI's own word only.** A shape that could fire on the user's content violates the cardinal
  rule and is a bug, not a pattern.
- **Monotone.** A new pattern may only preserve or deepen a word's meaning — never ship as a shape
  that, once known, can be cheaply emptied. If it can, it was never a check.
- **Honest about its own teeth.** A pattern that only warns is documented as a warning. To claim a
  warning blocks would be makoto overclaiming its own coverage — the precise emptiness it exists to
  catch, turned inward.
