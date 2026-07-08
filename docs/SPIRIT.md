# 誠, The Spirit and Wholeness of a Word

> 誠 (*makoto*) = 言 (word) + 成 (to complete, to fulfill, to make real). **The word made real.**
>
> This is makoto's constitution, the one principle every pattern is derived from. It also holds
> itself to that principle: where the code does not yet live up to the word, this document says so
> plainly. An empty claim of coverage would be the exact emptiness makoto exists to catch. (The
> live, current catalog of every check lives in README.md's "What it catches" section; this
> document states the principle those checks are derived from, not a second copy of the roster.)

---

## 1. The One Principle

**Makoto ensures the agent's words are not empty.**

It does not *audit* a word for realness after the fact; that would make realness contingent, a
property a word might pass or fail on inspection. Makoto makes realness **constitutive**. Water does
not pass a wetness test; *wet is what water is.* In the same way, within makoto a word that is not
real is not a word, the way dry water is not water. Emptiness is refused at the boundary, so what
survives *is* real, by construction.

A word is empty when it is spoken but not **completed (成)**: when it carries no substance, is not
enacted, contradicts the speaker's own record, misstates evidence in plain view, survives in name
while its definition is gutted, or is silenced outright. Makoto's single job is to hold the agent's
own utterances to that standard: kept, whole, and honored in deed.

This is not honesty about the world. 誠 makoto means "the spoken word IS reality." It holds no truth
and judges no external fact (France doesn't exist to it). It never
asks "is this claim true of the world?" It asks "is this word kept and whole?" The engine fires
only on a verifiable contradiction between the word and the world, where "the world" means the
durable, recorded state makoto itself captured, and is inert on absence, on a guess.

---

## 2. Why a Real Word Is Legal Tender

Constitutive realness has a consequence, and the consequence is the point: **a makoto-backed word
can be spent like currency.** If realness is a fundamental property of the word, not a hopeful
audit result, then a downstream party can *accept the word at face value without re-deriving it*,
the way you take a banknote without assaying the gold. That is what legal tender is: a medium of
exchange whose backing is guaranteed, so trust does not have to be re-established at every hand-off.
Makoto's economic function is to **mint trust**, to collapse a low-trust agent economy, where every
claim must be re-verified (slow, costly), into a high-trust one, where a kept word is simply spent.

Three properties make the word tender, and each is a design obligation:

- **Un-counterfeitable, or it is worthless.** Tender that can be forged is paper. If makoto can be
  muted, a word is only *contingently* real, real-while-watched, which is no realness at all. So
  non-bypassability is not a feature; it is the mint's seal. The self-mute guard
  (`content.self_mute_guard`) keeps makoto's own word un-forgeable: it does not honor an in-band
  `makoto-allow` on the self-mute path, so the seal cannot be signed by the would-be forger.
- **Redeemable against a reserve of deeds.** A word is real because it is *cashable* against the
  ledger, the record of what was actually done, not because it sounds sincere. The ledger is the
  reserve that backs the currency.
- **Spendable without re-verification.** A reviewer, a CI gate, a human, or another agent can take a
  makoto-backed *"I ran X and it passed"* and build on it directly. That is the whole payoff.

And this is why **0 false positives and 0 false negatives is not pedantry, it is sound money.** A
mint debases its currency two ways: by stamping a real coin counterfeit (a false block, calling a
kept word empty), or by passing a forgery as real (missing an empty word). Makoto's charter forbids
both equally, and resolves the tension by being exceedingly clear, never timid.
Fail-open guarantees it never debases by false rejection; catch-emptiness guarantees it never
inflates with hollow words. Soundness *is* the discipline.

---

## 3. What a Word Is Here

A "word" is **the agent's own utterance**, of two kinds:

- **A claim**: the assistant's end-of-turn text, read at the Stop hook.
- **A tool call**: the call the assistant is about to emit, read at PreToolUse; a content-scan
  reads the NEW text a PreToolUse file-mutation introduces, the agent's own Write/Edit/MultiEdit.

**Makoto watches its own words, never the user's.** This is the cardinal rule, enforced
structurally and not merely asserted: a user-directed action arrives as a PreToolUse/PostToolUse
event, never as a Stop, so it can never gate a *user* action. The Stop hook reads only the
assistant's own closing text (the AI's claim) and PreToolUse reads only the tool's own input (the
AI's own pending call), so a user utterance is never on a gated surface. Promise
detection requires a **first-person subject**, so a subagent's or a user's action is never
misread as the AI's promise.

