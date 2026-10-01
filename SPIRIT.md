# Makoto spirit

## WHY
Repo clause (verbatim): Makoto prevents blindspots through detection

Full WORDS.tsv WHY row (verbatim):
```tsv
WHY	2026-10-01T21:41Z	Makoto prevents blindspots through detection, DetIO cuts tokens and increases relevance Deterministically, tiller routes perfectly, and countdown creates a true countdown that ends up perfect at the thin line between something and nothing through the shortest possible path, with seed being created and mesh created to make it the shortest for that project
```

## Done-bar
Owner's DONE words (verbatim, WORDS.tsv DONE):
"thinnest line between something and nothing, force perfect flexibility. DONE = packaged, installed, proven in a fresh session, WHOLE repo clean outside history"

All mesh holes must be met against current inputs. Historical evidence is not a current receipt. Mesh is a timeless conjunction; PLAN.md is the remaining dependency order. A suite pass does not prove fresh installation, register alignment, exact-head CI, or whole-repo audit.

## Acceptance checks
- rule-behavior: every shipped rule has a blocking slip and silent control; run tests/test_evaluate.py. Citation: copied S1/S2 below and pinned tests/sources.tsv.
- observation: settled effects bind to the correct object and turn; denied/pending calls do not count as deeds; run tests/test_observed.py. Citation: copied S2 subject-bound witness.
- hook-output: first finding denies/blocks, unchanged state is silent, changed state can fire; run tests/test_hook.py directly as a unit test, without installing or invoking any hook. Citation: local six assertions and copied S2.
- source-pins: every row has a case and a verbatim pinned quote; run the named source test. This proves fixture agreement, not external source provenance. Citation: tests/sources.tsv and input pins below.
- register-alignment: owner-approved predicates, source citations, shared family checks, attributed removals, and replay regression accounting. REGISTER.md, CITATIONS.tsv, REPLAY.tsv, REGISTER-PROPOSAL.md are recovery inputs; their existence alone never closes this hole. The current check deliberately fails after that recovery gate until a semantic checker and hostile plant are implemented. Citation: copied S1 audit.
- package-consistency: marketplace points to ./plugin and README title matches manifest version. Citation: WORDS.tsv DONE. No hook wiring requirement is added: the owner forbids hooks in this formation pass.
- fresh-installation: intended version loaded in a fresh account/session, actual slip blocked, look-alike silent, no runtime errors; retain source-pinned receipts and implement a receipt checker with a missing-plugin plant. Current check deliberately fails pending that checker. Citation: WORDS.tsv DONE and copied S1 (older version only).
- complete-validation: local suite and five CI jobs pass on the exact selected head, with retained receipts and a checker rejecting another revision. Current check runs the local suite then deliberately fails pending exact-head CI verification. Citation: copied S1.
- whole-repo-clean: audit every current tracked and ignored file outside history for credentials, private infrastructure, stale/dead/duplicate content; pin audit inputs; prove clean worktree. Current check deliberately fails pending a content checker with a planted-secret test. Citation: WORDS.tsv DONE.

MESH.tsv commands run from repo root with POSIX sh; Python >=3.11 and pytest are required. Each plant creates and mutates a private copy under ${TMPDIR:-/tmp}; it never mutates this checkout. To test a plant, execute its command: it prints the copy path, then execute that row's check from that path; require a nonzero exit. Retain or remove only that printed private directory after review. Blocked holes already fail; their plants demonstrate a missing prerequisite, not sensitivity of an unimplemented semantic checker. Replace provisional checks and plants before closing those holes.

## Scope
Makoto detection, portable evidence, package integrity, register alignment, current validation, fresh-session proof, and whole-repo current-content audit. Preserve subject binding and source-backed predicates. Owner decides register amendments and merges.

## Out-of-scope
DetIO, Countdown, Tiller implementation; historical cleanup or history rewriting; publishing, merging, credentials, hooks installation/configuration, or edits beyond this formation's six artifacts. Existing hook code/configuration is untouched. If “no hooks anywhere” requires their removal, that requires a separately authorized source change; this pass cannot claim that property.

### Input pins
Git blob hashes below were obtained with `git hash-object` in this checkout.
Check each with `git hash-object PATH`; a changed blob invalidates the affected status.
These pin all tracked inputs at the snapshot; HANDOFF.md cannot pin its own bytes.

