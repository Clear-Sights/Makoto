# Blindspot Register v9

`REGISTER v9  entries=77 collapsed=0 per-case=58 not-claimed=19 words=28 dedupe-marked=35 owners scour=2 makoto=38 owner-dedupe=25 blindspot=12 families: makoto=35 scour=10 gate=16 kernel=3 lineage=5 drift=4 judgment=4 lines=77 distinct-after-dedupe=59 over-ten-terms=0  (statuses read from HANDOFF/sections/makoto.md; collapsed only when landed in Makoto #105)`

Regenerate: `python3 /mnt/project-files/MAKOTO/registry-v9.py`. Every predicate is inferred until the attacker has attacked it.

## Predicate language

```
FIVE FAMILIES (his 03:29Z), one per decider, chosen by the variables an entry's line needs: makoto (what the Pre hook sees), scour (the tree,
static: ast nodes, calls, refs), gate (a run's result: exit, elapsed, git state after a run, plants), kernel (zero.py plan verdicts: met, shape, TERMS rows),
judgment (a narrowed question a model answers about work that is NOT its own: the line is the question and its sealed reader). No line asks a model about itself.
LINEAGE and DRIFT (his 03:31-03:32Z) are shapes, not opinions, over two ledger variables the evaluator records once:
  source.read: path -> content hash at the time it was read, for content this session did NOT itself write (an own answer is never a source);
  refs(output): the paths, urls, shas and quoted values a Write/Edit content or closing text names.
  lineage: a name in refs(output) with no entry in source.read (answered from an answer, or from the head, not from the source).
  drift: a name in refs(output) whose source.read hash differs from its hash now (answered without looking again).
Every entry has exactly one family and one line.
PREDICATE LANGUAGE (makoto family; the other families use the same operators over their own variables). Each claimed entry's set is ONE line, at most ten terms, no free text. Variables are what a hook sees at the event
(Pre: the tool call about to run; Stop: the turn's closing text, read by one claim reader) plus the session's own record of EARLIER events
(their args, exits and outputs as recorded). No before-and-after tree state: a set that needs the state after the act says "needs post state".
  line  := conj (" or " conj)*            conjuncts sorted, disjuncts sorted: identical canonical lines are one entry
  conj  := atom (" and " atom)*
  atom  := ["not "] var op value | seen(conj) | unseen_since(conj, conj) | verifier | claim.names | claim.falsifier | tree.X.exists
  var   := event tool path args.<field> settings.<key> exit output claim.kind claim.subject claim.number reads.distinct
  op    := = != in matches(regex) >= <=
  seen(X): some earlier recorded event satisfies X. unseen_since(X, Y): no event satisfies X after the last one satisfying Y.
  $v: the current event's value of v. verifier: this command key has exited nonzero at least once this session (its verdict is its exit).
  Named sets, one table each in the evaluator: MODEL, TEST_PATH, DOC_PATH, WAIVER, SUPPRESS, PLUGIN.
  claim.kind in {cite, pass, clean, absent, done, shipped, running, count, plan, retracted, question, cannot}: one claim reader.
  NO MODEL (his 03:27Z: a model cannot judge itself). Every term is evaluated by a script: the claim reader is a fixed word table
  plus regexes over the closing text (claim.subject = the path, url, sha or command it names); claim.names = the text contains one of
  the failure identities the run recorded; claim.falsifier = the text names a command or path that would redden. An entry whose set
  would need a model to decide is NOT EXPRESSIBLE with "needs judgment" as its missing fact.
```

## Register (v8 structure; per entry: predicate, merged, effect, check, status, owner)