**Keptness, not world-truth, except where the evidence is in front of makoto.** Makoto does not
fact-check the world. But a *surfaced result* is checkable: a number the agent recorded, a file on
disk, a URL a prior tool returned, a citation in the declared set. If you say *"I looked up the
capital of France and the result said X,"* makoto cannot know the capital, but it can read the
result you surfaced. Where the evidence is present, misstating it is an empty word, and makoto may
fire.

---

## 4. The Taxonomy of Emptiness

Six ways a word goes empty, plus one composite:

| Kind | A word goes empty when… |
|---|---|
| **INCOMPLETE** | it is spoken with no substance. A transparently-labeled stub or an empty call empties no word; it is honest about being incomplete. The only emptiness here is a stub **passed off as done**, which is UNFULFILLED, not a marker-scan. |
| **UNFULFILLED** | it is claimed but not enacted: "I produced `foo.py`" with no `foo.py` in the ledger or on disk; a presented commit SHA with no `git commit` behind it. |
| **SELF-CONTRADICTING** | it contradicts your own prior word or record: "everything is done" over an undischarged commitment you yourself made; a checkbox marked done that says DEFERRED. |
| **MISREPORTED** | it misstates evidence in front of makoto: a claimed "tests pass" over a recorded test *failure*; a citation absent from the declared set; a WebFetch URL no prior tool returned. |
| **HOLLOWED** | it survives in name while its definition is gutted: a loosened comparator in an integrity file; a suppression flag; env-gated audit code; `\|\| true` masking a test runner. *Loosening a test empties the word "test."* |
| **BYPASSED** | it is silenced or routed around: disabling patterns or un-wiring the hook in `settings.json`; abusing `makoto-allow`. |
| **PURPOSE-CONTRADICTION** | an exemption or self-edit is deployed *to empty another word*, a composite of BYPASSED plus exemption-abuse: a bare `makoto-allow` added in the same edit that disables another check, laundering the bypass past the guard. |

Every live check in README.md's "What it catches" section is derived from one of these seven
rows; that section is the current, tested mapping from principle to code, kept in sync with the
live catalog by its own materiality tests.

---

## 5. The Monotonicity Invariant

**Once a word like "test X" has a definition, its meaning may only be PRESERVED or DEEPENED, never
made less meaningful, less complete, skipped, or bypassed.**

A test only has meaning if it has integrity. **A bypassable test was never a test.** A check wired
to always pass is not a relaxed check; it is the *absence* of a check wearing the check's name. You
may strengthen a check, add cases, tighten a comparator; you may not loosen it, env-gate it, mask
its exit code, or mute the watchdog that reads it. The direction of meaning is one-way. This is the
moral core of the HOLLOWED and BYPASSED classes, and the reason a mint never debases its own coin.

---

## 6. The Design Rule for Future Patterns

**For any proposed shape, ask: *what word is being emptied here, and how?***

Name the word. Name the emptiness-kind from §4. If you cannot name the emptied word, if the shape
is a style preference, an efficiency nudge, or a guess about the world, **it is not a makoto
pattern.** (This is why shell/git-hygiene nudges are not integrity patterns: they keep a convention,
not a word.)

**Two independent admission filters, two kinds of cut.** A candidate must pass *both*: it must be
**about the weight of a word** (this section's test, *constitutional*) **and** be **detectable at
zero false positives** (the corpus-FP ratchet, *tractable*). The filters are orthogonal, and so are
the reasons a pattern is scrapped. A shape cut for **tractability** (no FP-safe signal on the corpus)
is *a word-weight pattern makoto cannot yet catch*; it may **return** the day a cleaner corpus or a
sharper discriminator gives it teeth. A shape cut as **preference** (a convention, a nudge, a taste)
is *not a word at all*; no corpus and no discriminator can ever resurrect it, because there was never
an emptied word to keep. Never conflate the two: "we couldn't measure it" and "it was never ours to
measure" are different verdicts, and only the first is revisable.

Every pattern must obey makoto's own constants:

- **Fail-open, never timid.** A check is never made inert to dodge work; that would trade away the
  functionality makoto exists for. Block only on what makoto positively knows.
- **The AI's own word only.** A shape that could fire on the user's content violates the cardinal
  rule and is a bug, not a pattern.
- **Monotone.** A new pattern may only preserve or deepen a word's meaning, never ship as a shape
  that, once known, can be cheaply emptied. If it can, it was never a check.
- **Honest about its own teeth.** A pattern that only warns is documented as a warning. To claim a
  warning blocks would be makoto overclaiming its own coverage, the precise emptiness it exists to
  catch, turned inward.