| repo file | git blob |
|---|---|
| .claude-plugin/marketplace.json | `989e2577eec0e7675a2f5de643757822e151032e` |
| .claude/settings.json | `8551dc8112179904110e15ae05198bea4801af38` |
| .gitattributes | `5788002e3211037dcb62b6decdd1c842e2d35077` |
| .github/workflows/ci.yml | `1e1a4e527e013d9d1a8e5301d6f504e498f46a55` |
| .github/workflows/release.yml | `1d78c4c21c44bec6f1edaf363b7379571d2a99b6` |
| .gitignore | `7c36d99ff2e8943941e905f40493b6ba6544ee98` |
| LICENSE | `d645695673349e3947e8e5ae42332d0ac3164cd7` |
| README.md | `01443832a432092cb6606d31e590a6b986139853` |
| plugin/.claude-plugin/plugin.json | `90447d707faa4dc9986de72eaa53e132a7f73eb2` |
| plugin/hooks/hooks.json | `12bf03570e9e673d7151aa55ae5cda59fea50fe0` |
| plugin/makoto2/CONFIG_KEYS.txt | `8a9f22791fc98d6e4343ed2ff5f0595f9f4dc8da` |
| plugin/makoto2/__init__.py | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| plugin/makoto2/__main__.py | `32669e303a8c9ebcef2970d9d6f268be5b4a9c54` |
| plugin/makoto2/config.json | `7d96971cd746aae426fb4397bb7c8d93297111fb` |
| plugin/makoto2/evaluate.py | `a76bf352758a9ef04df92b8772693a16a42f261e` |
| plugin/makoto2/hook.py | `23f667d27c823c35c8fb3246031ef6665e4f9112` |
| plugin/makoto2/observed.py | `b168bc5b16a40d7e77a95f0be39b460b8734511f` |
| plugin/makoto2/rows.tsv | `baad09cf44c56fe3a3f31c71840dfdf06b09d6bd` |
| tests/sources.tsv | `1bf332c02e33243c61210211a88b487ce54c18ab` |
| tests/test_evaluate.py | `685ef0888f3ac3a01b7ad619a8e6ba429fb80997` |
| tests/test_hook.py | `b3fb02e4b7b6e1d91c1554656fa7def446a6fe21` |
| tests/test_observed.py | `a27f6710263ca5ff2e23c077b61bcf7bc03ed01b` |

## Copied evidence and decisions
S1 = PLANS/MAKOTO.md, 2026-10-01, lines 19-52:
- #130 merged as 1325511; five CI jobs green; fresh `claude -p` loaded 4.0.0.
  Merge did not publish a release: release workflow is manual (lines 19-20).
- #131 merged as a9ecde7; cost-claim slips 0/5 -> 5/5, controls 4/4 silent.
- #132, branch claude/makoto-blindspots, version 4.0.2, head 6d628a4:
  historical five-job CI green; C12 and opt-in I1/I2/I3 checks added; merge held.
- Gabriel: "Makoto enforces the REGISTER. Not the other way around."
  Makoto measures nothing. Earlier NEEDS-SIGNAL verdicts for H3/B26/G3/D8/F12/I2
  were rejected for skipping family-shape tests (lines 45-46).
- Register audit on claude/makoto-register-shapes atop #132: FAIL incomplete;
  seven uncited rule components removed, three draft removals, 84 tests per Python job,
  mesh 9/20 slips plus 20/20 silent controls, 33 unattributed replay regressions,
  61 unresolved shapes and four conflicts (line 49). These files are absent here.
- One test may cover several entries; amend REGISTER, not Makoto (line 51).
  Family -> four family runs -> combine chain launched; no final result in this source.
  Expected combine outputs: verdict, PR body, register proposal (line 52).
S2 = LEDGER/OUTCOMES.tsv lines 1782-1784,1799,1844-1847:
- Claim-reader experiment failed: six false alarms remained; no claim reader ships.
- Inventory was 77 entries, not assumed 64: covered 7, half 39, none 29, duplicate 2.
- Subject-bound terminal witness improved mesh slips 4 -> 9/20, controls 20/20,
  337 replay cases with zero regressions. Preserve it during the register audit.
S3 = VERIFY/MESH/HOLES.tsv:2-4 and PROCESS.md:
- Makoto owns present integrity, not the reviewer or another ledger.
  Old 3.x installed mesh 155 cases is historical, not this 4.x done-bar.
- One owner per hole, wake only on changed input, parent reads a bounded verdict.
S4 = VERIFY/CURRENT.tsv:2,6,8,10; Countdown provenance only:
- SEED28 hash prefix 5937c56e575c; Seed.v 4e500556c22b; checker a572073fe5ae;
  7,342 instances, 48/48 plants red. These are SHA-256 prefixes, not repo blob pins.
  None of these external artifacts is required to run this Makoto suite.
S5 = PLANS/COUNTDOWN-NEXT.md:64-86: derive distance 26 -> 0 was held;
  legacy runtime restoration later merged as MZ #51. Do not revive stale ordered plans.
S6 = PLANS/COUNTDOWN-DONE.md:39-49: MZ #90 merged c0b8a1a;
  later bc7c9cd settings plus user-scope install made fresh init list zero:countdown
  and zero:zero. This is Countdown evidence, not proof Makoto is installed now.
S7 = PLANS/ROUTER.md:1-10: Tiller is router home; #27 owner-merged;
  route-test G1-G4/tail plants and live toy passed; later 28/28 checks, 47/47 plants red.
S8 = PLANS/DETIO-SEED-MESH.md:14-19: #87 head 97d5fe9; 61 pass, one fail
  requiring complete Causality-Dev. Chain9 strict schema rejected by API;
  chain9b and live chain10 denied. Four standalone tools were unwired: wire or delete.
  RelevantFraction lacks semantic/source and accepted-harm receipts;
  CurrentExactState renderer lacks consumer. These are DetIO blockers, not Makoto fixes.