```
=========================================
THE BLINDSPOT REGISTER
=========================================
Find the family. Read down. Stop at the
one that stings.

A family is what a checker must have in
hand to catch its entries; two families
needing the same thing are one. Read
every fix line and there are four, each
needing what the one before lacks. An
entry lives under its shape. Its id is a
name, kept: the letter says where it
was born.

1  THE SPEC
   the thing isn't what its definition says
   needs: one reading, and a definition
   the checker already holds
2  THE OTHER POINT
   true where made, not where it landed;
   true then, not now; true here, not there
   needs: a second reading of the same
   thing; no definition held
3  THE SWITCH
   a branch nothing ever selected
   needs: an act first: feed an input,
   then read the response
4  THE LINEAGE
   answered from an answer, not the source
   needs: the readings themselves: what
   was read before the write

===== 1 - THE SPEC =====================
  needs: one reading, and a held definition
A2  SURFACE-FORM IDENTITY
    same spelling taken as same thing
  > canonicalize; test both directions
  family: lineage
  predicate: event in {Pre,Stop} and refs(output)-source.read!={}   [terms=2; inferred until attacked]
  merged: one line with G1,H1,H4,H5; one check serves them
  effect: citation
  check: content.phantom_citation
  dedupe: effect "citation" shared with content.fabricated_commit_sha,content.unsourced_webfetch; collapse candidate
  status: per-case: not landed in #105; check shared with G1
  owner: lineage (decided: its line reads the read ledger: every name the output uses traces to a source read this session); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
A3  POSITIONAL PAIRING
    two sequences assumed to line up
  > join on a shared key
  family: scour
  predicate: call=zip and not kw.strict=True   [terms=2; inferred until attacked]
  effect: read
  check: gate.unread_structure
  status: per-case: not landed in #105
  owner: scour (decided: its line reads only the tree, statically); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
A4  LAST-WINS  (+A10)
    duplicate keys; which one wins is unstated
  > define the winner; test both orders
  family: scour
  predicate: keys.duplicated!={} and node=dict   [terms=2; inferred until attacked]
  effect: duplicate
  check: content.last_wins
  dedupe: effect "duplicate" shared with gate.canon,gate.canon_fingerprints,gate.pasted_fix; collapse candidate
  status: per-case: not landed in #105
  owner: scour (decided: its line reads only the tree, statically); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
A5  WRAPPER STRIPPED
    the context around the value was dropped
  > compare whole output, not the inner value
  family: judgment
  predicate: Q: does the value as quoted keep the context that made it true (its commit, its unit)?; the read-ledger shape that would decide it is not given yet, so it stays a question | sealed reader on another session output   [terms=0; inferred until attacked]
  effect: duplicate
  check: gate.canon_fingerprints
  dedupe: effect "duplicate" shared with content.last_wins,gate.canon,gate.pasted_fix; collapse candidate
  status: per-case: not landed in #105; check shared with A11
  owner: judgment (its family); today covered by: makoto
A7  ONE-NUMBER CONFLATION  (+B27 B6)
    one total hides parts that differ
  > compare per unit, at the grain you cite
  family: makoto
  predicate: claim.kind=pass and event=Stop and not seen(exit=0 and args.command matches $claim.subject)   [terms=5; inferred until attacked]
  merged: one line with C3; one check serves them
  effect: run
  check: gate.named_test
  dedupe: effect "run" shared with gate.liveness,gate.report_before_run,gate.unpaid_acceptance,gate.unwitnessed_verifier; collapse candidate
  status: per-case: not landed in #105; check shared with C3
  owner: makoto (its family)
A11 REPLAY COUNTED AS NEW
    a re-emission counted as a fresh occurrence
  > count distinct content, not records
  family: makoto
  predicate: args.command matches ">>" and event=Pre and seen(args.command=$args.command and exit=0) and tool=Bash and unseen_since(tool in {Write,Edit}, args.command=$args.command)   [terms=9; inferred until attacked]
  effect: duplicate
  check: gate.canon_fingerprints
  dedupe: effect "duplicate" shared with content.last_wins,gate.canon,gate.pasted_fix; collapse candidate
  status: per-case: not landed in #105; check shared with A5
  owner: makoto (decided: its line reads only what the Pre hook sees); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
A13 SETTING CALLED INHERENT
    a configured value described as a property
  > name which layer set it, and where it changes
  family: gate
  predicate: (author in MODEL or trailers matches MODEL or message matches MODEL) and run="git log base..HEAD"   [terms=4; inferred until attacked]
  merged: one line with E3; one check serves them
  effect: attribution
  check: gate.claude_identity
  dedupe: effect "attribution" shared with content.illusory_authorship_trailer; collapse candidate
  status: per-case: not landed in #105
  owner: gate (decided: its line reads a run result); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
B2  VACUOUS GREEN  (+A9 B13 B8 B22)
    a set never counted, or absence, taken as proof
  > count the population independently, then the property
  family: makoto
  predicate: event=Pre and not args.content matches "\b(assert|raise|expect)" and path matches TEST_PATH and tool in {Write,Edit}   [terms=4; inferred until attacked]
  merged: one line with B20,B5; one check serves them
  effect: hollow
  check: gate.hollow_test
  dedupe: effect "hollow" shared with content.verifier_body_hollowed; collapse candidate
  status: per-case: not landed in #105; check shared with B5,B20
  owner: makoto (decided: its line reads only what the Pre hook sees); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
B7  RULE WITH NO RUNNER  (+B15 B33 F11)
    written or cited, enforced nowhere live
  > bind every rule to a check on every path
  family: kernel
  predicate: zero.py: a TERMS row with check column empty   [terms=0; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: tools/merge_pass.py is not a hook check
  owner: kernel (decided: its line reads a zero.py plan verdict); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
B9  WAIVER NEVER EXPIRES  (+B25)
    an exemption with no checkable end
  > every waiver names a checkable discharge
  family: makoto
  predicate: args.content matches WAIVER and event=Pre and not args.content matches "\b(until|expires|remove by)\b" and tool in {Write,Edit}   [terms=4; inferred until attacked]
  effect: waiver
  check: gate.undischarged_waiver
  status: per-case: not landed in #105
  owner: makoto (decided: its line reads only what the Pre hook sees); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
B23 BOUND AS COUNT
    a ceiling with slack only says yes
  > assert equality; retighten on each change
  family: makoto
  predicate: args.content matches "assert\s+len\(.*\)\s*<=?\s*\d+" and event=Pre and path matches TEST_PATH and tool in {Write,Edit}   [terms=5; inferred until attacked]
  effect: count
  check: content.bound_as_count
  status: per-case: not landed in #105
  owner: makoto (its family)
B35 UNDECLARED EXEMPTION
    the code exempts what the rule never mentions
  > enumerate exemptions from the code; each declared
  family: makoto
  predicate: args.content matches SUPPRESS and event=Pre and not args.content matches "ADR-\d+" and tool in {Write,Edit}   [terms=4; inferred until attacked]
  effect: bypass
  check: content.integrity_suppression_flag
  status: per-case: not landed in #105
  owner: makoto (its family)
B36 UNMATCHED RESIDUE UNREPORTED
    a recognizer's misses vanish instead of counting
  > report the residue it did not match
  family: scour
  predicate: body matches "re\.(match|search)" and node=loop and not else_branch   [terms=2; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: REFUSED WITH A MEASUREMENT. In code, the closest reading, a loop that keeps regex matches with no branch for the misses, matched 73 sites in 2,331 files (this tree, Measure-Zero, Measure-Zero-Dev, CPython 3.11's stdlib, and the site-packages of this tree's test environment)
  owner: scour (its family)
C2  MISSING THIRD STATE  (+A1)
    "couldn't run", or absence, forced into a valid value
  > carry not-evaluable in its own field
  family: makoto
  predicate: claim.kind in {clean,absent} and event=Stop and not claim.falsifier   [terms=3; inferred until attacked]
  merged: one line with B32; one check serves them
  effect: claim
  check: gate.undeclared_falsifiable
  dedupe: effect "claim" shared with gate.claimed_running,gate.claimed_shipped,gate.completion; collapse candidate
  status: per-case: not landed in #105; check shared with B32
  owner: makoto (decided: its line reads only what the Pre hook sees); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
C6  SIGN INVERTED
    right number, wrong direction recorded
  > state the wanted direction beforehand
  family: makoto
  predicate: args.new matches "(<=|>=|\bin\b)" and args.old matches "==" and event=Pre and path matches TEST_PATH and tool=Edit   [terms=9; inferred until attacked]
  effect: weaken
  check: content.verifier_predicate_weakened
  status: per-case: not landed in #105
  owner: makoto (its family)
C7  TRUNCATION AS COMPLETION
    an interrupted producer's partial output accepted
  > require a terminator or a count
  family: makoto
  predicate: claim.kind=done and event=Stop and not tree.$claim.subject.exists   [terms=3; inferred until attacked]
  merged: one line with D1; one check serves them
  effect: claim
  check: gate.completion
  dedupe: effect "claim" shared with gate.claimed_running,gate.claimed_shipped,gate.undeclared_falsifiable; collapse candidate
  status: per-case: not landed in #105; check shared with D1
  owner: makoto (decided: its line reads only what the Pre hook sees); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
C10 ABSENCE ON ONE ROUTE
    the answer arrived by a route you never read
  > name every route; absence needs all of them
  family: makoto
  predicate: claim.kind=shipped and event=Stop and not seen(args.command matches "git\s+push" and exit=0)   [terms=5; inferred until attacked]
  effect: claim
  check: gate.claimed_shipped
  dedupe: effect "claim" shared with gate.claimed_running,gate.completion,gate.undeclared_falsifiable; collapse candidate
  status: per-case: not landed in #105
  owner: makoto (its family)
C12 VERDICT WITHOUT ITS SUBJECT
    a failure was counted but never named
  > name the failing identity in its own run
  family: makoto
  predicate: claim.kind=count and event=Stop and not claim.names and seen(verifier and exit!=0)   [terms=6; inferred until attacked]
  effect: failure
  check: gate.unnamed_failure
  status: per-case: not landed in #105
  owner: makoto (its family)
D13 UNENUMERATED DESTRUCTION
    removing a set never listed, or whose members nest
  > list first, expand each member, act on exactly that
  family: makoto
  predicate: event=Stop and not seen(claim.kind in {done,retracted} and claim.subject=$item) and seen(claim.kind=plan and claim.subject=$item)   [terms=7; inferred until attacked]
  merged: one line with F8; one check serves them
  effect: drop
  check: gate.dropped
  dedupe: effect "drop" shared with gate.plan_item_drift; collapse candidate
  status: per-case: not landed in #105
  owner: makoto (its family)
E3  COINCIDENCE
    a pattern that matched by accident
  > require an explicit intent marker
  family: gate
  predicate: (author in MODEL or trailers matches MODEL or message matches MODEL) and run="git log base..HEAD"   [terms=4; inferred until attacked]
  merged: one line with A13; one check serves them
  effect: attribution
  check: content.illusory_authorship_trailer
  dedupe: effect "attribution" shared with gate.claude_identity; collapse candidate
  status: per-case: not landed in #105; escapes by shape: trailer via key=value flag, an alternate attribution key, a different verb, the author field, an escaped-byte name, prose in a PR body
  owner: gate (its family); today covered by: makoto
E5  UNBOUNDED RETRY
    a loop whose only exit is success
  > cap it, with a path for "still failing"
  family: makoto
  predicate: event=Pre and seen(args.command=$args.command and exit!=0) and tool=Bash and unseen_since(tool in {Write,Edit}, args.command=$args.command)   [terms=8; inferred until attacked]
  merged: one line with E10; one check serves them
  effect: repeat
  check: event.identical_retry
  dedupe: effect "repeat" shared with gate.relaunched_unchanged; collapse candidate
  status: per-case: not landed in #105; check shared with E10
  owner: makoto (decided: its line reads only what the Pre hook sees); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
E10 RETRY BLIND TO CLASS  (+F13)
    retrying without classifying the failure
  > map each class to retry or stop; name what changed
  family: makoto
  predicate: event=Pre and seen(args.command=$args.command and exit!=0) and tool=Bash and unseen_since(tool in {Write,Edit}, args.command=$args.command)   [terms=8; inferred until attacked]
  merged: one line with E5; one check serves them
  effect: repeat
  check: event.identical_retry
  dedupe: effect "repeat" shared with gate.relaunched_unchanged; collapse candidate
  status: per-case: not landed in #105; check shared with E5
  owner: makoto (its family)
E11 NESTED BUDGET SHADOWED
    an outer limit smaller than yours
  > name the limiting layer before retrying
  family: gate
  predicate: elapsed>=budget and run=suite   [terms=2; inferred until attacked]
  effect: budget
  check: event.nested_budget
  status: per-case: not landed in #105; escapes by shape: a timeout argument inside a nested interpreter, a sleep loop exceeding the outer budget
  owner: gate (its family); today covered by: makoto
E12 PRINCIPAL EXCLUDED
    rewording can't grant what you can't hold
  > read which attribute the gate inspects
  family: gate
  predicate: (settings.disableAllHooks=true or settings.enabledPlugins.makoto!=true or not tree.PLUGIN.exists) and launch   [terms=3; inferred until attacked]
  effect: disable
  check: content.self_mute_guard
  status: per-case: not landed in #105; escapes by shape: kill-switch written by shell redirect, in-place edit adding the disable variable, the plugin disabled in the enable map, the plugin folder moved
  owner: gate (its family); today covered by: makoto
E13 PARKED ON AN INHERITED CHANNEL
    a detached task waits on input nobody sends
  > close or redirect every channel you don't feed
  family: makoto
  predicate: event=Pre and seen(tool=Agent and args.prompt=$args.prompt) and tool=Agent and unseen_since(verifier, tool=Agent)   [terms=8; inferred until attacked]
  effect: repeat
  check: gate.relaunched_unchanged
  dedupe: effect "repeat" shared with event.identical_retry; collapse candidate
  status: per-case: not landed in #105
  owner: makoto (its family)
G2  DETERMINED ASKED AS OPEN  (+G4)
    a settled quantity or decision sent out as open
  > derive it; ask only what survives derivation
  family: makoto
  predicate: claim.kind=plan and event=Stop and not seen(claim.kind=question)   [terms=4; inferred until attacked]
  effect: ask
  check: gate.unasked_plan
  status: per-case: not landed in #105
  owner: makoto (its family)
G3  SCOPE BELOW THE ANSWER
    each part sees less than the answer spans
  > give one party the whole span
  family: judgment
  predicate: Q: does any one party see the whole span the answer covers?; the read-ledger shape that would decide it is not given yet, so it stays a question | sealed reader on another session output   [terms=0; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: needs each party's span compared against the answer's
  owner: judgment (its family); today covered by: none, a blindspot this line closes
G5  WALL WITHOUT INVENTORY
    "cannot" declared with the means already held
  > list what you hold before saying no
  family: makoto
  predicate: claim.kind=cannot and event=Stop and unseen_since(event=Pre, event=User)   [terms=5; inferred until attacked]
  effect: wall
  check: gate.unexamined_wall
  status: per-case: not landed in #105
  owner: makoto (its family)


===== 2 - THE OTHER POINT ==============
  needs: a second reading of the same thing
A14 NORMALIZATION MERGES
    a cleanup mapped two distinct inputs onto one
  > assert count in equals count out
  family: scour
  predicate: key=call(item) and node=dictcomp and not seen_assert(len_in=len_out)   [terms=3; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: REFUSED WITH A MEASUREMENT. The closest reading, a dict or set comprehension keyed by a normalizing call of its item (`{k.lower(): v for k, v in ...}`), matched 21 sites in 2,331 files (this tree, Measure-Zero, Measure-Zero-Dev, CPython 3.11's stdlib, and the site-packages of this tree's test environment), and the merge is the intent at CPython 3.11 distutils/_msvccompiler.py:115 (Windows environment names are case-insensitive) and pip's req/req_uninstall.py:123 (normcase paths). Whether two inputs should merge is intent the code does not state
  owner: scour (its family)
B4  WRONG ORACLE  (+B30)
    a stand-in graded some or all, not the target
  > find where proxy and target disagree
  family: makoto
  predicate: claim.kind=clean and event=Stop and not seen(args.command=$claim.subject and exit!=0)   [terms=5; inferred until attacked]
  effect: run
  check: gate.unwitnessed_verifier
  dedupe: effect "run" shared with gate.liveness,gate.named_test,gate.report_before_run,gate.unpaid_acceptance; collapse candidate
  status: per-case: not landed in #105
  owner: makoto (its family)
B11 BASELINE UNTAKEN  (+B12)
    a failure attributed without a graded base
  > run the baseline; grade it on its own bar
  family: makoto
  predicate: event=Pre and tool=Agent and unseen_since(tool in {Bash,Glob,Grep,Read}, event=User)   [terms=5; inferred until attacked]
  effect: dispatch
  check: gate.unprobed_fanout
  dedupe: effect "dispatch" shared with event.unbriefed_dispatch; collapse candidate
  status: per-case: not landed in #105
  owner: makoto (its family)
B14 MECHANISM AS OUTCOME
    built and firing, never shown to help
  > measure with and without
  family: gate
  predicate: claim.helps and not run_pair(with,without).differs   [terms=0; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: argued, not probed. The witness is two runs of one measurement that differ only by the mechanism, plus the claim that it helped. Nothing in a command marks which token is the mechanism, so pairing two runs as with and without is a similarity judgement
  owner: gate (its family); today covered by: none, a blindspot this line closes
B18 IN-SAMPLE SELECTION  (+B19)
    scored only on what it was built from
  > report on something you didn't build
  family: judgment
  predicate: Q: was the scored set any part of what the scored thing was built from?; the read-ledger shape that would decide it is not given yet, so it stays a question | sealed reader on another session output   [terms=0; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: argued, not probed. The witness is that the scored set was not the one the thing was built from. The record shows a score and the file it ran on, never what shaped the thing being scored, and a score on a file the session wrote itself reads the same as an honest regression test
  owner: judgment (its family); today covered by: none, a blindspot this line closes
B26 UNSUPERVISED SUPERVISOR
    the guarantor of delivery died unnoticed
  > make its liveness an output; absence fails loud
  family: gate
  predicate: launch and not planted_event.fires   [terms=0; inferred until attacked]
  merged: one line with B1,D9; one check serves them
  effect: circular
  check: gate.self_wired
  status: per-case: not landed in #105; check shared with B1,D9
  owner: gate (its family); today covered by: makoto
C8  LAUNCHER EXIT AS JOB EXIT
    the starter returned; the work still ran
  > wait on something the work itself emits
  family: makoto
  predicate: claim.kind=running and event=Stop and not seen(output matches $claim.subject)   [terms=4; inferred until attacked]
  effect: claim
  check: gate.claimed_running
  dedupe: effect "claim" shared with gate.claimed_shipped,gate.completion,gate.undeclared_falsifiable; collapse candidate
  status: per-case: not landed in #105
  owner: makoto (its family)
D1  WRITE UNVERIFIED  (+A8 D5 D2 F5 C1)
    a write, setting, or status taken as its effect
  > read back through the consumer before trusting or retrying
  family: makoto
  predicate: claim.kind=done and event=Stop and not tree.$claim.subject.exists   [terms=3; inferred until attacked]
  merged: one line with C7; one check serves them
  effect: claim
  check: gate.completion
  dedupe: effect "claim" shared with gate.claimed_running,gate.claimed_shipped,gate.undeclared_falsifiable; collapse candidate
  status: per-case: not landed in #105; check shared with C7
  owner: makoto (its family)
D4  DERIVED ARTIFACT STALE  (+D6)
    a derivative older than its source
  > key on content; regenerate and compare
  family: drift
  predicate: event in {Pre,Stop} and exists n in refs(output) and source.read[n]!=tree[n].hash   [terms=3; inferred until attacked]
  merged: one line with F10,F7,H2; one check serves them
  effect: stale
  check: gate.stale_pass
  status: per-case: not landed in #105; check shared with F7,H2
  owner: drift (its family); today covered by: makoto
D8  SCALE UNTESTED  (+A12)
    proven small, or in another form
  > exercise at real magnitude, in the shipped form
  family: gate
  predicate: run.form!=shipped.form or run.size<real.size   [terms=1; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: argued, not probed. The witness is a run at the real magnitude in the shipped form, and the real magnitude appears in no hook payload
  owner: gate (its family); today covered by: none, a blindspot this line closes
D11 REWRITE BY ROUNDTRIP
    the edit drowned in a whole-artifact rewrite
  > bound the change, or append
  family: makoto
  predicate: event=Pre and tool=Write and tree.$path.exists   [terms=3; inferred until attacked]
  effect: revert
  check: event.thrash_revert
  status: per-case: not landed in #105
  owner: makoto (its family)
D12 PRESERVE TO VOLATILE
    the copy shares the fate it should survive
  > re-read it after the boundary
  family: makoto
  predicate: args.command matches "git\s+(checkout|switch|reset)\s+(\S+)" and event=Pre and not seen(output matches $ref) and tool=Bash   [terms=5; inferred until attacked]
  effect: ref
  check: gate.unknown_ref_switch
  status: per-case: not landed in #105
  owner: makoto (its family)
D14 UNDO UNPROVEN
    a trial's residue could not be removed
  > prove the undo on that target first
  family: gate
  predicate: git_status_after!="" and run=suite   [terms=2; inferred until attacked]
  effect: destroy
  check: gate.unobserved_destruction
  status: per-case: not landed in #105; escapes by shape: find-delete, a library tree removal, truncation to zero, a redirect of nothing, a move over a file, a Write of empty content
  owner: gate (its family); today covered by: makoto
E7  UNDECLARED ENVIRONMENT  (+E6 E4)
    it runs only here; ambient state stood in for conditions
  > set every condition; run from clean
  family: makoto
  predicate: args.content matches "if\s+os\.environ" and event=Pre and tool in {Write,Edit}   [terms=3; inferred until attacked]
  effect: skip
  check: content.env_gated_audit
  status: per-case: not landed in #105
  owner: makoto (decided: its line reads only what the Pre hook sees); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
F2  TWO SOURCES OF TRUTH  (+F1)
    one rule read independently wherever
    used, diverging -- between any two of
    them, or within one
  > one owner; every consumer calls it
  family: makoto
  predicate: event=Pre and seen(tool=Edit and args.new=$args.new and path!=$path) and tool=Edit and unseen_since(verifier, tool=Edit and args.new=$args.new)   [terms=10; inferred until attacked]
  merged: one line with H3; one check serves them
  effect: duplicate
  check: gate.pasted_fix
  dedupe: effect "duplicate" shared with content.last_wins,gate.canon,gate.canon_fingerprints; collapse candidate
  status: per-case: not landed in #105; check shared with H3
  owner: makoto (decided: its line reads only what the Pre hook sees); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
F7  CHECK-THEN-ACT RACE
    it moved between the check and the act
  > re-verify within the same exclusion
  family: drift
  predicate: event in {Pre,Stop} and exists n in refs(output) and source.read[n]!=tree[n].hash   [terms=3; inferred until attacked]
  merged: one line with D4,F10,H2; one check serves them
  effect: stale
  check: gate.stale_pass
  status: per-case: not landed in #105; check shared with D4,H2
  owner: drift (its family); today covered by: makoto
F8  STALE REFIRE
    the same alert forever, unread
  > suppress while unchanged; resurface on cadence
  family: makoto
  predicate: event=Stop and not seen(claim.kind in {done,retracted} and claim.subject=$item) and seen(claim.kind=plan and claim.subject=$item)   [terms=7; inferred until attacked]
  merged: one line with D13; one check serves them
  effect: drop
  check: gate.plan_item_drift
  dedupe: effect "drop" shared with gate.dropped; collapse candidate
  status: per-case: not landed in #105
  owner: makoto (its family)
F14 DECLARED CLASS TRUSTED
    "no behavior change" that changed behavior
  > compare behavior, not text
  family: scour
  predicate: ast.old!=ast.new and commit.message matches "no behaviou?r change"   [terms=2; inferred until attacked]
  effect: hollow
  check: content.verifier_body_hollowed
  dedupe: effect "hollow" shared with gate.hollow_test; collapse candidate
  status: per-case: not landed in #105
  owner: scour (its family); today covered by: makoto
G1  GOAL SUBSTITUTION  (+B24)
    answered, or cited evidence for, a nearby easier question
  > set each claim beside what it rests on
  family: lineage
  predicate: event in {Pre,Stop} and refs(output)-source.read!={}   [terms=2; inferred until attacked]
  merged: one line with A2,H1,H4,H5; one check serves them
  effect: citation
  check: content.phantom_citation
  dedupe: effect "citation" shared with content.fabricated_commit_sha,content.unsourced_webfetch; collapse candidate
  status: per-case: not landed in #105; check shared with A2
  owner: lineage (its family); today covered by: makoto


===== 3 - THE SWITCH ===================
  needs: an act first, then the response
A6  GRADIENT COLLAPSE
    a threshold maps near-perfect to zero
  > assert output tracks input throughout
  family: scour
  predicate: branches in {0,1} and node=ifexp and test matches ">=\s*0?\.\d+"   [terms=4; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: REFUSED WITH A MEASUREMENT. The closest reading, a float-literal comparison mapped straight onto 0 or 1 (`1 if s >= 0.9 else 0`), matched 0 of 2,331 files (this tree, Measure-Zero, Measure-Zero-Dev, CPython 3.11's stdlib, and the site-packages of this tree's test environment). Whether a threshold collapses a gradient depends on where the inputs fall, and neither the written code nor any hook payload carries the inputs
  owner: scour (its family); today covered by: none, a blindspot this line closes
B1  CHECKER SELF-TRUST  (+B3 B29)
    I wrote both the task and the oracle
  > see the verdict flip on a plant first
  family: gate
  predicate: launch and not planted_event.fires   [terms=0; inferred until attacked]
  merged: one line with B26,D9; one check serves them
  effect: circular
  check: gate.self_wired
  status: per-case: not landed in #105; check shared with B26,D9
  owner: gate (its family); today covered by: makoto
B5  MEASUREMENT THEATER
    the metric is a constant, not a measure
  > check where each metric is written
  family: makoto
  predicate: event=Pre and not args.content matches "\b(assert|raise|expect)" and path matches TEST_PATH and tool in {Write,Edit}   [terms=4; inferred until attacked]
  merged: one line with B2,B20; one check serves them
  effect: hollow
  check: gate.hollow_test
  dedupe: effect "hollow" shared with content.verifier_body_hollowed; collapse candidate
  status: per-case: not landed in #105; check shared with B2,B20
  owner: makoto (its family)
B10 NEVER-ABSTAINING CHECK
    fires on everything, so says nothing
  > measure its rate on benign input
  family: gate
  predicate: any(check=red) and run=suite_on_clean_base   [terms=2; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: tests corpus-FP invariant is not a hook check
  owner: gate (decided: its line reads a run result); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
B20 PLANT WITHDRAWN
    the input was edited, or the mutation changed nothing
  > the mutation must be observed to change the subject
  family: makoto
  predicate: event=Pre and not args.content matches "\b(assert|raise|expect)" and path matches TEST_PATH and tool in {Write,Edit}   [terms=4; inferred until attacked]
  merged: one line with B2,B5; one check serves them
  effect: hollow
  check: gate.hollow_test
  dedupe: effect "hollow" shared with content.verifier_body_hollowed; collapse candidate
  status: per-case: not landed in #105; check shared with B2,B5
  owner: makoto (its family)
B21 OVERDETERMINED VERDICT
    a sibling condition gave the same answer
  > isolate each condition with its own input
  family: gate
  predicate: plant=row and reddened_rows!={row}   [terms=2; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: tools/merge_pass.py is not a hook check
  owner: gate (decided: its line reads a run result); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
B28 ISOLATED CASES ONLY
    each case tested fresh; real runs are sequences
  > replay the real succession into shared state
  family: gate
  predicate: not replay_sequence.present and run=suite   [terms=1; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: argued, not probed. The fault is an absence: no case replays a real succession into shared state. The suite that would hold that case can sit anywhere, a Write shows one file, and a Stop check sees only what ran this session, so no event can establish the absence
  owner: gate (its family); today covered by: none, a blindspot this line closes
B34 LAW EXEMPTS ITS INSTRUMENT
    the law it enforces, its own machinery breaks
  > run the artifact's own law over the artifact;
    name every region it cannot
  family: gate
  predicate: run=gate_on_own_tree and verdict!=pass   [terms=2; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: tools/register_map.py is not a hook check
  owner: gate (its family); today covered by: makoto
B37 SIMPLER FORM UNSOUGHT
    a shorter equivalent exists; nothing asked
  > state the predicate twice, keep the shorter;
    an act proves them equal, not a reading
  family: kernel
  predicate: removal leaves met or zero.py: shape>0 (two units share a shape)   [terms=0; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: the witness is that two differently-worded predicates are equal. Equality of two predicates is undecidable in general (Rice's theorem)
  owner: kernel (its family); today covered by: none, a blindspot this line closes
C3  MASK
    one item's signal hides the rest
  > evaluate each item in isolation
  family: makoto
  predicate: claim.kind=pass and event=Stop and not seen(exit=0 and args.command matches $claim.subject)   [terms=5; inferred until attacked]
  merged: one line with A7; one check serves them
  effect: run
  check: gate.named_test
  dedupe: effect "run" shared with gate.liveness,gate.report_before_run,gate.unpaid_acceptance,gate.unwitnessed_verifier; collapse candidate
  status: per-case: not landed in #105; check shared with A7
  owner: makoto (decided: its line reads only what the Pre hook sees); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
C4  CRASH PERMITS
    the checker failed, so the act proceeded
  > an error resolves as a denial
  family: gate
  predicate: verdict=exit of the gate own run of each check; a reported exit is never read   [terms=1; inferred until attacked]
  effect: mask
  check: content.verifier_exit_masking
  status: per-case: not landed in #105; escapes by shape: a verifier followed by an unconditional exit, by an unconditional echo, a build tool told to ignore errors
  owner: gate (decided: its line reads a run result); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
C5  FALLTHROUGH  (+B16 E2)
    no branch for the shape that arrived
  > every dispatch ends in an error; feed foreign shapes
  family: scour
  predicate: node=match and not cases.last=wildcard_raise   [terms=2; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: dispatch fail-closed is not a hook check
  owner: scour (decided: its line reads only the tree, statically); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
C11 REPORT BEFORE DECIDE
    the outcome was emitted after the narration about it
  > emit the outcome first; reporting comes after
  family: makoto
  predicate: claim.kind=pass and event=Pre and not seen(verifier) and path matches DOC_PATH and tool in {Write,Edit}   [terms=6; inferred until attacked]
  effect: run
  check: gate.report_before_run
  dedupe: effect "run" shared with gate.liveness,gate.named_test,gate.unpaid_acceptance,gate.unwitnessed_verifier; collapse candidate
  status: per-case: not landed in #105
  owner: makoto (decided: its line reads only what the Pre hook sees); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
D9  SELF-INCLUSION  (+D10 B17)
    the actor or rule is inside its own set
  > exclude self by identity; plant a real instance
  family: gate
  predicate: launch and not planted_event.fires   [terms=0; inferred until attacked]
  merged: one line with B1,B26; one check serves them
  effect: circular
  check: gate.self_wired
  status: per-case: not landed in #105; check shared with B26,B1
  owner: gate (decided: its line reads a run result); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
E1  SHADOWED BRANCH
    a case that can never be selected
  > every branch needs a witness input
  family: scour
  predicate: node=stmt and not node=call and result.uses={}   [terms=3; inferred until attacked]
  effect: run
  check: gate.liveness
  dedupe: effect "run" shared with gate.named_test,gate.report_before_run,gate.unpaid_acceptance,gate.unwitnessed_verifier; collapse candidate
  status: per-case: not landed in #105
  owner: scour (its family); today covered by: makoto
E8  OPTION INTERACTION
    each setting valid, the combination not
  > bisect, then pin the combination
  family: gate
  predicate: shipped.settings!=tested.settings   [terms=1; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: argued, not probed. The witness is the combination of settings that ships, run and pinned. Which combination ships appears in no hook payload, so no event separates a tested combination from the one that matters
  owner: gate (its family); today covered by: none, a blindspot this line closes
E9  RECOVERY UNDEFINED HERE
    the fallback can't cover its own trigger
  > exercise it from the real failure state
  family: scour
  predicate: body.calls contains try.calls and node=except   [terms=1; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: REFUSED WITH A MEASUREMENT. The closest reading, an except handler that re-runs the call its own try just failed, matched 44 sites in 2,331 files (this tree, Measure-Zero, Measure-Zero-Dev, CPython 3.11's stdlib, and the site-packages of this tree's test environment)
  owner: scour (its family); today covered by: none, a blindspot this line closes
F6  MONOTONICITY ASSUMED
    removal resurrects, addition suppresses
  > walk the small state space
  family: kernel
  predicate: zero.py: removal of one unit changes met of an unrelated row   [terms=0; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: argued, not probed. The witness is a walk of the small state space. The states, and which of them a removal or an addition reaches, are behaviour of the code across runs, which no single event holds
  owner: kernel (its family); today covered by: none, a blindspot this line closes
F12 CAUSE FROM SYMPTOM
    the first plausible mechanism became it
  > verify one discriminating observation
  family: judgment
  predicate: Q: which observation distinguishes the named cause from the next plausible one, and was it made? | sealed reader on another session output   [terms=0; inferred until attacked]
  effect: none (not claimed)
  check: none
  status: not claimed: a discriminating observation between mechanisms is a similarity judgement
  owner: judgment (its family); today covered by: none, a blindspot this line closes


===== 4 - THE LINEAGE ==================
  needs: the readings themselves
B32 CLAIM RESTATES ITSELF
    the claim unfolds to itself; the proof is identity
  > reject a result whose proof does no work
  family: makoto
  predicate: claim.kind in {clean,absent} and event=Stop and not claim.falsifier   [terms=3; inferred until attacked]
  merged: one line with C2; one check serves them
  effect: claim
  check: gate.undeclared_falsifiable
  dedupe: effect "claim" shared with gate.claimed_running,gate.claimed_shipped,gate.completion; collapse candidate
  status: per-case: not landed in #105; check shared with C2
  owner: makoto (decided: its line reads only what the Pre hook sees); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
F10 DIGEST KEPT, SOURCE GONE  (+F9)
    trusting your own record of the event
  > re-derive or re-run it, or label it unverified
  family: drift
  predicate: event in {Pre,Stop} and exists n in refs(output) and source.read[n]!=tree[n].hash   [terms=3; inferred until attacked]
  merged: one line with D4,F7,H2; one check serves them
  effect: duplicate
  check: gate.canon
  dedupe: effect "duplicate" shared with content.last_wins,gate.canon_fingerprints,gate.pasted_fix; collapse candidate
  status: per-case: not landed in #105
  owner: drift (decided: its line reads the read ledger: a name used whose thing changed since it was last read); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
H1  ANSWER READ AS SOURCE  (+F4)
    the next answer drawn from the last answer
  > go back to the source for every question
  family: lineage
  predicate: event in {Pre,Stop} and refs(output)-source.read!={}   [terms=2; inferred until attacked]
  merged: one line with A2,G1,H4,H5; one check serves them
  effect: citation
  check: content.unsourced_webfetch
  dedupe: effect "citation" shared with content.fabricated_commit_sha,content.phantom_citation; collapse candidate
  status: per-case: not landed in #105
  owner: lineage (decided: its line reads the read ledger: every name the output uses traces to a source read this session); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
H2  OLD ANSWER READ AS CURRENT  (+F3 F15 F16)
    an earlier answer consumed as still true
  > read the source again, once, last
  family: drift
  predicate: event in {Pre,Stop} and exists n in refs(output) and source.read[n]!=tree[n].hash   [terms=3; inferred until attacked]
  merged: one line with D4,F10,F7; one check serves them
  effect: stale
  check: gate.stale_pass
  status: per-case: not landed in #105; check shared with D4,F7
  owner: drift (its family); today covered by: makoto
H3  FIX DRAWN FROM FIXES
    a change reasoned from other changes
  > order by dependence; one change per pass
  family: makoto
  predicate: event=Pre and seen(tool=Edit and args.new=$args.new and path!=$path) and tool=Edit and unseen_since(verifier, tool=Edit and args.new=$args.new)   [terms=10; inferred until attacked]
  merged: one line with F2; one check serves them
  effect: duplicate
  check: gate.pasted_fix
  dedupe: effect "duplicate" shared with content.last_wins,gate.canon,gate.canon_fingerprints; collapse candidate
  status: per-case: not landed in #105; check shared with F2
  owner: makoto (its family)
H4  SWEEP DRAWN FROM MEMORY
    each item read through prior conclusions
  > judge once up front; each read a token
  family: lineage
  predicate: event in {Pre,Stop} and refs(output)-source.read!={}   [terms=2; inferred until attacked]
  merged: one line with A2,G1,H1,H5; one check serves them
  effect: none (not claimed)
  check: none
  status: not claimed: (note withheld: carries a blocked string)
  owner: lineage (its family); today covered by: none, a blindspot this line closes
H5  REFERENT DRAWN FROM THE HEAD  (+D3 D7 C9)
    a thing pointed at, never read from source
  > name it as a row from the source first
  family: lineage
  predicate: event in {Pre,Stop} and refs(output)-source.read!={}   [terms=2; inferred until attacked]
  merged: one line with A2,G1,H1,H4; one check serves them
  effect: citation
  check: content.fabricated_commit_sha
  dedupe: effect "citation" shared with content.phantom_citation,content.unsourced_webfetch; collapse candidate
  status: per-case: not landed in #105
  owner: lineage (decided: its line reads the read ledger: every name the output uses traces to a source read this session); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it
H6  FUNCTION DRAWN FROM NO CLAIM
    a unit answering to nothing in the source
  > one source claim per unit, or delete it
  family: scour
  predicate: node=def and not decorated and not name matches "^test_" and refs={}   [terms=3; inferred until attacked]
  effect: orphan
  check: gate.unclaimed_unit
  status: per-case: not landed in #105
  owner: scour (decided: its line reads only the tree, statically); owner-dedupe finding: Scour and Makoto both cover it today, the other drops it


===== MERGES MADE HERE (each proven) ===
Survivor's fix alone catches the dropped
entry's trip. Survivor picked by fix.

A7 (+B6): trip B6, the total reported is
  not the total graded; the per-unit table
  has fewer rows than the total. B6's
  second fix, "name their run", is a
  second fix (rule 5); it is H5's, and
  H5 carries it.
B2 (+B8 B22): trip B8, absence taken as
  proof; the population counted reads
  zero, and a property over zero proves
  nothing.
C2 (+A1): trip A1, missing data defaults
  valid; a not-evaluable field is the
  sentinel outside the valid range.
D1 (+C1): trip C1, the failure computed,
  then dropped; the status read back
  through its consumer is green where red
  was computed.
D1 (+D2 F5): trip D2, landed where
  nothing consumes; reading back through
  the consumer finds nothing.
D9 (+B17): trip B17, the checker holds
  the pattern it hunts; excluded by
  identity, it is outside its own set.
  B17's lineage widening, "or the target
  was already red", is B1's fix (no flip)
  and is not carried here.
E7 (+E4): trip E4, the platform chose the
  posture; every condition set from clean
  leaves the platform nothing to choose.
F2 (+F1): trip F1, the fix on one twin;
  one owner leaves no twin.
G1 (+B24): trip B24, evidence attached to
  a bigger claim. G1's fix widened to
  "set each claim beside what it rests
  on": the sentence beside its source
  shows the gap. Re-run for G1's own
  trip: the claim "done" beside the
  request.
H1 (+F4): trip F4, built against a
  description; back to the source. Same
  fix.
H2 (+F3 F15 F16): trips: the referent
  moved; the record trails live state.
  Read the source again, once, last: the
  referent is read at use; the record is
  not read.
H5 (+D3 D7): trip D3, the copy isn't the
  one graded; a row from the source pins
  it.
H5 (+C9): trip C9, concluded, stated,
  never persisted; a decision named as a
  row from its sources is persisted. It
  was proposed into H1; H1's fix alone,
  back to the source, persists nothing.

Not merged, tried:
  B26 into C8: with the supervisor dead,
    waiting on the work's own emission
    never returns; a hang is not loud.
    Two fixes.
  F12 into H1: a read of the source gives
    a mechanism, not the observation that
    discriminates two. Two fixes.
  B20 into B1: a withdrawn plant still
    shows a flip; B1's fix passes it.
  F7 into H2 (no exclusion); F10 into H1
    (a record is a row); B14 into H6 (a
    claimed unit can still not help); E5
    into H3 (a cap names no cause); B9
    into H2 (a waiver is static).


===== FAMILIES ==========================
Filed by what the checker needs, not by
letter. One input trips each shape and no
other: a count equal at producer and
consumer but wrong against the graded rows
fires the spec alone; a stale derivative
fires the other point alone, no input
moves it; a fail branch written but never
selected passes the spec and fails the
switch; a proof that read only its claim
fires the lineage alone. The seven letters
split into these: the value and the wrong
question mostly spec; verdict, effect and
elsewhere mostly the other point; check
and branch mostly the switch; the answer
the lineage. Each entry sits under the
shape its fix line takes.

===== GAPS AND LINEAGE ==================
B31: no revision in reach holds its text;
  the id is retired, not reused.
The riders written before this revision
  (A10 B27 B3 B29 A9 B13 B30 B15 B33 F11
  B25 B12 B19 B16 E2 A8 D5 D6 A12 D10 E6
  F13 F9 G4) carry no proof and no text
  in any revision in reach; they ride as
  received.
Entered from the lineage's additions
  pass: A14 B35 B36 C11 C12, each with its
  incident and its rule-2 check there.
  B36 was that pass's B34, renumbered
  because B34 was taken here first.
B20 and D13 take the lineage's widenings;
  each re-ran step 1 for its own id.


===== ADDING TO THIS REGISTER ==========
Add only what cost you something in this
run, with the incident in hand.

1  Write the fix line first, before the
   name. The fix is the entry's identity.

2  Set that fix beside every existing fix
   line, all families. If any one, applied,
   would have caught the incident, stop:
   cite that id. Two symptoms with one test
   are one entry. Widen the old wording if
   it needs to; never add a twin.

3  Strike every noun that names a tool,
   format, language, artifact, medium, or
   vendor. If the entry still reads, keep
   the struck version. If it doesn't, the
   entry was about the tool: rewrite until
   it does, or drop it.

4  Name one input that would trip this
   entry and no other. None: it's a twin.

5  Two fixes means two entries.

6  File it under what its checker needs,
   whatever its letter says.

===== MERGING ==========================
A merge is a claim that one fix catches
both incidents. Prove it, both ways:

1  Name an input that trips the dropped
   entry. Apply the survivor's fix alone.
   If it doesn't catch that input, no merge.

2  Pick the survivor by fix, not by family
   or name. Same fix in another family is
   still the survivor.

3  Widen the survivor until step 1 passes
   for every id it carries. Then re-run
   step 1 for each of them: widening for
   one can loosen another.

4  Write the absorbed ids on the survivor:
   NAME  (+B15 B33 F11). Any later edit to
   that entry re-runs step 1 for each id
   listed. A gap in numbering with no
   carrier is an error.

Form: id, name, defect under ten words,
then "> " and the fix under ten.
Append within the family; never renumber,
entries cite these numbers.

```
